# Wiring

## Shared bus (every display)

All displays share one SPI0 bus. Wire these four lines identically to every
panel (daisy-chained, not one-per-panel):

| GC9A01 pin | Pi 4 pin (BCM) | Physical pin |
|---|---|---|
| SCL / SCK  | GPIO11 (SPI0 SCLK) | 23 |
| SDA / MOSI | GPIO10 (SPI0 MOSI) | 19 |
| DC         | GPIO24 | 18 |
| RST        | GPIO25 | 22 |
| VCC        | 3.3V | 1 or 17 |
| GND        | GND | any GND pin |

We do **not** wire MISO (GC9A01 is write-only) and we do **not** use the
Pi's hardware CE0/CE1 lines — every panel's CS is a plain software-toggled
GPIO output instead, because 6 displays need 6 independent CS lines and the
Pi 4 only exposes 2 hardware chip-selects on SPI0.

## Per-display CS pin (unique per panel)

6 slots provisioned now per your call (4 spare beyond the launch pair).
Chosen to avoid SPI0's own pins (GPIO7-11), I2C (GPIO2/3), and UART
(GPIO14/15):

| Module (config/modules.yaml key) | CS pin (BCM) | Physical pin | Status |
|---|---|---|---|
| `weather` | GPIO5 | 29 | wired at launch |
| `claude_usage` | GPIO13 | 33 | wired (swapped from GPIO6 during bring-up) |
| `bambu_printer` | GPIO6 | 31 | wired (swapped from GPIO13 during bring-up) |
| `stocks` | GPIO16 | 36 | spare, wire when needed |
| `clock` | GPIO19 | 35 | spare, wire when needed |
| `reserved_4` | GPIO26 | 37 | spare |

**Before wiring:** double-check none of these BCM pins are already claimed
by another HAT or peripheral on your Pi. If one conflicts, just pick a
different free GPIO and update the `cs_pin` for that slot in
`config/modules.yaml` — nothing else in the codebase hardcodes pin numbers.

## Power

Confirm total display current draw stays within the Pi's 3.3V rail budget as
more panels are added (PRD open item) — if 6 GC9A01 panels pull too much,
power the displays from a separate regulated 3.3V source instead of the
Pi's own rail, sharing only GND.

## Bring-up

1. Wire the shared bus + the 2 launch CS pins.
2. Enable SPI: `sudo raspi-config` → Interfacing Options → SPI → Enable.
3. `cp config/modules.example.yaml config/modules.yaml` and adjust pins if
   you deviated from the table above.
4. `python3 scripts/test_display.py` — fills each configured display with
   red/green/blue/checkerboard. This is also the first real validation of
   the GC9A01 init sequence in `orbiboard/display/gc9a01.py`, which was
   written from the commonly-published register table but not yet tested
   against real hardware — if colors are swapped (R/B) or the image is
   mirrored, check `MADCTL` (0x36) in that file first.

## Known issue: multi-panel signal integrity on breadboard jumpers

With 2 panels sharing the bus over breadboard jumper wires, `spi_speed_hz:
8000000` was already unreliable — one panel would initialize and blit fine,
the other would stay blank or show a white screen, with no error raised
(writes succeed at the SPI level even when the receiving panel doesn't latch
them correctly). This looked exactly like a bad CS connection at first (and
a real floating-CS issue was also fixed along the way — every panel's CS
line needs a pull-up to 3.3V so a momentarily disconnected/loose CS defaults
to deselected rather than self-selecting), but swapping panels, CS pins, and
even trying a totally unused spare CS pin (GPIO13) all reproduced the same
failure. Dropping `spi_speed_hz` to `1000000` (1MHz) fixed it immediately —
confirming it was bus loading/reflection from 2 panels on the shared
MOSI/SCK/DC/RST lines, not a bad panel or a bad CS wire.

Expect this to get worse, not better, as more of the 6 provisioned panels
get wired — re-test at whatever speed is currently configured each time a
new panel is added, and raise the speed only after confirming all panels
work together at the lower one.
