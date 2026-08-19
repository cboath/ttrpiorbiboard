# ttrpiorbiboard

A desk-mounted, always-on Raspberry Pi 4 dashboard: each data "module"
(Claude Code usage, local weather, and more later) renders to its own
1.28" round GC9A01 SPI display. Displays share one SPI bus and are
distinguished by software-toggled CS pins, so new modules are pure
software additions once spare CS lines are wired.

Full requirements: [`PRD.md`](PRD.md).

## Architecture

- **Module workers** (`orbiboard/modules/*.py`, one systemd unit each) —
  fetch data on their own schedule, render a 240×240 Pillow frame, write it
  as RGB565 bytes to a shared tmpfs frame file. No SPI/GPIO access, so a
  crash or hang in one module can't affect another.
- **Display server** (`orbiboard/display/server.py`, single instance) — the
  only process that touches SPI/GPIO. Watches each module's frame file and
  pushes new bytes to the matching panel. Kept deliberately tiny since it's
  the one thing that must never crash.
- **systemd is the supervisor** — `Restart=on-failure` per module unit,
  `Restart=always` for the display server. No custom orchestrator process.

See [`docs/ADDING_A_MODULE.md`](docs/ADDING_A_MODULE.md) for how the two
launch modules were built and how to add a new one, and
[`docs/WIRING.md`](docs/WIRING.md) for the pin table.

## Hardware

Raspberry Pi 4, 6 GC9A01 round SPI displays wired on one bus (2 wired at
launch: weather + Claude usage; 4 spare CS lines reserved). See
`docs/WIRING.md` for the full pin table and bring-up steps.

## Setup (on the Pi)

```shell
sudo raspi-config   # Interfacing Options -> SPI -> Enable

sudo apt update
sudo apt install -y python3-pip python3-pil git \
    python3-gpiozero python3-lgpio python3-spidev
# (Bookworm's system Python rejects `pip install` for GPIO/SPI packages —
# install those via apt, everything else via pip.)

git clone <this repo> ttrpiorbiboard
cd ttrpiorbiboard
pip3 install -r requirements.txt --break-system-packages   # or use a venv

cp config/modules.example.yaml config/modules.yaml
# edit config/modules.yaml if your wiring differs from docs/WIRING.md
```

**Hardware bring-up** (do this before anything else — validates wiring and
the GC9A01 driver together):

```shell
python3 scripts/test_display.py
```

**Claude usage — one-time login** (PRD open question #1; run once, from the
Pi if it has a browser, or from any machine and copy
`state/claude_creds.json` onto the Pi afterwards):

```shell
python3 scripts/claude_auth_setup.py
```

**Bambu printer — one-time setup** (optional module, disabled by default;
flip `bambu_printer.enabled: true` in `config/modules.yaml` once you've done
this):

```shell
# LAN mode (default) — no script needed, just fill in config/modules.yaml:
#   bambu_printer.params.serial       (printer Settings > Device)
#   bambu_printer.params.ip           (printer Settings > Network)
#   bambu_printer.params.access_code  (printer Settings > Network)
# and make sure LAN-only mode is enabled on the printer.

# Cloud mode (mode: cloud) — run once instead, to cache a token:
python3 scripts/bambu_cloud_auth_setup.py
```

See `orbiboard/modules/bambu_printer.py` for the full LAN-vs-cloud tradeoffs.

**Run it:**

```shell
sudo cp systemd/orbiboard-display.service systemd/orbiboard-module@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now orbiboard-display
sudo systemctl enable --now orbiboard-module@weather
sudo systemctl enable --now orbiboard-module@claude_usage
# for any other module you've enabled in config/modules.yaml (bambu_printer,
# stocks, clock, ...), also enable its own worker unit the same way:
sudo systemctl enable --now orbiboard-module@bambu_printer
```

Every module needs its own `orbiboard-module@<id>` unit enabled — flipping
`enabled: true` in `config/modules.yaml` only tells the display server to
claim that panel's CS pin, it does **not** start the process that fetches
data and renders frames for it. A module with no worker running shows
nothing on its panel, silently (no error) — the display server just never
sees a frame file to push. So each time you enable another module (e.g.
`bambu_printer`, `stocks`, `clock`) in `config/modules.yaml`, also run:

```shell
sudo systemctl enable --now orbiboard-module@<module_id>
```

Both `systemd/*.service` files have `User=`/`WorkingDirectory=` placeholders
— edit them to match where you cloned the repo and which user has
`spi`/`gpio` group membership before copying them in.

## Developing without a Pi

Module fetch/render logic has no hardware dependency and can be iterated on
anywhere:

```shell
pip3 install -r requirements.txt   # spidev/gpiozero/lgpio will fail to
                                    # import off-Pi, but nothing outside
                                    # orbiboard/display/ needs them
python3 scripts/sim_preview.py --module weather
python3 scripts/sim_preview.py --module claude_usage
```

Saves a PNG per module to `state/previews/` instead of pushing to SPI.

## Adding a module

See [`docs/ADDING_A_MODULE.md`](docs/ADDING_A_MODULE.md) — write one file,
add one config entry, enable one systemd unit. No wiring, no changes to
existing modules.
