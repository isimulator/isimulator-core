"""Conformance tests for SimPyAdapter (ISIM-CR-03, conformance suite 6.4)."""
import importlib
import json
import pathlib

import pytest

from isimulator_core.adapter import get_adapter, register
from isimulator_core.adapter.base import AdapterBase
from isimulator_core.adapter.simpy_adapter import SimPyAdapter

GOLDEN_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "github__isimulator__examples"
    / "otchere-order-to-cash"
    / "simulation.json"
)
# Inside CI the examples repo is not available; the spec is vendored in fixtures.
VENDORED = pathlib.Path(__file__).parent / "fixtures" / "otchere_simulation.json"


def spec_path() -> pathlib.Path:
    return GOLDEN_PATH if GOLDEN_PATH.exists() else VENDORED


@pytest.fixture
def spec():
    return json.loads(spec_path().read_text())


def test_capability_binding():
    assert issubclass(get_adapter("discrete-event"), SimPyAdapter)
    with pytest.raises(KeyError):
        get_adapter("agent-based")


def test_register_enforces_required_operations():
    class Incomplete(AdapterBase):
        capability = "continuous"

        def load(self, spec):
            ...

    with pytest.raises(TypeError):
        register(Incomplete)


def test_load_accepts_otchere(spec):
    adapter = SimPyAdapter()
    handle = adapter.load(spec)
    assert handle.spec_version == spec["spec_version"]


def test_load_rejects_wrong_capability(spec):
    spec["execution"]["capability"] = "agent-based"
    with pytest.raises(ValueError):
        SimPyAdapter().load(spec)


def test_compile_builds_process_graph(spec):
    graph = SimPyAdapter().compile(SimPyAdapter().load(spec)).graph
    assert graph["processes"]["order-to-cash"] == [
        "order-validation",
        "credit-check",
        "inventory-allocation",
        "fulfillment",
        "shipment",
        "invoicing",
        "payment",
    ]
    assert len(graph["resources"]) == 7


def test_initialize_applies_overrides(spec):
    adapter = SimPyAdapter()
    ctx = adapter.compile(adapter.load(spec))
    scenario = {"id": "demand-plus-20", "parameter_overrides": {"order_rate": 120}}
    ready = adapter.initialize(ctx, scenario, 42)
    assert ready.context.handle.spec["parameters"]["order_rate"] == 120
    # the original iTwin document is never mutated
    assert spec["parameters"]["order_rate"] == 100


def test_initialize_applies_control_override(spec):
    adapter = SimPyAdapter()
    ctx = adapter.compile(adapter.load(spec))
    scenario = {"id": "capacity-plus-5", "control_overrides": {"fulfillment-capacity": 15}}
    ready = adapter.initialize(ctx, scenario, 42)
    capacities = {
        r["id"]: r["capacity"] for r in ready.context.handle.spec["model"]["resources"]
    }
    assert capacities["fulfillment-worker"] == 15


def test_run_completes_horizon(spec):
    adapter = SimPyAdapter()
    ready = adapter.initialize(adapter.compile(adapter.load(spec)), {"id": "baseline"}, 42)
    completion = adapter.run(ready, spec["execution"]["horizon"])
    assert completion.horizon == spec["execution"]["horizon"]


def test_result_is_normalized_r09(spec):
    adapter = SimPyAdapter()
    ready = adapter.initialize(adapter.compile(adapter.load(spec)), {"id": "baseline"}, 42)
    completion = adapter.run(ready, spec["execution"]["horizon"])
    result = adapter.result(completion)
    doc = result.to_dict()
    assert {m["id"] for m in doc["metrics"]} == {
        "throughput",
        "cycle-time",
        "backlog",
        "sla",
        "resource-utilization",
        "cost",
    }
    prov = doc["provenance"]
    assert prov["engine"] == "SimPy"
    assert prov["capability"] == "discrete-event"
    assert "configuration_hash" in prov and "random_seed" in prov


def test_observe_emits_simulated_observations(spec):
    adapter = SimPyAdapter()
    ready = adapter.initialize(adapter.compile(adapter.load(spec)), {"id": "baseline"}, 42)
    completion = adapter.run(ready, spec["execution"]["horizon"])
    observations = adapter.observe(completion)
    assert observations
    assert all(o.kind == "simulated" for o in observations)


def test_optional_operations_flagged():
    adapter = SimPyAdapter()
    with pytest.raises(NotImplementedError):
        adapter.step(None, 1)
    adapter.terminate(object())  # supported


def test_simpy_import_confined_to_adapter_module():
    """The SimPy import is confined to simpy_adapter.py (architectural constraint)."""
    import re

    pattern = re.compile(r"^\s*(?:import|from)\s+simpy\b", re.MULTILINE)
    package = pathlib.Path(importlib.util.find_spec("isimulator_core").origin).parent
    offenders = []
    for py in package.rglob("*.py"):
        if py.name == "simpy_adapter.py":
            continue
        if pattern.search(py.read_text()):
            offenders.append(py.name)
    assert not offenders
