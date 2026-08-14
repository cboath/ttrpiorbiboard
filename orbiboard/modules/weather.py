"""Local weather module — Open-Meteo, no API key required.

Data source and weather-code-to-icon mapping adapted from
~/Development/Waveshare-ePaper-10.85-dashboard/main.py (get_weather_icon,
lines ~856-871, and the API_ENDPOINTS['weather'] call at line ~599).
"""
import math

from PIL import Image

from orbiboard.modules.base import Module
from orbiboard.net import net
from orbiboard.render_utils import (
    BG, FG, MUTED, ACCENT,
    new_canvas, load_font, draw_icon, draw_centered_text, draw_stale_badge,
)

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Default: zip 63043, Maryland Heights, MO (looked up via Zippopotam.us).
DEFAULT_LAT = 38.7229
DEFAULT_LON = -90.4474


def get_weather_icon(code, is_day=1):
    if code == 0:
        return "icon_sun" if is_day else "icon_moon"
    if code in (1, 2):
        return "icon_partly-cloudy-day"
    if code == 3:
        return "icon_clouds"
    if code in (45, 48):
        return "icon_wind"
    if code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
        return "icon_rain"
    if code in (71, 73, 75, 85, 86):
        return "icon_snow"
    if code in (95, 96, 99):
        return "icon_storm"
    return "icon_sun"


class WeatherModule(Module):
    MODULE_ID = "weather"
    DEFAULT_INTERVAL_SEC = 900  # 15 min

    def fetch(self, params: dict) -> dict:
        lat = params.get("latitude", DEFAULT_LAT)
        lon = params.get("longitude", DEFAULT_LON)
        resp = net.get_json(WEATHER_URL, params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,is_day",
            "daily": "temperature_2m_max,temperature_2m_min",
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
            "forecast_days": 1,
        })
        if not resp or "current" not in resp:
            raise RuntimeError("weather fetch failed or missing 'current'")

        cur = resp["current"]
        daily = resp.get("daily", {})
        return {
            "temp": cur.get("temperature_2m"),
            "humidity": cur.get("relative_humidity_2m"),
            "code": cur.get("weather_code", 0),
            "is_day": cur.get("is_day", 1),
            "hi": (daily.get("temperature_2m_max") or [None])[0],
            "lo": (daily.get("temperature_2m_min") or [None])[0],
        }

    def render(self, data: dict, stale: bool) -> Image.Image:
        canvas, draw = new_canvas()
        f_temp = load_font(64)
        f_label = load_font(16)
        f_small = load_font(14)

        if not data or data.get("temp") is None:
            draw_centered_text(draw, 120, 108, "No data", load_font(20), fill=MUTED)
            if stale:
                draw_stale_badge(draw)
            return canvas

        temp = round(data["temp"])
        icon_name = get_weather_icon(data.get("code", 0), data.get("is_day", 1))

        draw_icon(canvas, (78, 28), icon_name, size=(84, 84))
        draw_centered_text(draw, 120, 122, f"{temp}°F", f_temp, fill=FG)

        hi, lo = data.get("hi"), data.get("lo")
        if hi is not None and lo is not None:
            draw_centered_text(draw, 120, 190, f"H:{round(hi)}°  L:{round(lo)}°",
                                f_label, fill=MUTED)

        hum = data.get("humidity")
        if hum is not None:
            draw_centered_text(draw, 120, 212, f"Humidity {hum}%", f_small, fill=ACCENT)

        if stale:
            draw_stale_badge(draw)
        return canvas


MODULE = WeatherModule()
