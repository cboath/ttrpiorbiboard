"""Loads and validates config/modules.yaml."""
import os

import yaml

from orbiboard.paths import CONFIG_FILE, CONFIG_EXAMPLE_FILE


class ConfigError(RuntimeError):
    pass


def load_config(path=None):
    path = path or CONFIG_FILE
    if not os.path.exists(path):
        raise ConfigError(
            f"{path} not found. Copy config/modules.example.yaml to "
            f"config/modules.yaml and edit it for your wiring:\n"
            f"  cp {CONFIG_EXAMPLE_FILE} {path}"
        )
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}

    if "display_bus" not in cfg or "modules" not in cfg:
        raise ConfigError(f"{path} is missing 'display_bus' or 'modules' top-level keys")

    cs_pins_seen = {}
    for module_id, mod_cfg in cfg["modules"].items():
        if not mod_cfg.get("enabled"):
            continue
        cs_pin = mod_cfg.get("cs_pin")
        if cs_pin is None:
            raise ConfigError(f"module '{module_id}' is enabled but has no cs_pin")
        if cs_pin in cs_pins_seen:
            raise ConfigError(
                f"cs_pin {cs_pin} used by both '{cs_pins_seen[cs_pin]}' and "
                f"'{module_id}' — every enabled module needs a unique CS pin"
            )
        cs_pins_seen[cs_pin] = module_id

    return cfg


def enabled_modules(cfg):
    return {
        mid: mcfg for mid, mcfg in cfg["modules"].items()
        if mcfg.get("enabled")
    }
