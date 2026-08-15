"""Time and date — reads the Pi's own system clock, no network involved.

Simplest module in the set: fetch() never fails (nothing external to fail
on), so the last-known-good/stale path in orbiboard/modules/base.py is
effectively dead code here, but the module still follows the same
fetch()/render() contract as everything else for consistency.

No seconds ticker by design (matches how most dashboard clocks avoid a
constantly-redrawing display) — DEFAULT_INTERVAL_SEC just needs to be
shorter than a minute so the displayed time never lags by more than that.
"""
from datetime import datetime

from PIL import Image

from orbiboard.modules.base import Module
from orbiboard.render_utils import (
    FG, MUTED,
    new_canvas, load_font, draw_centered_text, draw_stale_badge, text_size,
)


class ClockModule(Module):
    MODULE_ID = "clock"
    DEFAULT_INTERVAL_SEC = 20  # keeps the displayed minute fresh without a seconds ticker

    def fetch(self, params: dict) -> dict:
        now = datetime.now()
        fmt_24h = params.get("format_24h", False)

        if fmt_24h:
            return {
                "time": now.strftime("%H:%M"),
                "ampm": None,
                "weekday": now.strftime("%A"),
                "date": now.strftime("%B %-d"),
            }
        return {
            "time": now.strftime("%-I:%M"),
            "ampm": now.strftime("%p"),
            "weekday": now.strftime("%A"),
            "date": now.strftime("%B %-d"),
        }

    def render(self, data: dict, stale: bool) -> Image.Image:
        canvas, draw = new_canvas()
        f_weekday = load_font(18)
        f_time = load_font(56)
        f_ampm = load_font(20)
        f_date = load_font(16)

        if not data or "time" not in data:
            draw_centered_text(draw, 120, 108, "No data", load_font(20), fill=MUTED)
            if stale:
                draw_stale_badge(draw)
            return canvas

        draw_centered_text(draw, 120, 40, data["weekday"].upper(), f_weekday, fill=MUTED)

        time_str = data["time"]
        ampm = data.get("ampm")
        w_time, h_time = text_size(draw, time_str, f_time)
        if ampm:
            w_ampm, h_ampm = text_size(draw, ampm, f_ampm)
            gap = 6
            x_start = 120 - (w_time + gap + w_ampm) / 2
            draw.text((x_start, 95), time_str, font=f_time, fill=FG)
            draw.text((x_start + w_time + gap, 95 + (h_time - h_ampm)), ampm, font=f_ampm, fill=MUTED)
        else:
            draw.text((120 - w_time / 2, 95), time_str, font=f_time, fill=FG)

        draw_centered_text(draw, 120, 175, data["date"], f_date, fill=MUTED)

        if stale:
            draw_stale_badge(draw)
        return canvas


MODULE = ClockModule()
