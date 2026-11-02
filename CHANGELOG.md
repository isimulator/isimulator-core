# Changelog

All notable changes to this repository are documented here. Format follows Keep a Changelog; versioning is semantic.

## [0.2.0] - 2026-09-02

### Added
- ISIM-CR-03 (Reference Engine Integration): first executable proof of the CR-02 framework.
- `AdapterBase` engine-neutral contract with capability registry (R01).
- `SimPyAdapter` for the `discrete-event` capability (IDR-0001; see docs ADR-0003) with deterministic replay via seeded numpy RandomState (R02).
- `isimulator-replay` CLI: spec in, normalized result out, replications aggregated (R03).
- Conformance suite: adapter operations, capability binding, normalized R09 results, provenance R10, deterministic replay, SimPy-import confinement, OTCHERE golden path end-to-end (R04).
- CI workflow running the conformance suite and the golden-path CLI replay on push/PR.
- Vendored OTCHERE fixture and committed deterministic replay evidence (asset I).

## [0.1.0] - 2026-08-31

### Added
- Initial repository seed for the iSimulator organization.
