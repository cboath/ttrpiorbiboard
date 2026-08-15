"""Bambu Lab 3D printer status — local LAN MQTT or Bambu Cloud MQTT.

Fetch logic adapted from
~/Development/Waveshare-ePaper-10.85-dashboard/main.py (update_data_thread's
ENABLE_BAMBU branch) and the vendored bambulabs_api client at
~/Development/Waveshare-ePaper-10.85-dashboard/lib/bambulabs_api/. Unlike the
request/response modules (weather, claude_usage), bambulabs_api's MQTT client
keeps a persistent connection and updates its internal state from a
background thread — get_printer_state()/get_last_print_percentage()/etc.
read whatever the printer last pushed rather than making a fresh network
call. So the connection is opened once and kept on this Module instance
(run_module_forever only ever constructs one instance per process) and
fetch() just reads the latest cached values each cycle, reconnecting if the
link drops.

Two connection modes, picked via `params.mode`:

- "lan" (default): connects directly to the printer's own MQTT broker using
  its IP + access code (Settings > Network on the printer's screen) and
  serial (Settings > Device). No internet required, but the printer must
  have LAN-only mode enabled.
- "cloud": connects to Bambu's cloud MQTT broker under your Bambu Cloud
  account instead, so LAN-only mode never has to be turned on. Requires
  running scripts/bambu_cloud_auth_setup.py once to log in (email/password,
  plus — for most accounts — a one-time emailed verification code) and
  cache a token in state/bambu_cloud_creds.json; this module only ever
  refreshes that token afterwards, same pattern as claude_usage's OAuth.

Both modes go through bambulabs_api's lower-level PrinterMQTTClient directly
(not the Printer wrapper, which only knows how to build LAN connections and
also drags in FTP/camera clients we don't use here).

Two caveats worth knowing about cloud mode:
1. Bambu publishes no public docs for its cloud login API. The endpoints
   below match what several independent open-source Bambu integrations
   reverse-engineered as of when this was written; Bambu can change them
   without notice.
2. bambulabs_api's MQTT client disables TLS certificate verification
   unconditionally (it was built for the printer's self-signed LAN cert).
   That carries over to the cloud broker connection too — a real, if
   narrow, MITM exposure over the open internet. Acceptable for a hobby
   dashboard; not something this module can fix without reimplementing the
   MQTT transport itself.
"""
import base64
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

# --- Cloud mode: login/token handling -----------------------------------
CLOUD_API_BASE = "https://api.bambulab.com"
CLOUD_LOGIN_URL = f"{CLOUD_API_BASE}/v1/user-service/user/login"
CLOUD_CODE_URL = f"{CLOUD_API_BASE}/v1/user-service/user/sendemail/code"
CLOUD_REFRESH_URL = f"{CLOUD_API_BASE}/v1/user-service/user/refreshtoken"
CLOUD_MQTT_HOSTS = {"us": "us.mqtt.bambulab.com", "cn": "cn.mqtt.bambulab.com"}
CLOUD_CREDENTIALS_FILE = os.path.join(STATE_DIR, "bambu_cloud_creds.json")
CLOUD_REFRESH_BUFFER_SEC = 300


def _jwt_username(token):
    """Pull the 'username' claim (e.g. "u_1234567") out of a cloud access
    token without verifying its signature — we just received it from Bambu's
    own login response, so there's nothing to verify against."""
    try:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return payload.get("username")
    except Exception:
        return None


def _load_cloud_credentials():
    if not os.path.exists(CLOUD_CREDENTIALS_FILE):
        return None
    try:
        with open(CLOUD_CREDENTIALS_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_cloud_credentials(creds):
    tmp = CLOUD_CREDENTIALS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(creds, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CLOUD_CREDENTIALS_FILE)


def _cloud_token_expired(creds):
    expires_at = creds.get("expiresAt", 0)
    now_ms = int(time.time() * 1000)
    return now_ms >= (expires_at - CLOUD_REFRESH_BUFFER_SEC * 1000)


def _refresh_cloud_token(creds):
    refresh_token = creds.get("refreshToken")
    if not refresh_token:
        raise RuntimeError(
            "bambu_printer cloud: no refresh token cached — rerun "
            "scripts/bambu_cloud_auth_setup.py"
        )
    resp = net.post_json(CLOUD_REFRESH_URL, json_body={"refreshToken": refresh_token})
    if resp is None or resp.status_code != 200:
        raise RuntimeError(
            f"bambu_printer cloud: token refresh failed "
            f"({getattr(resp, 'status_code', 'no response')})"
        )
    data = resp.json()
    access_token = data.get("accessToken")
    if not access_token:
        raise RuntimeError("bambu_printer cloud: refresh response missing accessToken")

    creds["accessToken"] = access_token
    if data.get("refreshToken"):
        creds["refreshToken"] = data["refreshToken"]
    creds["expiresAt"] = int(time.time() * 1000) + data.get("expiresIn", 3600) * 1000
    username = _jwt_username(access_token)
    if username:
        creds["username"] = username
    _save_cloud_credentials(creds)
    return creds


def _cloud_connection_info(params: dict):
    creds = _load_cloud_credentials()
    if not creds:
        raise RuntimeError(
            "bambu_printer cloud mode: no cached credentials — run "
            "scripts/bambu_cloud_auth_setup.py once"
        )
    if _cloud_token_expired(creds):
        creds = _refresh_cloud_token(creds)

    username = creds.get("username") or _jwt_username(creds.get("accessToken", ""))
    if not username:
        raise RuntimeError("bambu_printer cloud: could not determine cloud MQTT username from token")

    region = params.get("region", "us")
    host = CLOUD_MQTT_HOSTS.get(region)
    if not host:
        raise RuntimeError(f"bambu_printer cloud: unknown region '{region}' (expected 'us' or 'cn')")

    return host, username, creds["accessToken"]


class BambuPrinterModule(Module):
    MODULE_ID = "bambu_printer"
    DEFAULT_INTERVAL_SEC = 30  # print progress moves faster than weather/usage

    def __init__(self):
        self._client = None

    def _ensure_connected(self, params: dict):
        if bl is None:
            raise RuntimeError("bambulabs_api not installed — pip install bambulabs-api")

        serial = params.get("serial")
        if not serial:
            raise RuntimeError("bambu_printer needs 'serial' in params")

        mode = params.get("mode", "lan")
        if mode == "lan":
            ip = params.get("ip")
            access_code = params.get("access_code")
            if not (ip and access_code):
                raise RuntimeError(
                    "bambu_printer (mode: lan) needs 'ip' and 'access_code' in params "
                    "(see printer Settings > Network)"
                )
            host, username, access = ip, "bblp", access_code
        elif mode == "cloud":
            host, username, access = _cloud_connection_info(params)
        else:
            raise RuntimeError(f"bambu_printer: unknown mode '{mode}' (expected 'lan' or 'cloud')")

        if self._client is not None and self._client.is_connected():
            return

        if self._client is not None:
            try:
                self._client.stop()
            except Exception:
                pass

        self._client = bl.PrinterMQTTClient(
            hostname=host, access=access, printer_serial=serial, username=username,
        )
        self._client.connect()
        self._client.start()
        time.sleep(CONNECT_SETTLE_SEC)

    def fetch(self, params: dict) -> dict:
        self._ensure_connected(params)
        client = self._client

        if not client.is_connected():
            raise RuntimeError("bambu_printer: MQTT not connected")

        state = str(client.get_printer_state())
        if state == "UNKNOWN":
            raise RuntimeError("bambu_printer: no data pushed by printer yet")

        pct = client.get_last_print_percentage()
        remaining = client.get_remaining_time()
        return {
            "state": state,
            "percent": pct if isinstance(pct, (int, float)) else None,
            "remaining_min": remaining if isinstance(remaining, (int, float)) else None,
            "bed_temp": client.get_bed_temperature(),
            "nozzle_temp": client.get_nozzle_temperature(),
            "layer_cur": client.current_layer_num(),
            "layer_total": client.total_layer_num(),
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
