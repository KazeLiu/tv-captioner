from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

from faster_whisper import WhisperModel


_MODEL_CACHE: dict[tuple[str, str, str], WhisperModel] = {}


def _model(model_path: Path, device: str, compute_type: str) -> WhisperModel:
    key = (str(model_path), device, compute_type)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = WhisperModel(str(model_path), device=device, compute_type=compute_type)
    return _MODEL_CACHE[key]


def format_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000.0))
    hours = millis // 3_600_000
    millis %= 3_600_000
    minutes = millis // 60_000
    millis %= 60_000
    secs = millis // 1000
    millis %= 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_srt(segments: list[dict[str, Any]], output_path: Path, text_key: str) -> None:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = (segment.get(text_key) or segment.get("text") or "").strip()
        if not text:
            continue
        lines.append(str(index))
        lines.append(f"{format_timestamp(segment['start'])} --> {format_timestamp(segment['end'])}")
        lines.append(text)
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_bilingual_srt(segments: list[dict[str, Any]], output_path: Path) -> None:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        source_text = (segment.get("text") or "").strip()
        translated_text = (segment.get("translation") or "").strip()
        if not source_text and not translated_text:
            continue
        lines.append(str(index))
        lines.append(f"{format_timestamp(segment['start'])} --> {format_timestamp(segment['end'])}")
        if translated_text:
            lines.append(translated_text)
        if source_text:
            lines.append(source_text)
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_json(payload: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def transcribe_media(
    media_path: Path,
    model_path: Path,
    language: str | None,
    device: str,
    compute_type: str,
    update: Callable[..., None],
) -> dict[str, Any]:
    update(message="Loading ASR model", progress=None)
    whisper = _model(model_path, device=device, compute_type=compute_type)

    kwargs: dict[str, Any] = {
        "beam_size": 5,
        "vad_filter": True,
        "word_timestamps": False,
    }
    if language:
        kwargs["language"] = language

    update(message="Transcribing media", progress=0.05)
    segments_iter, info = whisper.transcribe(str(media_path), **kwargs)

    duration = info.duration or 0
    segments: list[dict[str, Any]] = []
    for segment in segments_iter:
        segments.append(
            {
                "id": segment.id,
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text.strip(),
            }
        )
        if duration and math.isfinite(duration):
            update(progress=min(0.95, max(0.05, segment.end / duration)), message="Transcribing media")

    return {
        "language": info.language,
        "languageProbability": info.language_probability,
        "duration": duration,
        "segments": segments,
    }
