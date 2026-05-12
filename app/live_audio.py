from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from .catalog import LIVE_AUDIO_DIR


def create_live_session(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = uuid.uuid4().hex
    session_dir = LIVE_AUDIO_DIR / session_id
    chunks_dir = session_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "id": session_id,
        "status": "open",
        "createdAt": time.time(),
        "updatedAt": time.time(),
        "chunkCount": 0,
        **payload,
    }
    _write_json(session_dir / "session.json", metadata)
    return metadata


def list_live_sessions() -> list[dict[str, Any]]:
    if not LIVE_AUDIO_DIR.exists():
        return []
    sessions = []
    for session_file in LIVE_AUDIO_DIR.glob("*/session.json"):
        sessions.append(_read_json(session_file))
    return sorted(sessions, key=lambda item: item.get("createdAt", 0), reverse=True)


def get_live_session(session_id: str) -> dict[str, Any] | None:
    session_file = LIVE_AUDIO_DIR / session_id / "session.json"
    if not session_file.exists():
        return None
    return _read_json(session_file)


def save_live_chunk(
    session_id: str,
    sequence: int,
    content: bytes,
    filename: str,
    content_type: str | None,
    start_ms: int | None,
    duration_ms: int | None,
) -> dict[str, Any]:
    session_dir = LIVE_AUDIO_DIR / session_id
    chunks_dir = session_dir / "chunks"
    session_file = session_dir / "session.json"
    if not session_file.exists():
        raise KeyError(session_id)

    suffix = Path(filename or "").suffix or ".bin"
    chunk_name = f"{sequence:08d}{suffix}"
    chunk_path = chunks_dir / chunk_name
    chunk_path.write_bytes(content)

    record = {
        "sequence": sequence,
        "filename": chunk_name,
        "originalFilename": filename,
        "contentType": content_type,
        "sizeBytes": len(content),
        "startMs": start_ms,
        "durationMs": duration_ms,
        "receivedAt": time.time(),
    }
    with (session_dir / "chunks.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")

    session = _read_json(session_file)
    session["chunkCount"] = int(session.get("chunkCount", 0)) + 1
    session["updatedAt"] = time.time()
    _write_json(session_file, session)
    return record


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
