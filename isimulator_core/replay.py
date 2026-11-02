"""Replay CLI (ISIM-CR-03 R03).

Loads an iTwin declarative simulation specification, selects an adapter by
declared execution capability from the registered adapter set, runs the
simulation under each declared scenario for the declared replications,
aggregates metrics across replications (mean, std, min, max), and writes
the normalized result (R09) with provenance (R10).

Usage:
    python -m isimulator_core.replay simulation.json
    python -m isimulator_core.replay simulation.json --output result.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

from .adapter import get_adapter
from .adapter.base import config_hash


def replay(spec: dict[str, Any]) -> dict[str, Any]:
    """Run every declared scenario; return the normalized result document."""
    from . import adapter as _pkg  # ensure bundled adapters are registered

    execution = spec.get("execution", {})
    capability = execution["capability"]
    adapter_cls = get_adapter(capability)
    adapter = adapter_cls()

    handle = adapter.load(spec)
    context = adapter.compile(handle)

    scenario_results = []
    for scenario in spec.get("scenarios", []):
        seed_base = scenario.get("random_seed", execution.get("random_seed", 0))
        horizon = scenario.get("horizon", execution.get("horizon"))
        replications = execution.get("replications", 1)

        replication_metrics: dict[str, list[float]] = {}
        first_result = None
        for rep in range(replications):
            seed = seed_base + rep
            ready = adapter.initialize(context, scenario, seed)
            completion = adapter.run(ready, horizon)
            result = adapter.result(completion)
            if first_result is None:
                first_result = result
            for m in result.metrics:
                replication_metrics.setdefault(m["id"], []).append(m["value"])

        aggregated = []
        for m in first_result.metrics:
            samples = replication_metrics[m["id"]]
            aggregated.append(
                {
                    "id": m["id"],
                    "name": m["name"],
                    "unit": m["unit"],
                    "source": m.get("source", "simulated"),
                    "value": statistics.fmean(samples),
                    "stats": {
                        "replications": len(samples),
                        "mean": statistics.fmean(samples),
                        "stdev": statistics.pstdev(samples) if len(samples) > 1 else 0.0,
                        "min": min(samples),
                        "max": max(samples),
                    },
                }
            )

        scenario_results.append(
            {
                "scenario": {"id": scenario["id"], "name": scenario.get("name", scenario["id"])},
                "metrics": aggregated,
                "provenance": {
                    "spec_version": spec.get("spec_version"),
                    "simulation_id": spec.get("simulation", {}).get("id"),
                    "scenario_id": scenario["id"],
                    "adapter": f"{adapter_cls.__module__}.{adapter_cls.__name__}",
                    "adapter_version": adapter_cls.adapter_version,
                    "engine": adapter_cls.engine_name,
                    "engine_version": adapter_cls.engine_version,
                    "capability": capability,
                    "configuration_hash": config_hash(spec),
                    "random_seed": seed_base,
                    "replications": replications,
                    "horizon": horizon,
                },
            }
        )

    return {
        "result_version": "0.1.0",
        "simulation_id": spec.get("simulation", {}).get("id"),
        "spec_version": spec.get("spec_version"),
        "capability": capability,
        "scenarios": scenario_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="isimulator-replay",
        description="Replay an iTwin declarative simulation specification.",
    )
    parser.add_argument("spec", help="path to the simulation specification JSON")
    parser.add_argument("--output", help="write the normalized result to this path")
    args = parser.parse_args(argv)

    spec = json.loads(Path(args.spec).read_text())
    result = replay(spec)

    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
