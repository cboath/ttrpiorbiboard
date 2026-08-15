"""Bambu Lab 3D printer status — local LAN MQTT, no cloud account needed.

Fetch logic adapted from
~/Development/Waveshare-ePaper-10.85-dashboard/main.py (update_data_thread's
ENABLE_BAMBU branch) and the vendored bambulabs_api client at
~/Development/Waveshare-ePaper-10.85-dashboard/lib/bambulabs_api/. Unlike the
request/response modules (weather, claude_usage), bambulabs_api.Printer
keeps a persistent MQTT connection and updates its internal state from a
background thread — get_state()/get_percentage()/etc. read whatever the
printer last pushed rather than making a fresh network call. So the
connection is opened once and kept on this Module instance (run_module_forever
only ever constructs one instance per process) and fetch() just reads the
latest cached values each cycle, reconnecting if the link drops.

Requires LAN-only mode enabled on the printer, plus its IP, access code
(Settings > Network on the printer's screen), and serial number (Settings >
Device) in this module's `params` in config/modules.yaml — there's no sane
hardcoded default the way weather has a default lat/lon.
"""
import time

from PIL import Image

from orbiboard.modules.base import Module
from orbiboard.render_utils import (
    FG, MUTED, ACCENT, WARN,
    new_canvas, load_font, draw_ring, draw_centered_text, draw_stale_badge,
)

try:
    import bambulabs_api as bl
except ImportError:
    bl = None

CONNECT_SETTLE_SEC = 1.5  # time for the first MQTT pushall to land after connect()

STATE_LABELS = {
    "RUNNING": "PRINTING",
    "PAUSE": "PAUSED",
    "FINISH": "FINISHED",
    "PREPARE": "PREPARING",
    "FAILED": "FAILED",
    "IDLE": "IDLE",
}


class BambuPrinterModule(Module):
    MODULE_ID = "bambu_printer"
    DEFAULT_INTERVAL_SEC = 30  # print progress moves faster than weather/usage

    def __init__(self):
        self._printer = None

    def _ensure_connected(self, params: dict):
        if bl is None:
            raise RuntimeError("bambulabs_api not installed — pip install bambulabs-api")

        ip = params.get("ip")
        access_code = params.get("access_code")
        serial = params.get("serial")
        if not (ip and access_code and serial):
            raise RuntimeError(
                "bambu_printer needs 'ip', 'access_code', and 'serial' in params "
                "(see printer Settings > Network / Device)"
            )

        if self._printer is None:
            self._printer = bl.Printer(ip, access_code, serial)

        if not self._printer.mqtt_client_connected():
            self._printer.connect()
            time.sleep(CONNECT_SETTLE_SEC)

    def fetch(self, params: dict) -> dict:
        self._ensure_connected(params)
        printer = self._printer

        if not printer.mqtt_client_connected():
            raise RuntimeError("bambu_printer: MQTT not connected")

        state = str(printer.get_state())
        if state == "UNKNOWN":
            raise RuntimeError("bambu_printer: no data pushed by printer yet")

        pct = printer.get_percentage()
        remaining = printer.get_time()
        return {
            "state": state,
            "percent": pct if isinstance(pct, (int, float)) else None,
            "remaining_min": remaining if isinstance(remaining, (int, float)) else None,
            "bed_temp": printer.get_bed_temperature(),
            "nozzle_temp": printer.get_nozzle_temperature(),
            "layer_cur": printer.current_layer_num(),
            "layer_total": printer.total_layer_num(),
        }

    def render(self, data: dict, stale: bool) -> Image.Image:
        canvas, draw = new_canvas()
        f_state = load_font(22)
        f_pct = load_font(40)
        f_label = load_font(16)
        f_small = load_font(14)

        if not data or "state" not in data:
            draw_centered_text(draw, 120, 108, "No data", load_font(20), fill=MUTED)
            if stale:
                draw_stale_badge(draw)
            return canvas

        state = data["state"]
        label = STATE_LABELS.get(state, state)
        active = state in ("RUNNING", "PAUSE", "PREPARE")

        draw_centered_text(draw, 120, 24, label, f_state,
                            fill=WARN if state == "FAILED" else FG)

        pct = data.get("percent")
        if active and pct is not None:
            draw_ring(draw, cx=120, cy=120, radius=64, pct=pct, width=14, color=ACCENT)
            pct_str = f"{round(pct)}%"
            w, h = draw.textbbox((0, 0), pct_str, font=f_pct)[2:]
            draw.text((120 - w / 2, 120 - h / 2), pct_str, font=f_pct, fill=FG)

            remaining = data.get("remaining_min")
            rem_str = f"{int(remaining)}m left" if remaining is not None else "—"
            draw_centered_text(draw, 120, 168, rem_str, f_label, fill=MUTED)

            layers = f"L {data.get('layer_cur', 0)}/{data.get('layer_total', 0)}"
            draw_centered_text(draw, 120, 188, layers, f_small, fill=MUTED)

        bed = data.get("bed_temp")
        nozzle = data.get("nozzle_temp")
        if bed is not None and nozzle is not None:
            draw_centered_text(draw, 120, 212, f"Bed {bed:.0f}°  Noz {nozzle:.0f}°",
                                f_small, fill=ACCENT)

        if stale:
            draw_stale_badge(draw)
        return canvas


MODULE = BambuPrinterModule()
