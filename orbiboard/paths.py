"""Central path constants shared by every module and script."""
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CONFIG_FILE = os.path.join(REPO_ROOT, "config", "modules.yaml")
CONFIG_EXAMPLE_FILE = os.path.join(REPO_ROOT, "config", "modules.example.yaml")
ASSETS_DIR = os.path.join(REPO_ROOT, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
ICON_DIR = os.path.join(ASSETS_DIR, "icons")
STATE_DIR = os.path.join(REPO_ROOT, "state")

# Frame handoff directory between module workers and the display server.
# On the Pi this is a systemd RuntimeDirectory (tmpfs, auto-created at
# /run/orbiboard). On a dev machine without systemd it falls back to a local
# folder under state/ so scripts/sim_preview.py works unmodified.
FRAME_DIR = os.environ.get("ORBIBOARD_FRAME_DIR") or (
    "/run/orbiboard/frames" if os.path.isdir("/run") and os.access("/run", os.W_OK)
    else os.path.join(STATE_DIR, "frames")
)


def ensure_state_dirs():
    os.makedirs(STATE_DIR, exist_ok=True)
    os.makedirs(FRAME_DIR, exist_ok=True)
