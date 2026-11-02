"""Deterministic replay tests (ISIM-CR-03 R02, risk register: determinism gap).

Two replays with identical seed produce identical metric values.
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


def metric_map(result):
    return {
        (s["scenario"]["id"], m["id"]): m["value"]
        for s in result["scenarios"]
        for m in s["metrics"]
    }


def test_replay_is_deterministic():
    spec = json.loads(spec_path().read_text())
    a = metric_map(replay(spec))
    b = metric_map(replay(spec))
    assert a == b


def test_identical_seed_identical_single_run():
    from isimulator_core.adapter import SimPyAdapter

    spec = json.loads(spec_path().read_text())
    adapter = SimPyAdapter()
    ctx = adapter.compile(adapter.load(spec))
    horizon = spec["execution"]["horizon"]

    values = []
    for _ in range(2):
        ready = adapter.initialize(ctx, {"id": "baseline"}, 42)
        completion = adapter.run(ready, horizon)
        values.append({m["id"]: m["value"] for m in adapter.result(completion).metrics})
    assert values[0] == values[1]


def test_different_seed_changes_stochastic_outcomes():
    from isimulator_core.adapter import SimPyAdapter

    spec = json.loads(spec_path().read_text())
    adapter = SimPyAdapter()
    ctx = adapter.compile(adapter.load(spec))
    horizon = spec["execution"]["horizon"]

    results = []
    for seed in (42, 4242):
        ready = adapter.initialize(ctx, {"id": "baseline"}, seed)
        completion = adapter.run(ready, horizon)
        results.append({m["id"]: m["value"] for m in adapter.result(completion).metrics})
    assert results[0]["cycle-time"] != results[1]["cycle-time"]
