from __future__ import annotations

import json
from typing import Any

from .catalog import DATA_DIR


LIVE_DEFAULTS_PATH = DATA_DIR / "live_defaults.json"

DEFAULT_LIVE_SETTINGS: dict[str, Any] = {
    "device": "auto",
    "deviceIndex": 0,
    "computeType": "auto",
    "nGpuLayers": 0,
    "translationGpuIndex": 0,
}


def load_live_defaults() -> dict[str, Any]:
    if not LIVE_DEFAULTS_PATH.exists():
        return dict(DEFAULT_LIVE_SETTINGS)
    try:
        payload = json.loads(LIVE_DEFAULTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_LIVE_SETTINGS)
    return {**DEFAULT_LIVE_SETTINGS, **{key: payload.get(key) for key in DEFAULT_LIVE_SETTINGS}}


def save_live_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    LIVE_DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings = {**DEFAULT_LIVE_SETTINGS, **{key: payload.get(key) for key in DEFAULT_LIVE_SETTINGS}}
    LIVE_DEFAULTS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings
