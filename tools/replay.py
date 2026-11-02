"""Shim to isimulator_core.replay:main (keeps the CR-03 §6.1 layout)."""
from isimulator_core.replay import main

if __name__ == "__main__":
    raise SystemExit(main())
