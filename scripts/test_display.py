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

from orbiboard.config import load_config, enabled_modules
from orbiboard.display.gpio import configure_lgpio_backend
from orbiboard.display.gc9a01 import GC9A01

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

    for module_id, mod_cfg in enabled_modules(cfg).items():
        print(f"--- {module_id} (cs_pin={mod_cfg['cs_pin']}) ---")
        panel = GC9A01(
            spi_bus=bus["spi_bus"], spi_device=bus["spi_device"],
            cs_pin=mod_cfg["cs_pin"], dc_pin=bus["dc_pin"], rst_pin=bus["rst_pin"],
            speed_hz=bus.get("spi_speed_hz", 40_000_000), width=width, height=height,
        )
        for name, color in (("red", RED), ("green", GREEN), ("blue", BLUE)):
            print(f"  fill {name}")
            panel.fill(color)
            time.sleep(1)
        print("  checkerboard pattern")
        panel.blit(pattern)
        time.sleep(2)
        panel.close()
        print(f"  {module_id}: done — confirm colors/orientation look right\n")


if __name__ == "__main__":
    main()
