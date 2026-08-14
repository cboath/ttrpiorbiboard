#!/usr/bin/env python3
"""Dev-machine preview: run one module fetch+render cycle, save a PNG.

No SPI/GPIO involved, so this works on a Mac/laptop with no Pi attached —
useful for iterating on a module's data-fetching and layout before it ever
touches real hardware. See docs/ADDING_A_MODULE.md.

Usage:
    python3 scripts/sim_preview.py --module weather
    python3 scripts/sim_preview.py --module claude_usage --watch
"""
import argparse
import importlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from orbiboard.config import load_config, ConfigError
from orbiboard.paths import CONFIG_EXAMPLE_FILE, REPO_ROOT

OUT_DIR = os.path.join(REPO_ROOT, "state", "previews")


def get_params(module_id):
    try:
        cfg = load_config()
    except ConfigError:
        cfg = load_config(CONFIG_EXAMPLE_FILE)
    mod_cfg = cfg["modules"].get(module_id, {})
    return mod_cfg.get("params", {})


def run_once(module_id, params):
    mod = importlib.import_module(f"orbiboard.modules.{module_id}")
    instance = getattr(mod, "MODULE")

    stale = False
    try:
        data = instance.fetch(params)
        print(f"fetch() ok: {data}")
    except Exception as e:
        print(f"fetch() failed ({e}) — rendering with empty/stale data, as it would on hardware")
        data = {}
        stale = True

    image = instance.render(data, stale)
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{module_id}.png")
    image.save(out_path)
    print(f"saved {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True)
    parser.add_argument("--watch", action="store_true", help="re-run every 30s")
    args = parser.parse_args()

    params = get_params(args.module)
    if args.watch:
        while True:
            run_once(args.module, params)
            time.sleep(30)
    else:
        run_once(args.module, params)


if __name__ == "__main__":
    main()
