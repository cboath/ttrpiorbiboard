"""Claude Code rate-limit usage module.

Fetch logic adapted from
~/Development/Waveshare-ePaper-10.85-dashboard/claude.py (load_credentials,
refresh_access_token, fetch_usage) — same private OAuth usage endpoint the
Claude Code CLI itself calls. Credentials are produced once by
scripts/claude_auth_setup.py (the interactive PKCE login) and stored in
state/claude_creds.json; this module only ever refreshes, never re-prompts.

Undocumented-API risk (per the PRD): this endpoint isn't publicly documented
and could change without notice. If it starts failing outright, the
documented fallbacks are Claude Code's local JSONL usage logs or the
Admin API's GET /v1/organizations/usage_report/messages (requires an Admin
API key) — neither is implemented here, this module just goes stale and
shows the last-known values with a stale badge until it's fixed.
"""
import json
import os
import time

from PIL import Image

from orbiboard.modules.base import Module
from orbiboard.net import net
from orbiboard.paths import STATE_DIR
from orbiboard.render_utils import (
    FG, MUTED, ACCENT, WARN,
    new_canvas, load_font, draw_ring, draw_centered_text, draw_stale_badge,
    text_size, time_until,
)

CREDENTIALS_FILE = os.path.join(STATE_DIR, "claude_creds.json")
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # public, same as Claude Code CLI
REFRESH_BUFFER_SEC = 600
USER_AGENT = "orbiboard/0.1 (claude_usage module)"


def _load_credentials():
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    try:
        with open(CREDENTIALS_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_credentials(creds):
    tmp = CREDENTIALS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(creds, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CREDENTIALS_FILE)


def _token_is_expired(creds):
    expires_at = creds.get("expiresAt", 0)
    now_ms = int(time.time() * 1000)
    return now_ms >= (expires_at - REFRESH_BUFFER_SEC * 1000)


def _refresh_access_token(creds):
    refresh_token = creds.get("refreshToken")
    if not refresh_token:
        raise RuntimeError("no refresh token in stored credentials")
    resp = net.post_json(TOKEN_URL, json_body={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    })
    if resp is None or resp.status_code != 200:
        raise RuntimeError(f"token refresh failed: {getattr(resp, 'status_code', 'no response')}")
    data = resp.json()
    creds["accessToken"] = data.get("access_token")
    creds["expiresAt"] = int(time.time() * 1000) + data.get("expires_in", 28800) * 1000
    if "refresh_token" in data:
        creds["refreshToken"] = data["refresh_token"]
    _save_credentials(creds)
    return creds


def _fetch_usage(access_token):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    raw = net.get_json(USAGE_URL, headers=headers)
    if raw is None:
        raise RuntimeError("usage fetch failed")
    return raw


class ClaudeUsageModule(Module):
    MODULE_ID = "claude_usage"
    DEFAULT_INTERVAL_SEC = 600  # 10 min

    def fetch(self, params: dict) -> dict:
        creds = _load_credentials()
        if not creds:
            raise RuntimeError(
                "no credentials — run scripts/claude_auth_setup.py once to authorize"
            )

        if _token_is_expired(creds):
            creds = _refresh_access_token(creds)

        try:
            raw = _fetch_usage(creds["accessToken"])
        except RuntimeError:
            # Could be a stale/revoked token even before our expiry buffer
            # tripped — refresh once and retry before giving up.
            creds = _refresh_access_token(creds)
            raw = _fetch_usage(creds["accessToken"])

        five = raw.get("five_hour") or {}
        seven = raw.get("seven_day") or {}
        return {
            "five_hour": {"utilization": five.get("utilization", 0), "resets_at": five.get("resets_at")},
            "seven_day": {"utilization": seven.get("utilization", 0), "resets_at": seven.get("resets_at")},
        }

    def render(self, data: dict, stale: bool) -> Image.Image:
        canvas, draw = new_canvas()
        f_title = load_font(16)
        f_pct = load_font(30)
        f_small = load_font(13)

        if not data or "five_hour" not in data:
            draw_centered_text(draw, 120, 90, "Claude usage", f_title, fill=MUTED)
            draw_centered_text(draw, 120, 120, "not configured", load_font(16), fill=WARN)
            return canvas

        five = data["five_hour"]
        seven = data["seven_day"]

        draw_ring(draw, cx=68, cy=100, radius=42, pct=five.get("utilization", 0),
                  width=12, color=ACCENT)
        pct5_str = f"{round(five.get('utilization', 0))}%"
        w, h = text_size(draw, pct5_str, f_pct)
        draw.text((68 - w / 2, 100 - h / 2), pct5_str, font=f_pct, fill=FG)
        draw_centered_text(draw, 68, 150, "5-hour", f_title, fill=MUTED)
        draw_centered_text(draw, 68, 168, time_until(five.get("resets_at")), f_small, fill=MUTED)

        draw_ring(draw, cx=172, cy=100, radius=42, pct=seven.get("utilization", 0),
                  width=12, color=ACCENT)
        pct7_str = f"{round(seven.get('utilization', 0))}%"
        w, h = text_size(draw, pct7_str, f_pct)
        draw.text((172 - w / 2, 100 - h / 2), pct7_str, font=f_pct, fill=FG)
        draw_centered_text(draw, 172, 150, "7-day", f_title, fill=MUTED)
        draw_centered_text(draw, 172, 168, time_until(seven.get("resets_at")), f_small, fill=MUTED)

        draw_centered_text(draw, 120, 20, "CLAUDE USAGE", f_title, fill=MUTED)

        if stale:
            draw_stale_badge(draw)
        return canvas


MODULE = ClaudeUsageModule()
