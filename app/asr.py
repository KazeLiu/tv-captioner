from __future__ import annotations

import ctypes
import json
import math
import sys
import threading
from pathlib import Path
from typing import Any, Callable

import ctranslate2
import numpy as np
from faster_whisper import WhisperModel

from .logs import log_event


_MODEL_CACHE: dict[tuple[str, str, str, int], WhisperModel] = {}
_MODEL_CACHE_LOCK = threading.RLock()
_WINDOWS_CUDA_RUNTIME_DLLS = ("cublas64_12.dll",)
CUDA_DOWNLOAD_URL = "https://developer.nvidia.com/cuda-12-6-3-download-archive?target_arch=x86_64&target_os=Windows&target_type=exe_local&target_version=10"


def _missing_windows_cuda_dlls() -> list[str]:
    if sys.platform != "win32":
        return []

    missing: list[str] = []
    for dll_name in _WINDOWS_CUDA_RUNTIME_DLLS:
        try:
            ctypes.WinDLL(dll_name)
        except OSError:
            missing.append(dll_name)
    return missing


def _cuda_unavailable_reason() -> str | None:
    try:
        cuda_devices = ctranslate2.get_cuda_device_count()
    except Exception as exc:  # noqa: BLE001 - CTranslate2 reports runtime issues with broad exceptions
        return str(exc)

    if cuda_devices <= 0:
        return "No CUDA device was detected."

    try:
        ctranslate2.get_supported_compute_types("cuda")
    except Exception as exc:  # noqa: BLE001 - CTranslate2 reports runtime issues with broad exceptions
        missing_dlls = _missing_windows_cuda_dlls()
        if missing_dlls:
            return f"Missing CUDA runtime DLL(s): {', '.join(missing_dlls)}. {exc}"
        return str(exc)

    return None


def _cuda_supported_compute_types() -> tuple[list[str], str]:
    try:
        return sorted(ctranslate2.get_supported_compute_types("cuda")), ""
    except Exception as exc:  # noqa: BLE001 - CTranslate2 reports runtime issues with broad exceptions
        return [], str(exc)


def _cuda_missing_dlls_if_unavailable(available: bool) -> list[str]:
    if available:
        return []
    missing_dlls = _missing_windows_cuda_dlls()
    return missing_dlls


def asr_cuda_status() -> dict[str, Any]:
    try:
        cuda_device_count = ctranslate2.get_cuda_device_count()
    except Exception as exc:  # noqa: BLE001 - CTranslate2 reports runtime issues with broad exceptions
        return {
            "available": False,
            "deviceCount": 0,
            "supportedComputeTypes": [],
            "missingDlls": _missing_windows_cuda_dlls(),
            "detail": str(exc),
            "downloadUrl": CUDA_DOWNLOAD_URL,
        }

    supported_compute_types, cuda_error = (
        _cuda_supported_compute_types() if cuda_device_count > 0 else ([], "")
    )
    available = cuda_device_count > 0 and not cuda_error
    missing_dlls = _cuda_missing_dlls_if_unavailable(available)

    if cuda_device_count <= 0:
        detail = "未检测到可用的 NVIDIA CUDA GPU；转写会使用 CPU。"
    elif not available:
        if missing_dlls:
            detail = (
                f"检测到 {cuda_device_count} 个 CUDA GPU，但缺少 CUDA 12 运行库："
                f"{', '.join(missing_dlls)}；转写会使用 CPU。"
            )
        else:
            detail = f"检测到 {cuda_device_count} 个 CUDA GPU，但 CUDA 运行库不可用：{cuda_error}；转写会使用 CPU。"
    else:
        compute_type_detail = ", ".join(supported_compute_types) if supported_compute_types else "auto"
        detail = f"转写 CUDA 运行库已可用；检测到 {cuda_device_count} 个 CUDA GPU；支持计算类型：{compute_type_detail}。"

    return {
        "available": available,
        "deviceCount": cuda_device_count,
        "supportedComputeTypes": supported_compute_types,
        "missingDlls": missing_dlls,
        "detail": detail,
        "downloadUrl": CUDA_DOWNLOAD_URL,
    }


def _resolve_asr_device(device: str) -> str:
    requested = (device or "auto").strip().lower()
    if requested != "auto":
        return requested

    return "cpu" if _cuda_unavailable_reason() else "cuda"


def _is_cuda_runtime_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(token in message for token in ("cublas", "cudnn", "cuda"))


def _load_cpu_model(model_path: Path, compute_type: str, device_index: int) -> WhisperModel:
    cpu_key = (str(model_path), "cpu", compute_type, device_index)
    if cpu_key not in _MODEL_CACHE:
        _MODEL_CACHE[cpu_key] = WhisperModel(
            str(model_path),
            device="cpu",
            device_index=device_index,
            compute_type=compute_type,
        )
    return _MODEL_CACHE[cpu_key]


def asr_runtime_status(device: str, device_index: int, compute_type: str) -> dict[str, Any]:
    requested_device = (device or "auto").strip().lower()
    resolved_device = _resolve_asr_device(requested_device)
    mode = "gpu" if resolved_device == "cuda" else "cpu"
    return {
        "mode": mode,
        "requestedDevice": requested_device,
        "device": resolved_device,
        "deviceIndex": device_index if mode == "gpu" else None,
        "computeType": compute_type,
    }


def clear_asr_model_cache() -> int:
    with _MODEL_CACHE_LOCK:
        count = len(_MODEL_CACHE)
        _MODEL_CACHE.clear()
        return count


def _model(model_path: Path, device: str, compute_type: str, device_index: int) -> tuple[WhisperModel, str]:
    requested_device = (device or "auto").strip().lower()
    resolved_device = _resolve_asr_device(device)
    key = (str(model_path), resolved_device, compute_type, device_index)
    with _MODEL_CACHE_LOCK:
        if key not in _MODEL_CACHE:
            try:
                _MODEL_CACHE[key] = WhisperModel(
                    str(model_path),
                    device=resolved_device,
                    device_index=device_index,
                    compute_type=compute_type,
                )
            except Exception as exc:
                if resolved_device == "cuda" and _is_cuda_runtime_error(exc):
                    log_event(
                        "warning",
                        "ASR CUDA 加载失败，已退回 CPU",
                        category="asr",
                        details={
                            "requestedDevice": requested_device,
                            "deviceIndex": device_index,
                            "computeType": compute_type,
                            "error": str(exc),
                            "hint": (
                                "如需转写 CUDA 加速，请安装 CUDA 12 运行库，"
                                "或把 GGUF CUDA DLC 放到后端目录。"
                            ),
                        },
                    )
                    return _load_cpu_model(model_path, compute_type, device_index), "cpu"
                raise
        return _MODEL_CACHE[key], resolved_device


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


def _transcribe(
    audio: str | Path | np.ndarray,
    model_path: Path,
    language: str | None,
    device: str,
    device_index: int,
    compute_type: str,
    update: Callable[..., None],
    initial_prompt: str | None = None,
    beam_size: int = 5,
    vad_filter: bool = True,
    condition_on_previous_text: bool = True,
) -> dict[str, Any]:
    update(message="Loading ASR model", progress=0.01)
    whisper, runtime_device = _model(
        model_path,
        device=device,
        device_index=device_index,
        compute_type=compute_type,
    )

    kwargs: dict[str, Any] = {
        "beam_size": beam_size,
        "vad_filter": vad_filter,
        "word_timestamps": False,
        "condition_on_previous_text": condition_on_previous_text,
    }
    if language:
        kwargs["language"] = language
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt

    update(message="Transcribing media", progress=0.05)
    segments_iter, info = whisper.transcribe(str(audio) if isinstance(audio, Path) else audio, **kwargs)

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
        "runtime": {
            **asr_runtime_status(device, device_index, compute_type),
            "mode": "gpu" if runtime_device == "cuda" else "cpu",
            "device": runtime_device,
            "deviceIndex": device_index if runtime_device == "cuda" else None,
        },
    }


def transcribe_media(
    media_path: Path,
    model_path: Path,
    language: str | None,
    device: str,
    device_index: int,
    compute_type: str,
    update: Callable[..., None],
) -> dict[str, Any]:
    return _transcribe(
        audio=media_path,
        model_path=model_path,
        language=language,
        device=device,
        device_index=device_index,
        compute_type=compute_type,
        update=update,
    )


def transcribe_audio_array(
    audio: np.ndarray,
    model_path: Path,
    language: str | None,
    device: str,
    device_index: int,
    compute_type: str,
    update: Callable[..., None],
    initial_prompt: str | None = None,
    beam_size: int = 5,
    vad_filter: bool = True,
    condition_on_previous_text: bool = True,
) -> dict[str, Any]:
    return _transcribe(
        audio=audio,
        model_path=model_path,
        language=language,
        device=device,
        device_index=device_index,
        compute_type=compute_type,
        update=update,
        initial_prompt=initial_prompt,
        beam_size=beam_size,
        vad_filter=vad_filter,
        condition_on_previous_text=condition_on_previous_text,
    )
