"""Minimal GC9A01 (240x240 round SPI LCD) driver.

Raw spidev + gpiozero, no displayio/CircuitPython dependency, so multiple
panels can share one physical bus with a software-toggled CS per panel (the
Pi 4 only has 2 hardware CE lines; the PRD wants up to 6 displays). Only
orbiboard/display/server.py should construct these — see the module
docstring in orbiboard/modules/base.py for why module workers never touch
SPI/GPIO directly.

The init register table below is the one published across most GC9A01
module vendors' own demo code (Waveshare, generic AliExpress modules, and
the drivers derived from them). It has NOT been validated against real
hardware yet — do that first via scripts/test_display.py during bring-up
(PRD milestone 1) before trusting it, and adjust MADCTL/gamma values here if
colors come out wrong (e.g. R/B swapped) or the picture is mirrored.
"""
import time

import spidev
from gpiozero import DigitalOutputDevice

WIDTH = 240
HEIGHT = 240

MADCTL_NORMAL = 0x08      # BGR order, no mirror/rotate
MADCTL_ROTATE_180 = 0xC8  # BGR order, MY|MX set — flips row+col scan order

# (command, [data bytes], delay_ms_after)
_INIT_SEQUENCE = [
    (0xEF, [], 0),
    (0xEB, [0x14], 0),
    (0xFE, [], 0),
    (0xEF, [], 0),
    (0xEB, [0x14], 0),
    (0x84, [0x40], 0),
    (0x85, [0xFF], 0),
    (0x86, [0xFF], 0),
    (0x87, [0xFF], 0),
    (0x88, [0x0A], 0),
    (0x89, [0x21], 0),
    (0x8A, [0x00], 0),
    (0x8B, [0x80], 0),
    (0x8C, [0x01], 0),
    (0x8D, [0x01], 0),
    (0x8E, [0xFF], 0),
    (0x8F, [0xFF], 0),
    (0xB6, [0x00, 0x20], 0),
    (0x36, [0x08], 0),            # MADCTL: BGR order, no mirror/rotate — may
                                   # be overridden after init, see rotate_180
                                   # in GC9A01.__init__/_run_init_sequence
    (0x3A, [0x05], 0),            # COLMOD: 16 bits/pixel (RGB565)
    (0x90, [0x08, 0x08, 0x08, 0x08], 0),
    (0xBD, [0x06], 0),
    (0xBC, [0x00], 0),
    (0xFF, [0x60, 0x01, 0x04], 0),
    (0xC3, [0x13], 0),
    (0xC4, [0x13], 0),
    (0xC9, [0x22], 0),
    (0xBE, [0x11], 0),
    (0xE1, [0x10, 0x0E], 0),
    (0xDF, [0x21, 0x0C, 0x02], 0),
    (0xF0, [0x45, 0x09, 0x08, 0x08, 0x26, 0x2A], 0),
    (0xF1, [0x43, 0x70, 0x72, 0x36, 0x37, 0x6F], 0),
    (0xF2, [0x45, 0x09, 0x08, 0x08, 0x26, 0x2A], 0),
    (0xF3, [0x43, 0x70, 0x72, 0x36, 0x37, 0x6F], 0),
    (0xED, [0x1B, 0x0B], 0),
    (0xAE, [0x77], 0),
    (0xCD, [0x63], 0),
    (0x70, [0x07, 0x07, 0x04, 0x0E, 0x0F, 0x09, 0x07, 0x08, 0x03], 0),
    (0xE8, [0x34], 0),
    (0x62, [0x18, 0x0D, 0x71, 0xED, 0x70, 0x70, 0x18, 0x0F, 0x71, 0xEF, 0x70, 0x70], 0),
    (0x63, [0x18, 0x11, 0x71, 0xF1, 0x70, 0x70, 0x18, 0x13, 0x71, 0xF3, 0x70, 0x70], 0),
    (0x64, [0x28, 0x29, 0xF1, 0x01, 0xF1, 0x00, 0x07], 0),
    (0x66, [0x3C, 0x00, 0xCD, 0x67, 0x45, 0x45, 0x10, 0x00, 0x00, 0x00], 0),
    (0x67, [0x00, 0x3C, 0x00, 0x00, 0x00, 0x01, 0x54, 0x10, 0x32, 0x98], 0),
    (0x74, [0x10, 0x85, 0x80, 0x00, 0x00, 0x4E, 0x00], 0),
    (0x98, [0x3E, 0x07], 0),
    (0x35, [], 0),                # tearing effect line ON
    (0x21, [], 0),                # display inversion ON (typical for GC9A01 panels)
    (0x11, [], 120),              # sleep out
    (0x29, [], 20),               # display ON
]


def reset_bus(rst_device):
    """Pulse the shared hardware RST line once for the whole bus.

    RST is wired identically to every panel (see docs/WIRING.md), so this
    must be called exactly once before initializing any panel. Pulsing it
    per-panel would also hardware-reset every already-initialized panel
    sharing the same line, wiping out their init sequence.
    """
    rst_device.off()
    time.sleep(0.02)
    rst_device.on()
    time.sleep(0.12)


class GC9A01:
    def __init__(self, spi_bus, spi_device, cs_pin, dc_device, rst_device,
                 speed_hz=40_000_000, width=WIDTH, height=HEIGHT,
                 rotate_180=False):
        self.width = width
        self.height = height
        self._rotate_180 = rotate_180

        # CS is the only line unique per panel. DC/RST are shared physical
        # lines across every panel on the bus (see docs/WIRING.md) — the
        # caller constructs one DigitalOutputDevice for each and passes them
        # in here, shared across all panels. Constructing our own per panel
        # would collide over the same GPIO pin as soon as a second panel
        # exists.
        self._cs = DigitalOutputDevice(cs_pin, initial_value=True)
        self._dc = dc_device
        self._rst = rst_device

        self._spi = spidev.SpiDev()
        self._spi.open(spi_bus, spi_device)
        self._spi.max_speed_hz = speed_hz
        self._spi.mode = 0b00
        # We never let the kernel drive CS (multiple panels share this bus);
        # each transfer is wrapped in explicit software CS below.
        self._spi.no_cs = True

        # Deliberately does NOT run the init sequence here. self._cs above
        # is now driven high (deselected), but a sibling panel constructed
        # after this one won't have claimed its own CS pin yet — until it
        # does, that pin is unclaimed/floating and can drift low (selected),
        # which would make it eavesdrop on and react to this panel's init
        # bytes on the shared MOSI/DC lines as if they were its own. The
        # caller must construct every panel on the bus first (so every CS
        # line is driven high), call reset_bus() once, and only then call
        # init_panel() on each — see build_panels() in display/server.py.

    def init_panel(self):
        self._run_init_sequence()

    def _write(self, data, is_data):
        self._dc.value = is_data
        self._cs.off()
        try:
            self._spi.writebytes2(data)
        finally:
            self._cs.on()

    def _cmd(self, cmd, data=()):
        self._write([cmd], is_data=False)
        if data:
            self._write(list(data), is_data=True)

    def _run_init_sequence(self):
        for cmd, data, delay_ms in _INIT_SEQUENCE:
            self._cmd(cmd, data)
            if delay_ms:
                time.sleep(delay_ms / 1000.0)
        if self._rotate_180:
            self._cmd(0x36, [MADCTL_ROTATE_180])

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(0x2A, [x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self._cmd(0x2B, [y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self._cmd(0x2C)

    def blit(self, rgb565_bytes):
        """Push a full-frame RGB565 buffer (width*height*2 bytes)."""
        expected = self.width * self.height * 2
        if len(rgb565_bytes) != expected:
            raise ValueError(f"expected {expected} bytes, got {len(rgb565_bytes)}")
        self._set_window(0, 0, self.width - 1, self.height - 1)
        self._dc.on()
        self._cs.off()
        try:
            # writebytes2 chunks internally; spidev has a per-call size limit
            # (commonly 4096B on Linux) well below a 115200B frame.
            chunk = 4096
            mv = memoryview(rgb565_bytes)
            for i in range(0, len(mv), chunk):
                self._spi.writebytes2(mv[i:i + chunk])
        finally:
            self._cs.on()

    def fill(self, rgb565_pixel: bytes):
        """Fill the whole panel with one repeated RGB565 pixel (2 bytes)."""
        self.blit(rgb565_pixel * (self.width * self.height))

    def close(self):
        """Closes this panel's own CS device and SPI fd only — dc/rst are
        shared across every panel on the bus and owned by the caller."""
        try:
            self._spi.close()
        finally:
            self._cs.close()
