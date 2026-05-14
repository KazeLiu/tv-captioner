from __future__ import annotations

import json
from typing import Any

from .catalog import DATA_DIR


TRANSLATION_SETTINGS_PATH = DATA_DIR / "translation_settings.json"
ONLINE_PROVIDERS = {"deepseek", "deeplx"}
ONLINE_PROVIDER = "deepseek"
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_API_URL = "https://api.deepseek.com"
DEFAULT_DEEPLX_API_URL = "https://api.deeplx.org"
DEFAULT_DEEPSEEK_PROMPT = (
    "You are a professional subtitle translator for TV programs. "
    "Translate the user's subtitle from {source_language} to {target_language}. "
    "Keep the meaning faithful, natural, concise, and suitable for on-screen subtitles. "
    "Preserve names, numbers, units, and speaker tone. "
    "Use previous subtitle context only for continuity. "
    "Return only the translated subtitle text, with no explanations."
)

DEFAULT_TRANSLATION_SETTINGS: dict[str, Any] = {
    "mode": "local",
    "onlineProvider": ONLINE_PROVIDER,
    "deepseek": {
        "apiUrl": DEFAULT_DEEPSEEK_API_URL,
        "apiKey": "",
        "model": DEEPSEEK_MODEL,
        "prompt": DEFAULT_DEEPSEEK_PROMPT,
    },
    "deeplx": {
        "apiUrl": DEFAULT_DEEPLX_API_URL,
        "apiKey": "",
    },
}


def _deep_merge(defaults: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in payload.items():
        if isinstance(value, dict) and isinstance(defaults.get(key), dict):
            merged[key] = _deep_merge(defaults[key], value)
        else:
            merged[key] = value
    return merged


def normalize_translation_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings = _deep_merge(DEFAULT_TRANSLATION_SETTINGS, payload)
    mode = str(settings.get("mode") or "local").strip().lower()
    if mode not in {"local", "online"}:
        mode = "local"
    online_provider = str(settings.get("onlineProvider") or ONLINE_PROVIDER).strip().lower()
    if online_provider not in ONLINE_PROVIDERS:
        online_provider = ONLINE_PROVIDER

    deepseek = settings.get("deepseek") if isinstance(settings.get("deepseek"), dict) else {}
    deeplx = settings.get("deeplx") if isinstance(settings.get("deeplx"), dict) else {}
    normalized = {
        "mode": mode,
        "onlineProvider": online_provider,
        "deepseek": {
            "apiUrl": str(deepseek.get("apiUrl") or DEFAULT_DEEPSEEK_API_URL).strip(),
            "apiKey": str(deepseek.get("apiKey") or "").strip(),
            "model": str(deepseek.get("model") or DEEPSEEK_MODEL).strip() or DEEPSEEK_MODEL,
            "prompt": str(deepseek.get("prompt") or DEFAULT_DEEPSEEK_PROMPT).strip()
            or DEFAULT_DEEPSEEK_PROMPT,
        },
        "deeplx": {
            "apiUrl": str(deeplx.get("apiUrl") or DEFAULT_DEEPLX_API_URL).strip(),
            "apiKey": str(deeplx.get("apiKey") or "").strip(),
        },
    }
    return normalized


def public_translation_settings(settings: dict[str, Any]) -> dict[str, Any]:
    deepseek = settings["deepseek"]
    deeplx = settings["deeplx"]
    return {
        **settings,
        "deepseek": {
            **deepseek,
            "apiKey": deepseek.get("apiKey") or "",
            "apiKeySet": bool(deepseek.get("apiKey")),
        },
        "deeplx": {
            **deeplx,
            "apiKey": deeplx.get("apiKey") or "",
            "apiKeySet": bool(deeplx.get("apiKey")),
        },
    }


def load_translation_settings() -> dict[str, Any]:
    if not TRANSLATION_SETTINGS_PATH.exists():
        return normalize_translation_settings({})
    try:
        payload = json.loads(TRANSLATION_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return normalize_translation_settings({})
    return normalize_translation_settings(payload if isinstance(payload, dict) else {})


def save_translation_settings(payload: dict[str, Any]) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings = normalize_translation_settings(payload)
    TRANSLATION_SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings
