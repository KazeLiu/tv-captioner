from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .catalog import DATA_DIR


LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "events.jsonl"
VALID_LEVELS = {"info", "warning", "error"}
RETENTION_DAYS = 10
CLEANUP_INTERVAL_SECONDS = 60 * 60
_lock = threading.RLock()
_last_cleanup_at = 0.0


def log_event(
    level: str,
    message: str,
    category: str = "system",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_level = level.lower().strip()
    if normalized_level == "waring":
        normalized_level = "warning"
    if normalized_level not in VALID_LEVELS:
        normalized_level = "info"

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": normalized_level,
        "category": category,
        "message": message,
        "details": details or {},
    }

    with _lock:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _cleanup_old_events_locked()
        with LOG_FILE.open("a", encoding="utf-8") as output:
            output.write(json.dumps(event, ensure_ascii=False) + "\n")

    return event


def list_events(level: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    normalized_level = (level or "").lower().strip()
    if normalized_level == "waring":
        normalized_level = "warning"
    if normalized_level and normalized_level not in VALID_LEVELS:
        normalized_level = ""

    safe_limit = max(1, min(limit, 1000))
    if not LOG_FILE.exists():
        return []

    events: deque[dict[str, Any]] = deque(maxlen=safe_limit)
    with _lock:
        _cleanup_old_events_locked()
        for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if normalized_level and event.get("level") != normalized_level:
                continue
            events.append(event)

    return list(reversed(events))


def _cleanup_old_events_locked() -> None:
    global _last_cleanup_at

    now = datetime.now(timezone.utc)
    if (now.timestamp() - _last_cleanup_at) < CLEANUP_INTERVAL_SECONDS:
        return
    _last_cleanup_at = now.timestamp()

    if not LOG_FILE.exists():
        return

    cutoff = now - timedelta(days=RETENTION_DAYS)
    kept_lines: list[str] = []
    changed = False
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            changed = True
            continue
        try:
            event = json.loads(line)
            timestamp = _parse_timestamp(event.get("timestamp"))
        except (json.JSONDecodeError, TypeError, ValueError):
            kept_lines.append(line)
            continue

        if timestamp is not None and timestamp < cutoff:
            changed = True
            continue
        kept_lines.append(line)

    if changed:
        LOG_FILE.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)
