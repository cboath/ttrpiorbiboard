"""Shared drawing helpers for module render() implementations.

Every module renders a 240x240 RGB frame with Pillow and hands it to
pack_rgb565() for the display server. Keeping the drawing primitives here
(rather than duplicated per module) is what makes a new module mostly just
"fetch some data + call a couple of these".
"""
import math
import os
from datetime import datetime, timezone
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

from orbiboard.paths import FONT_DIR, ICON_DIR

# --- Theme -------------------------------------------------------------
BG = (12, 14, 18)
FG = (235, 238, 242)
MUTED = (140, 148, 160)
ACCENT = (86, 180, 255)
WARN = (255, 176, 60)
TRACK = (40, 44, 52)

WIDTH = HEIGHT = 240


def new_canvas(bg=BG):
    img = Image.new("RGB", (WIDTH, HEIGHT), bg)
    return img, ImageDraw.Draw(img)


@lru_cache(maxsize=32)
def load_font(size, name="Aldrich-Regular.ttc"):
    path = os.path.join(FONT_DIR, name)
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=64)
def load_icon(name, size=(48, 48)):
    """Load a 1-bit icon bitmap and recolor it for a dark canvas.

    Source assets in assets/icons are black-on-transparent glyphs from the
    reference project's icon set; invert to white-on-transparent so they
    read on our dark background.
    """
    path = os.path.join(ICON_DIR, f"{name}.bmp")
    if not os.path.exists(path):
        return None
    with Image.open(path) as f_img:
        img = f_img.convert("L").resize(size)
        img = ImageOps.invert(img)
        alpha = img.point(lambda p: p)
        white = Image.new("RGBA", img.size, (255, 255, 255, 255))
        white.putalpha(alpha)
        return white


def draw_icon(canvas, xy, name, size=(48, 48)):
    icon = load_icon(name, size)
    if icon:
        canvas.paste(icon, xy, icon)


def text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_centered_text(draw, cx, y, text, font, fill=FG):
    w, _ = text_size(draw, text, font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill)


def draw_ring(draw, cx, cy, radius, pct, width=14, color=ACCENT, track=TRACK):
    """Percentage ring gauge, 0-100, starting at 12 o'clock, clockwise."""
    pct = max(0.0, min(100.0, pct))
    bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.arc(bbox, start=-90, end=270, fill=track, width=width)
    if pct > 0:
        end = -90 + 360 * (pct / 100.0)
        draw.arc(bbox, start=-90, end=end, fill=color, width=width)


def time_until(iso_str):
    """Format an ISO-8601 reset timestamp as a short countdown string."""
    if not iso_str:
        return "N/A"
    try:
        target = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = target - now
        secs = diff.total_seconds()
        if secs < 0:
            return "resetting"
        hours, rem = divmod(secs, 3600)
        days, hours = divmod(hours, 24)
        minutes = rem // 60
        if days > 0:
            return f"{int(days)}d {int(hours)}h"
        return f"{int(hours)}h {int(minutes)}m"
    except Exception:
        return "N/A"


def draw_stale_badge(draw, canvas_size=(WIDTH, HEIGHT)):
    """Small corner dot + label indicating rendered data is a stale cache."""
    w, _ = canvas_size
    draw.ellipse((w - 22, 8, w - 10, 20), fill=WARN)


def pack_rgb565(image: Image.Image) -> bytes:
    """Convert an RGB PIL image to big-endian RGB565 bytes for the panel."""
    if image.mode != "RGB":
        image = image.convert("RGB")
    px = image.load()
    w, h = image.size
    out = bytearray(w * h * 2)
    i = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            val = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[i] = (val >> 8) & 0xFF
            out[i + 1] = val & 0xFF
            i += 2
    return bytes(out)
