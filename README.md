# iSimulator: isimulator-core

Simulation runtime that executes iTwins through engine adapters.

**Version:** 0.2.0
**Status:** Active (ISIM-CR-03)
**Last Updated:** 2026-09-02

---

## Scope

Hosts iTwins, configures scenarios, and executes simulations through the
engine-neutral adapter contract from ISIM-CR-02
(`itwin-spec/contracts/engine-adapter.md`). Engine selection binds by
declared `execution.capability`; the first reference adapter is SimPy
(IDR-0001, docs ADR-0003). The iTwin document never references an engine.

## Contents

| Path | Content |
|------|---------|
| `isimulator_core/adapter/base.py` | AdapterBase contract: 10 operations, capability registry, normalized result (R01) |
| `isimulator_core/adapter/simpy_adapter.py` | SimPyAdapter: first concrete adapter, capability `discrete-event` (R02) |
| `isimulator_core/replay.py` | Replay CLI: load spec, dispatch by capability, run scenarios x replications, aggregate, emit normalized result (R03) |
| `tests/` | Conformance suite: adapter contract, deterministic replay, OTCHERE golden path, architectural boundary checks (R04) |
| `tests/fixtures/` | Vendored OTCHERE spec and committed deterministic replay evidence (asset I) |

## Quick start

```bash
pip install -e .[dev]
pytest -q
isimulator-replay tests/fixtures/otchere_simulation.json --output result.json
```

## ISIM-CR-01 Alignment

This repo is the **Simulation Runtime** layer: clock, events, state,
process, resources, controls, scheduler, rules, metrics, observers. SimPy
is an implementation dependency behind the adapter, never the conceptual
model. Runtime API (ISIM-CR-05) is defined here until the boundary earns
its own repository.

Structure and content evolve via versioned changes; see
[isimulator/openspec](https://github.com/isimulator/openspec) for
requirements and [isimulator/docs](https://github.com/isimulator/docs) for
design context.