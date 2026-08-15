"""Stock ticker — cycles one holding at a time, 3s each, price colored by
gain/loss against your cost basis. No API key (Yahoo Finance's public chart
endpoint), no cloud account.

Holdings (symbol/shares/purchase_price) live in config/stocks.yaml
(gitignored — see config/stocks.example.yaml), not in config/modules.yaml
`params`, since this is a variable-length list of positions rather than a
handful of scalar settings. total_value isn't stored — it's shares times
whatever the live price is, recomputed every fetch().

Unlike the other modules, DEFAULT_INTERVAL_SEC is 3s, not minutes — that's
what drives the on-screen cycling, since run_module_forever
(orbiboard/modules/base.py) calls fetch()+render()+write_frame() once per
interval. Each fetch() call advances to the next holding and returns just
that one, so render() only ever draws a single ticker per call, same as
every other module's contract. To avoid hammering Yahoo every 3 seconds,
actual price lookups are cached per-symbol on this Module instance (only
one instance is ever constructed, per run_module_forever) and only
refreshed every PRICE_TTL_SEC.

Caveat: this Yahoo endpoint is unofficial and undocumented (no public API
docs, no key) — same caveat as claude_usage's usage endpoint. It can change
or start rate-limiting without notice.

Known cost of the 3s cycle: run_module_forever writes a last-known-good
JSON snapshot to state/ on every successful fetch(), so this module writes
to the SD card roughly once every 3 seconds indefinitely, vs. once every
10-15 minutes for weather/claude_usage. Worth knowing if SD card wear on an
always-on Pi matters to you.
"""
import os
import time

import yaml
from PIL import Image

from orbiboard.modules.base import Module
from orbiboard.net import net
from orbiboard.paths import STOCKS_FILE, STOCKS_EXAMPLE_FILE
from orbiboard.render_utils import (
    FG, MUTED, GREEN, RED,
    new_canvas, load_font, draw_centered_text, draw_stale_badge,
)

QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
QUOTE_HEADERS = {"User-Agent": "Mozilla/5.0 (orbiboard stocks module)"}
PRICE_TTL_SEC = 60  # how often each symbol's live price is actually re-fetched


def _load_holdings():
    if not os.path.exists(STOCKS_FILE):
        raise RuntimeError(
            f"{STOCKS_FILE} not found. Copy config/stocks.example.yaml to "
            f"config/stocks.yaml and fill in your positions:\n"
            f"  cp {STOCKS_EXAMPLE_FILE} {STOCKS_FILE}"
        )
    with open(STOCKS_FILE) as f:
        cfg = yaml.safe_load(f) or {}
    holdings = cfg.get("holdings") or []
    if not holdings:
        raise RuntimeError(f"{STOCKS_FILE} has no holdings listed")
    return holdings


def _fetch_price(symbol):
    resp = net.get_json(
        QUOTE_URL.format(symbol=symbol),
        headers=QUOTE_HEADERS,
        params={"interval": "1d", "range": "1d"},
    )
    if not resp:
        raise RuntimeError(f"stocks: quote fetch failed for {symbol}")
    try:
        price = resp["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"stocks: unexpected response shape for {symbol}")
    return float(price)


class StocksModule(Module):
    MODULE_ID = "stocks"
    DEFAULT_INTERVAL_SEC = 3  # drives the on-screen cycle, see module docstring

    def __init__(self):
        self._index = 0
        self._price_cache = {}  # symbol -> {"price": float, "fetched_at": float}

    def _price_for(self, symbol):
        cached = self._price_cache.get(symbol)
        now = time.monotonic()
        if cached and (now - cached["fetched_at"]) < PRICE_TTL_SEC:
            return cached["price"]

        try:
            price = _fetch_price(symbol)
        except RuntimeError:
            if cached:
                return cached["price"]  # stale but better than nothing
            raise

        self._price_cache[symbol] = {"price": price, "fetched_at": now}
        return price

    def fetch(self, params: dict) -> dict:
        holdings = _load_holdings()
        holding = holdings[self._index % len(holdings)]
        self._index += 1

        symbol = holding["symbol"]
        shares = holding.get("shares")
        purchase_price = holding.get("purchase_price")

        price = self._price_for(symbol)

        gain = gain_pct = None
        if purchase_price:
            gain = price - purchase_price
            gain_pct = (gain / purchase_price) * 100

        total_value = shares * price if shares is not None else None

        return {
            "symbol": symbol,
            "price": price,
            "shares": shares,
            "purchase_price": purchase_price,
            "total_value": total_value,
            "gain": gain,
            "gain_pct": gain_pct,
        }

    def render(self, data: dict, stale: bool) -> Image.Image:
        canvas, draw = new_canvas()
        f_symbol = load_font(26)
        f_price = load_font(46)
        f_gain = load_font(18)
        f_small = load_font(14)

        if not data or "symbol" not in data:
            draw_centered_text(draw, 120, 108, "No data", load_font(20), fill=MUTED)
            if stale:
                draw_stale_badge(draw)
            return canvas

        gain = data.get("gain")
        color = FG if gain is None else (GREEN if gain >= 0 else RED)

        draw_centered_text(draw, 120, 22, data["symbol"], f_symbol, fill=FG)

        price = data.get("price")
        if price is not None:
            draw_centered_text(draw, 120, 90, f"${price:,.2f}", f_price, fill=color)

        gain_pct = data.get("gain_pct")
        if gain is not None and gain_pct is not None:
            sign = "+" if gain >= 0 else "-"
            draw_centered_text(draw, 120, 150, f"{sign}${abs(gain):,.2f} ({sign}{abs(gain_pct):.1f}%)",
                                f_gain, fill=color)

        shares = data.get("shares")
        total_value = data.get("total_value")
        if shares is not None:
            draw_centered_text(draw, 120, 184, f"{shares:g} sh", f_small, fill=MUTED)
        if total_value is not None:
            draw_centered_text(draw, 120, 202, f"Value ${total_value:,.2f}", f_small, fill=MUTED)

        if stale:
            draw_stale_badge(draw)
        return canvas


MODULE = StocksModule()
