"""AdapterBase: the engine-neutral adapter contract (ISIM-CR-03 R01).

Mirrors the operations table in
itwin-spec/contracts/engine-adapter.md (normative from ISIM-CR-02 R04).

Every concrete adapter inherits from AdapterBase. Required operations are
load, compile, initialize, run, observe, result. Optional operations
(pause, resume, step, terminate) are implemented when the underlying engine
supports them; unsupported operations raise NotImplementedError and the
conformance suite records them as optional-with-capability.

The adapter is the only place that may import an engine. iTwin documents
never reference engines by name or module (R05, R06).
"""
from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Module-level registry: capability -> adapter class (R03 dispatch by capability).
_REGISTRY: dict[str, type["AdapterBase"]] = {}


def register(adapter_cls: type["AdapterBase"]) -> type["AdapterBase"]:
    """Register an adapter class under its declared capability.

    Raises TypeError if a required operation is unimplemented.
    """
    required = ("load", "compile", "initialize", "run", "observe", "result")
    for op in required:
        if getattr(adapter_cls, op) is getattr(AdapterBase, op):
            raise TypeError(
                f"adapter {adapter_cls.__name__} does not implement required operation {op}"
            )
    if not getattr(adapter_cls, "capability", None):
        raise TypeError(f"adapter {adapter_cls.__name__} does not declare a capability")
    _REGISTRY[adapter_cls.capability] = adapter_cls
    return adapter_cls


def get_adapter(capability: str) -> type["AdapterBase"]:
    """Select an adapter by declared capability (never by engine name)."""
    try:
        return _REGISTRY[capability]
    except KeyError:
        raise KeyError(
            f"no registered adapter provides capability {capability!r}; "
            f"registered: {sorted(_REGISTRY)}"
        ) from None


# ---------------------------------------------------------------------------
# State objects of the adapter lifecycle (contract: load -> compile ->
# initialize -> run -> result, with observe available at any point).
# ---------------------------------------------------------------------------


@dataclass
class AdapterHandle:
    """Validated simulation specification plus adapter-private parsing."""

    spec: dict[str, Any]
    spec_version: str = ""


@dataclass
class ExecutionContext:
    """Engine model derived from the handle. Never mutates the iTwin document."""

    handle: AdapterHandle
    graph: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReadyState:
    context: ExecutionContext
    scenario: dict[str, Any]
    seed: int


@dataclass
class CompletionState:
    ready: ReadyState
    horizon: dict[str, Any]
    started: str
    ended: str


@dataclass
class PausedState:
    completion: CompletionState


@dataclass
class TerminalState:
    state: Any


@dataclass
class Observation:
    id: str
    kind: str  # epistemic kind: simulated for engine output (R09)
    metric: str
    value: Any
    timestamp: str


@dataclass
class NormalizedResult:
    """R09 normalized result with R10 provenance."""

    metrics: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "observations": self.observations,
            "provenance": self.provenance,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def config_hash(spec: dict[str, Any]) -> str:
    """Stable hash of the simulation configuration (provenance, R10)."""
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def validate_dotted_ref(spec: dict[str, Any], ref: str) -> bool:
    """Resolve a dotted reference such as parameters.order_rate within a spec."""
    node: Any = spec
    for part in re.split(r"\.", ref):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return False
    return True


class AdapterBase(ABC):
    """Abstract adapter surface mirroring the R04 operations table.

    Class attributes that concrete adapters MUST define:
      capability:      declared capability, one of the R05 enum
      adapter_version: semver of this adapter
      engine_name:     name of the underlying engine (reporting only)
      engine_version:  version of the underlying engine (reporting only)
    """

    capability: str = ""
    adapter_version: str = "0.0.0"
    engine_name: str = ""
    engine_version: str = ""

    @abstractmethod
    def load(self, spec: dict[str, Any]) -> AdapterHandle:
        """Validate that this adapter can represent the model."""

    @abstractmethod
    def compile(self, handle: AdapterHandle) -> ExecutionContext:
        """Derive the engine model. Never mutates the iTwin document."""

    @abstractmethod
    def initialize(
        self, ctx: ExecutionContext, scenario: dict[str, Any], seed: int
    ) -> ReadyState:
        """Apply scenario overrides and the random seed."""

    @abstractmethod
    def run(self, state: ReadyState, horizon: dict[str, Any]) -> CompletionState:
        """Execute to the horizon."""

    @abstractmethod
    def observe(self, state: Any) -> list[Observation]:
        """Emit normalized observations (epistemic kind simulated)."""

    @abstractmethod
    def result(self, state: Any) -> NormalizedResult:
        """Return the normalized R09 result with R10 provenance."""

    # Optional operations: engines that cannot support them leave the default.

    def pause(self, state: Any) -> PausedState:  # pragma: no cover
        raise NotImplementedError(f"{type(self).__name__} does not support pause")

    def resume(self, state: Any) -> Any:  # pragma: no cover
        raise NotImplementedError(f"{type(self).__name__} does not support resume")

    def step(self, state: Any, n: int) -> ReadyState:  # pragma: no cover
        raise NotImplementedError(f"{type(self).__name__} does not support step")

    def terminate(self, state: Any) -> TerminalState:  # pragma: no cover
        raise NotImplementedError(f"{type(self).__name__} does not support terminate")
