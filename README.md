# iSimulator: isimulator-core

Core simulation engine (runtime) that executes iTwins.

**Version:** 0.1.0
**Status:** Draft
**Last Updated:** 2026-08-31

---

## Scope

Hosts iTwins, configures scenarios (initial conditions, external events, control inputs), executes simulations faithful to entity semantics and temporal rules. Execution semantics (discrete-event, continuous, hybrid, agent-based) are an open decision.

## Status

## ISIM-CR-01 Alignment

This repo is the **Simulation Runtime** layer: clock, events, state, process, resources, controls, scheduler, rules, metrics, observers. It implements a simulation-engine abstraction (DES, continuous, discrete time, agent based, system dynamics, hybrid, co-simulation). First reference mode: Discrete Event Simulation; SimPy is an implementation dependency, never the conceptual model. Runtime API (ISIM-CR-05) is defined here until the boundary earns its own repository.


v0.1.0 seed. Structure and content evolve via versioned changes; see [isimulator/openspec](https://github.com/isimulator/openspec) for requirements and [isimulator/docs](https://github.com/isimulator/docs) for design context.
