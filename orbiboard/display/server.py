"""The one process that owns the shared SPI bus.

Reads config/modules.yaml, opens one GC9A01 handle per enabled module (each
on its own CS pin, all sharing the same MOSI/SCK/DC/RST), and polls each
module's rendered frame file for changes, pushing new bytes to the matching
panel. This is the only piece of the system that talks to SPI/GPIO — see
the plan's SPI-bus-arbitration note for why module workers never do this
directly (concurrent processes toggling CS on a shared bus can corrupt
whichever panel happens to have CS asserted at that instant).

Deliberately small and boring: nothing here should be able to crash on a
single module's bad data, since a dead display server blanks every panel,
not just one module's.
"""
import argparse
import logging
import os
import time

from gpiozero import DigitalOutputDevice

from orbiboard.config import load_config, enabled_modules
from orbiboard.display.gpio import configure_lgpio_backend
from orbiboard.display.gc9a01 import GC9A01, reset_bus
from orbiboard.paths import FRAME_DIR, ensure_state_dirs

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("orbiboard.display_server")

POLL_INTERVAL_SEC = 0.5


def frame_path(module_id):
    return os.path.join(FRAME_DIR, f"{module_id}.bin")


def build_panels(cfg):
    bus = cfg["display_bus"]

    # DC/RST are one shared physical line across every panel (see
    # docs/WIRING.md) — one device each, reused for every panel below.
    # Only CS is unique per panel.
    dc_device = DigitalOutputDevice(bus["dc_pin"], initial_value=False)
    rst_device = DigitalOutputDevice(bus["rst_pin"], initial_value=True)

    panels = {}
    for module_id, mod_cfg in enabled_modules(cfg).items():
        panels[module_id] = GC9A01(
            spi_bus=bus["spi_bus"],
            spi_device=bus["spi_device"],
            cs_pin=mod_cfg["cs_pin"],
            dc_device=dc_device,
            rst_device=rst_device,
            speed_hz=bus.get("spi_speed_hz", 40_000_000),
            width=bus.get("width", 240),
            height=bus.get("height", 240),
            rotate_180=mod_cfg.get("rotate_180", False),
        )
        log.info("claimed CS for module=%s cs_pin=%s", module_id, mod_cfg["cs_pin"])

    # Every panel's CS is now claimed and driven high (deselected) — only
    # now is it safe to pulse the shared RST line and run each panel's own
    # init sequence in turn (see GC9A01.__init__ for why order matters).
    reset_bus(rst_device)
    for module_id, panel in panels.items():
        panel.init_panel()
        log.info("initialized panel for module=%s", module_id)
    return panels


def run(cfg_path=None):
    ensure_state_dirs()
    configure_lgpio_backend()
    cfg = load_config(cfg_path)
    panels = build_panels(cfg)
    last_mtime = {module_id: 0.0 for module_id in panels}

    log.info("watching %d panel(s) in %s", len(panels), FRAME_DIR)
    while True:
        for module_id, panel in panels.items():
            path = frame_path(module_id)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime <= last_mtime[module_id]:
                continue
            try:
                with open(path, "rb") as f:
                    data = f.read()
                panel.blit(data)
                last_mtime[module_id] = mtime
                log.debug("pushed frame for %s", module_id)
            except Exception as e:
                log.error("failed to push frame for %s: %s", module_id, e)
        time.sleep(POLL_INTERVAL_SEC)


def main():
    parser = argparse.ArgumentParser(description="orbiboard SPI display server")
    parser.add_argument("--config", default=None, help="path to modules.yaml")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
