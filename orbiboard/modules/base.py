"""Module contract + the fetch/render/write loop shared by every module.

A module worker never touches SPI/GPIO — it only fetches data, renders a
Pillow frame, and atomically writes RGB565 bytes to its frame file under
orbiboard.paths.FRAME_DIR. orbiboard/display/server.py is the sole process
that pushes those bytes to hardware. This split is what lets modules crash
and restart independently (systemd Restart=on-failure per unit) without any
risk of corrupting the shared SPI bus.
"""
import json
import logging
import os
import time
from abc import ABC, abstractmethod

from PIL import Image

from orbiboard.paths import FRAME_DIR, STATE_DIR, ensure_state_dirs
from orbiboard.render_utils import pack_rgb565

log = logging.getLogger(__name__)


class Module(ABC):
    MODULE_ID: str = None
    DEFAULT_INTERVAL_SEC: int = 600

    @abstractmethod
    def fetch(self, params: dict) -> dict:
        """Fetch fresh data. Raise on any failure (network, auth, parse)."""

    @abstractmethod
    def render(self, data: dict, stale: bool) -> Image.Image:
        """Return a 240x240 RGB frame for the given data."""


def _state_path(module_id):
    return os.path.join(STATE_DIR, f"{module_id}_last.json")


def _load_last_good(module_id):
    path = _state_path(module_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_last_good(module_id, data):
    path = _state_path(module_id)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _write_frame(module_id, image: Image.Image):
    path = os.path.join(FRAME_DIR, f"{module_id}.bin")
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(pack_rgb565(image))
    os.replace(tmp, path)


def run_module_forever(module: Module, params: dict, interval_sec: int = None):
    ensure_state_dirs()
    interval = interval_sec or module.DEFAULT_INTERVAL_SEC
    module_id = module.MODULE_ID

    while True:
        stale = False
        try:
            data = module.fetch(params)
            _save_last_good(module_id, data)
        except Exception as e:
            log.warning("%s: fetch failed (%s), falling back to last-known-good", module_id, e)
            data = _load_last_good(module_id)
            stale = True
            if data is None:
                data = {}

        try:
            frame = module.render(data, stale)
            _write_frame(module_id, frame)
        except Exception:
            log.exception("%s: render failed, skipping this cycle", module_id)

        time.sleep(interval)
