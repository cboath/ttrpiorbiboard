"""GPIO pin factory setup, shared by every process that touches GPIO.

Only orbiboard/display/server.py imports this — module workers never touch
GPIO/SPI directly (see docs/WIRING.md and the plan's SPI-bus-arbitration
rationale).

Prefer the lgpio backend: gpiozero's native/sysfs factory is broken on
Raspberry Pi OS Bookworm (kernel 6.x) and fails to export pins. This mirrors
the exact workaround already proven in
~/Development/Waveshare-ePaper-10.85-dashboard/main.py (lines ~98-116),
including importing from /tmp so lgpio's notification pipe never depends on
this project directory's permissions.
"""
import os


def configure_lgpio_backend():
    prev_cwd = os.getcwd()
    try:
        os.chdir("/tmp")
        from gpiozero import Device
        from gpiozero.pins.lgpio import LGPIOFactory
        Device.pin_factory = LGPIOFactory()
    except Exception as e:
        print(f"lgpio pin factory unavailable ({e}); using gpiozero default")
    finally:
        os.chdir(prev_cwd)
