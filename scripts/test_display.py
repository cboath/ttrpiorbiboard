#!/usr/bin/env python3
"""On-Pi hardware smoke test (PRD milestone 1).

Fills every enabled display with red, green, blue, then a checkerboard, so
you can confirm wiring + the GC9A01 init sequence without any of the
module/orchestrator machinery. Run this first when bringing up new hardware.

Usage (on the Pi, with SPI enabled and displays wired per docs/WIRING.md):
    python3 scripts/test_display.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from gpiozero import DigitalOutputDevice

from orbiboard.config import load_config, enabled_modules
from orbiboard.display.gpio import configure_lgpio_backend
from orbiboard.display.gc9a01 import GC9A01, reset_bus

RED = bytes([0xF8, 0x00])
GREEN = bytes([0x07, 0xE0])
BLUE = bytes([0x00, 0x1F])


def checkerboard(width, height, on=bytes([0xFF, 0xFF]), off=bytes([0x00, 0x00]), cell=20):
    buf = bytearray()
    for y in range(height):
        for x in range(width):
            lit = ((x // cell) + (y // cell)) % 2 == 0
            buf += on if lit else off
    return bytes(buf)


def main():
    configure_lgpio_backend()
    cfg = load_config()
    bus = cfg["display_bus"]
    width, height = bus.get("width", 240), bus.get("height", 240)
    pattern = checkerboard(width, height)

    # DC/RST are shared across every panel (see docs/WIRING.md) — one
    # device each, reused for every panel below.
    dc_device = DigitalOutputDevice(bus["dc_pin"], initial_value=False)
    rst_device = DigitalOutputDevice(bus["rst_pin"], initial_value=True)

    # Phase 1: construct every panel first, so every CS line is claimed and
    # driven high (deselected) before any SPI traffic happens. A panel built
    # (or tested) before its siblings exist would leave their CS pins
    # floating, and a floating CS can drift low and eavesdrop on/react to
    # traffic meant for another panel.
    panels = {}
    cs_pins = {}
    for module_id, mod_cfg in enabled_modules(cfg).items():
        cs_pins[module_id] = mod_cfg["cs_pin"]
        panels[module_id] = GC9A01(
            spi_bus=bus["spi_bus"], spi_device=bus["spi_device"],
            cs_pin=mod_cfg["cs_pin"], dc_device=dc_device, rst_device=rst_device,
            speed_hz=bus.get("spi_speed_hz", 40_000_000), width=width, height=height,
            rotate_180=mod_cfg.get("rotate_180", False),
        )

    # Phase 2: reset the shared bus once, then init each panel in turn.
    reset_bus(rst_device)
    for panel in panels.values():
        panel.init_panel()

    # Phase 3: now that every panel is initialized and idle (CS high except
    # during its own transfers below), it's safe to test them one at a time.
    for module_id, panel in panels.items():
        print(f"--- {module_id} (cs_pin={cs_pins[module_id]}) ---")
        for name, color in (("red", RED), ("green", GREEN), ("blue", BLUE)):
            print(f"  fill {name}")
            panel.fill(color)
            time.sleep(1)
        print("  checkerboard pattern")
        panel.blit(pattern)
        time.sleep(2)
        panel.close()
        print(f"  {module_id}: done — confirm colors/orientation look right\n")

    dc_device.close()
    rst_device.close()


if __name__ == "__main__":
    main()
