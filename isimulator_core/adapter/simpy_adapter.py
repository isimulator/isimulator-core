"""SimPyAdapter: the first concrete adapter (ISIM-CR-03 R02, IDR-0001).

Architectural boundary (R06): this module is the ONLY place that imports
simpy. The iTwin document never references SimPy by name or module.

Determinism (R10): all stochastic operations (inter-arrival sampling,
duration sampling, failure draws) route through a numpy RandomState seeded
with the scenario seed. Two replays with identical seed produce identical
metric values (proved by tests/test_replay_determinism.py).

Time unit internal to the adapter: minutes.
"""
from __future__ import annotations

import copy
import statistics
from typing import Any

import simpy

from .base import (
    AdapterBase,
    AdapterHandle,
    CompletionState,
    ExecutionContext,
    NormalizedResult,
    Observation,
    ReadyState,
    TerminalState,
    config_hash,
    now_iso,
    register,
)

# --------------------------------------------------------------------------- 
# Unit conversion (all internal time is minutes)
# ---------------------------------------------------------------------------
_TO_MINUTES = {
    "minutes": 1.0, "hours": 60.0, "days": 1440.0, "seconds": 1.0 / 60.0,
    "minute": 1.0, "hour": 60.0, "day": 1440.0, "second": 1.0 / 60.0,
}


def _to_minutes(value: float, unit: str) -> float:
    try:
        return value * _TO_MINUTES[unit]
    except KeyError:
        raise ValueError(f"unsupported time unit {unit!r}") from None


def resolve_path(doc: dict[str, Any], path: str):
    """Resolve a spec path like parameters.order_rate or
    model.resources[fulfillment-worker].capacity. Returns (parent, key) or
    (None, None) when unresolvable."""
    import re

    tokens = re.findall(r"[^.\[\]]+", path)
    node: Any = doc
    for key in tokens[:-1]:
        if isinstance(node, list):
            match = [e for e in node if isinstance(e, dict) and e.get("id") == key]
            node = match[0] if match else None
        elif isinstance(node, dict):
            node = node.get(key)
        else:
            return None, None
        if node is None:
            return None, None
    leaf = tokens[-1]
    if isinstance(node, dict) and leaf in node:
        return node, leaf
    return None, None


# ---------------------------------------------------------------------------
# Run-time statistics container (one per simulation run)
# ---------------------------------------------------------------------------


class _RunStats:
    def __init__(self) -> None:
        self.completed = 0
        self.failed = 0
        self.cycle_times: list[float] = []
        self.busy: dict[str, float] = {}  # resource id -> busy minutes
        # time-weighted work-in-progress integral
        self.backlog_area = 0.0
        self._wip = 0
        self._last_t = 0.0
        self.cost_from_executions = 0.0
        self.sla_limit_minutes: float | None = None

    def wip_change(self, when: float, delta: int) -> None:
        self.backlog_area += self._wip * (when - self._last_t)
        self._last_t = when
        self._wip += delta

    def finalize(self, horizon_minutes: float) -> float:
        """Close the WIP integral; return the time-weighted mean backlog."""
        self.backlog_area += self._wip * (horizon_minutes - self._last_t)
        self._last_t = horizon_minutes
        return self.backlog_area / horizon_minutes if horizon_minutes else 0.0


@register
class SimPyAdapter(AdapterBase):
    capability = "discrete-event"
    adapter_version = "0.1.0"
    engine_name = "SimPy"
    engine_version = simpy.__version__

    # -- load --------------------------------------------------------------

    def load(self, spec: dict[str, Any]) -> AdapterHandle:
        if spec.get("execution", {}).get("capability") != self.capability:
            raise ValueError(
                f"spec declares capability "
                f"{spec.get('execution', {}).get('capability')!r}; "
                f"this adapter provides {self.capability!r}"
            )
        model = spec.get("model", {})
        for section in ("processes", "activities", "resources"):
            if not model.get(section):
                raise ValueError(f"model.{section} is empty or missing")
        act_ids = {a["id"] for a in model["activities"]}
        res_ids = {r["id"] for r in model["resources"]}
        for p in model["processes"]:
            for a in p.get("activities", []):
                if a not in act_ids:
                    raise ValueError(f"process {p['id']} references undefined activity {a}")
        for a in model["activities"]:
            for r in a.get("resources", []):
                if r not in res_ids:
                    raise ValueError(f"activity {a['id']} references undefined resource {r}")
        return AdapterHandle(spec=spec, spec_version=spec.get("spec_version", ""))

    # -- compile -----------------------------------------------------------

    def compile(self, handle: AdapterHandle) -> ExecutionContext:
        spec = handle.spec
        model = spec["model"]
        graph = {
            "processes": {p["id"]: p["activities"] for p in model["processes"]},
            "activities": {a["id"]: a for a in model["activities"]},
            "resources": {r["id"]: r for r in model["resources"]},
            "queues": {q["activity"]: q for q in model.get("queues", [])},
            "arrivals": model.get("arrivals", []),
            "metrics": {m["id"]: m for m in model.get("metrics", [])},
            "controls": {c["id"]: c for c in model.get("controls", [])},
            "rules": model.get("rules", []),
        }
        return ExecutionContext(handle=handle, graph=graph)

    # -- initialize --------------------------------------------------------

    @staticmethod
    def _apply_overrides(spec: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
        """Apply scenario parameter and control overrides to a deep copy."""
        doc = copy.deepcopy(spec)
        for key, value in (scenario.get("parameter_overrides") or {}).items():
            parent, leaf = resolve_path(doc, f"parameters.{key}")
            if parent is not None:
                parent[leaf] = value
        controls = {c["id"]: c for c in doc.get("model", {}).get("controls", [])}
        for cid, value in (scenario.get("control_overrides") or {}).items():
            control = controls.get(cid)
            if control is None:
                raise ValueError(f"control override references undefined control {cid}")
            parent, leaf = resolve_path(doc, control["target"])
            if parent is None:
                raise ValueError(f"control {cid} target {control['target']} does not resolve")
            parent[leaf] = value
        return doc

    def initialize(
        self, ctx: ExecutionContext, scenario: dict[str, Any], seed: int
    ) -> ReadyState:
        return ReadyState(
            context=ExecutionContext(
                handle=AdapterHandle(
                    spec=self._apply_overrides(ctx.handle.spec, scenario),
                    spec_version=ctx.handle.spec_version,
                ),
                graph=ctx.graph,
            ),
            scenario=scenario,
            seed=seed,
        )

    # -- run ---------------------------------------------------------------

    def run(self, state: ReadyState, horizon: dict[str, Any]) -> CompletionState:
        import numpy as np

        spec = state.context.handle.spec
        graph = self._recompile_graph(spec)
        horizon_minutes = _to_minutes(horizon["value"], horizon["unit"])

        # SLA limit from rules (condition "cycle_time > 4h" style)
        for rule in graph["rules"]:
            if "sla" in rule.get("id", "") or "cycle_time" in rule.get("condition", ""):
                import re

                m = re.search(r"(\d+(?:\.\d+)?)\s*h", rule.get("condition", ""))
                if m:
                    graph["sla_limit_minutes"] = float(m.group(1)) * 60.0

        rng = np.random.RandomState(state.seed)
        env = simpy.Environment()
        stats = _RunStats()
        stats.sla_limit_minutes = graph.get("sla_limit_minutes")

        resources = {
            rid: simpy.Resource(env, capacity=r["capacity"])
            for rid, r in graph["resources"].items()
        }

        def sample_duration(duration: dict[str, Any]) -> float:
            base = _to_minutes(duration["value"], duration.get("unit", "minutes"))
            dist = duration.get("distribution")
            if dist is None or dist == "constant":
                return base
            spread = duration.get("spread", 0.0)
            spread_minutes = _to_minutes(spread, duration.get("unit", "minutes"))
            if dist == "triangular":
                lo, hi = base - spread_minutes, base + spread_minutes
                return float(rng.triangular(lo, base, hi))
            if dist == "exponential":
                return float(rng.exponential(base))
            if dist == "uniform":
                return float(rng.uniform(base - spread_minutes, base + spread_minutes))
            raise ValueError(f"unsupported duration distribution {dist!r}")

        def order_process(env, chain):
            born = env.now
            for activity_id in chain:
                activity = graph["activities"][activity_id]
                for rid in activity.get("resources", []):
                    with resources[rid].request() as req:
                        yield req
                        duration = sample_duration(activity["duration"])
                        yield env.timeout(duration)
                        stats.busy[rid] = stats.busy.get(rid, 0.0) + duration
                if "cost_per_execution" in activity:
                    stats.cost_from_executions += activity["cost_per_execution"]
                if rng.random() < activity.get("failure_rate", 0.0):
                    stats.failed += 1
                    stats.wip_change(env.now, -1)
                    return
            stats.completed += 1
            stats.cycle_times.append(env.now - born)
            stats.wip_change(env.now, -1)

        for arrival in graph["arrivals"]:
            chain = graph["processes"][arrival["process"]]
            rate = arrival["rate"]
            period = _TO_MINUTES[rate.get("per", "hour")]
            mean_interval = period / rate["value"]

            def arrival_gen(chain=chain, mean_interval=mean_interval):
                while True:
                    yield env.timeout(float(rng.exponential(mean_interval)))
                    stats.wip_change(env.now, 1)
                    env.process(order_process(env, chain))

            env.process(arrival_gen())

        started = now_iso()
        env.run(until=horizon_minutes)
        mean_backlog = stats.finalize(horizon_minutes)
        ended = now_iso()

        completion = CompletionState(ready=state, horizon=horizon, started=started, ended=ended)
        completion.metrics = self._collect_metrics(spec, stats, horizon_minutes, mean_backlog)
        return completion

    # -- observe / result ----------------------------------------------------

    def observe(self, state: Any) -> list[Observation]:
        metrics = getattr(state, "metrics", None) or self._empty_metrics(state)
        return [
            Observation(
                id=f"obs-{m['id']}",
                kind="simulated",
                metric=m["id"],
                value=m["value"],
                timestamp=now_iso(),
            )
            for m in metrics
        ]

    def result(self, state: Any) -> NormalizedResult:
        metrics = getattr(state, "metrics", [])
        spec = state.ready.context.handle.spec
        provenance = {
            "spec_version": spec.get("spec_version"),
            "simulation_id": spec.get("simulation", {}).get("id"),
            "scenario_id": state.ready.scenario.get("id"),
            "adapter": "simpy-adapter",
            "adapter_version": self.adapter_version,
            "engine": self.engine_name,
            "engine_version": self.engine_version,
            "capability": self.capability,
            "configuration_hash": config_hash(spec),
            "random_seed": state.ready.seed,
            "horizon": state.horizon,
            "started": state.started,
            "ended": state.ended,
        }
        return NormalizedResult(
            metrics=metrics,
            observations=[o.__dict__ for o in self.observe(state)],
            provenance=provenance,
        )

    # -- optional operations -------------------------------------------------

    def step(self, state: Any, n: int) -> ReadyState:
        raise NotImplementedError("SimPyAdapter v1 does not support step")

    def terminate(self, state: Any) -> TerminalState:
        return TerminalState(state=state)

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _recompile_graph(spec: dict[str, Any]) -> dict[str, Any]:
        model = spec["model"]
        graph = {
            "processes": {p["id"]: p["activities"] for p in model["processes"]},
            "activities": {a["id"]: a for a in model["activities"]},
            "resources": {r["id"]: r for r in model["resources"]},
            "queues": {q["activity"]: q for q in model.get("queues", [])},
            "arrivals": model.get("arrivals", []),
            "metrics": {m["id"]: m for m in model.get("metrics", [])},
            "controls": {c["id"]: c for c in model.get("controls", [])},
            "rules": model.get("rules", []),
        }
        return graph

    @staticmethod
    def _empty_metrics(state: Any) -> list[dict[str, Any]]:
        return []

    def _collect_metrics(
        self,
        spec: dict[str, Any],
        stats: _RunStats,
        horizon_minutes: float,
        mean_backlog: float = 0.0,
    ) -> list[dict[str, Any]]:
        horizon_hours = horizon_minutes / 60.0
        horizon_days = horizon_minutes / 1440.0
        declared = spec.get("model", {}).get("metrics", [])

        values: dict[str, float] = {}
        values["throughput"] = stats.completed / horizon_hours
        values["cycle-time"] = (
            statistics.fmean(stats.cycle_times) if stats.cycle_times else 0.0
        )
        values["backlog"] = mean_backlog
        values["sla"] = (
            100.0 * sum(1 for ct in stats.cycle_times if ct <= stats.sla_limit_minutes)
            / len(stats.cycle_times)
            if stats.cycle_times
            else 0.0
        )
        busy_total = sum(stats.busy.values())
        capacity_total = sum(
            r["capacity"] * horizon_minutes for r in spec["model"]["resources"]
        )
        values["resource-utilization"] = (
            100.0 * busy_total / capacity_total if capacity_total else 0.0
        )
        labor_cost = sum(
            stats.busy.get(rid, 0.0) / 60.0 * r.get("cost_per_hour", 0.0)
            for rid, r in {r["id"]: r for r in spec["model"]["resources"]}.items()
        )
        values["cost"] = (labor_cost + stats.cost_from_executions) / max(horizon_days, 1e-9)

        out = []
        for m in declared:
            out.append(
                {
                    "id": m["id"],
                    "name": m["name"],
                    "unit": m["unit"],
                    "source": m.get("source", "simulated"),
                    "value": values.get(m["id"], 0.0),
                }
            )
        return out
