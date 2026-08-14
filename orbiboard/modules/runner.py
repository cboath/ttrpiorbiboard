"""CLI entrypoint for a single module worker.

    python -m orbiboard.modules.runner --module weather

Looks up orbiboard.modules.<module_id> and expects it to expose a module-level
`MODULE` instance (a Module subclass). This is the convention new modules
follow too — see docs/ADDING_A_MODULE.md.
"""
import argparse
import importlib
import logging

from orbiboard.config import load_config
from orbiboard.modules.base import run_module_forever

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    parser = argparse.ArgumentParser(description="orbiboard module worker")
    parser.add_argument("--module", required=True, help="module id, e.g. weather")
    parser.add_argument("--config", default=None, help="path to modules.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    mod_cfg = cfg["modules"].get(args.module)
    if mod_cfg is None:
        raise SystemExit(f"module '{args.module}' not found in config")
    if not mod_cfg.get("enabled"):
        raise SystemExit(f"module '{args.module}' is not enabled in config")

    mod = importlib.import_module(f"orbiboard.modules.{args.module}")
    instance = getattr(mod, "MODULE", None)
    if instance is None:
        raise SystemExit(f"orbiboard.modules.{args.module} has no MODULE instance")

    interval = mod_cfg.get("refresh_interval_sec")
    run_module_forever(instance, mod_cfg.get("params", {}), interval)


if __name__ == "__main__":
    main()
