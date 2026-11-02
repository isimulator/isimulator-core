"""Adapter package: engine-neutral contract plus concrete adapters.

Importing this package registers all bundled adapters.
"""
from . import simpy_adapter  # noqa: F401  (registers SimPyAdapter)
from .simpy_adapter import SimPyAdapter  # noqa: F401
from .base import (  # noqa: F401
    AdapterBase,
    AdapterHandle,
    CompletionState,
    ExecutionContext,
    NormalizedResult,
    Observation,
    ReadyState,
    TerminalState,
    get_adapter,
    register,
)
