"""End-to-end golden path tests (ISIM-CR-03 acceptance).

Replays examples/otchere-order-to-cash/simulation.json through the
adapter and asserts the CR-02 section 22 acceptance behavior: baseline vs
demand-plus-20 produce different throughput.
"""
import json
import pathlib

from isimulator_core.replay import replay


def spec_path() -> pathlib.Path:
    golden = (
        pathlib.Path(__file__).resolve().parents[2]
        / "github__isimulator__examples"
        / "otchere-order-to-cash"
        / "simulation.json"
    )
    return golden if golden.exists() else pathlib.Path(__file__).parent / "fixtures" / "otchere_simulation.json"


def test_golden_path_replays_end_to_end():
    spec = json.loads(spec_path().read_text())
    result = replay(spec)
    assert result["simulation_id"] == "otchere-order-to-cash"
    assert result["capability"] == "discrete-event"


def test_all_six_declared_metrics_present():
    spec = json.loads(spec_path().read_text())
    result = replay(spec)
    for scenario in result["scenarios"]:
        ids = {m["id"] for m in scenario["metrics"]}
        assert ids == {
            "throughput",
            "cycle-time",
            "backlog",
            "sla",
            "resource-utilization",
            "cost",
        }


def test_baseline_vs_demand_plus_20_differ():
    spec = json.loads(spec_path().read_text())
    result = replay(spec)
    values = {s["scenario"]["id"]: {m["id"]: m["value"] for m in s["metrics"]} for s in result["scenarios"]}
    assert values["demand-plus-20"]["throughput"] > values["baseline"]["throughput"]


def test_committed_fixture_matches_replay():
    """Asset I: committed replay evidence is deterministic given fixed seed."""
    fixture = pathlib.Path(__file__).parent / "fixtures" / "otchere_replay.json"
    committed = json.loads(fixture.read_text())
    spec = json.loads(spec_path().read_text())
    fresh = replay(spec)
    committed_metrics = {
        (s["scenario"]["id"], m["id"]): m["value"]
        for s in committed["scenarios"]
        for m in s["metrics"]
    }
    fresh_metrics = {
        (s["scenario"]["id"], m["id"]): m["value"]
        for s in fresh["scenarios"]
        for m in s["metrics"]
    }
    assert committed_metrics == fresh_metrics
