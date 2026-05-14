from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable


_LLAMA_CACHE: dict[tuple[str, int, int, int], Any] = {}
_LLAMA_RUNTIME: dict[tuple[str, int, int, int], dict[str, Any]] = {}
_LLAMA_CACHE_LOCK = threading.RLock()
_LLAMA_INFERENCE_LOCK = threading.RLock()


class TranslationRuntimeError(RuntimeError):
    pass


def resolve_gguf_model_path(path: Path) -> Path:
    if path.is_file():
        if path.suffix.lower() != ".gguf":
            raise TranslationRuntimeError("翻译模型需要 .gguf 文件。")
        return path

    gguf_files = sorted(item for item in path.glob("*.gguf") if item.is_file())
    if not gguf_files:
        raise TranslationRuntimeError("翻译模型目录里没有发现 .gguf 文件。")
    return gguf_files[0]


def gguf_runtime_status(n_gpu_layers: int, main_gpu: int) -> dict[str, Any]:
    supports_gpu = False
    available = False
    version = None
    try:
        import llama_cpp

        available = True
        version = getattr(llama_cpp, "__version__", None)
        supports_gpu = bool(getattr(llama_cpp, "llama_supports_gpu_offload", lambda: False)())
    except Exception:
        pass
    uses_gpu = available and supports_gpu and n_gpu_layers > 0
    return {
        "available": available,
        "version": version,
        "supportsGpuOffload": supports_gpu,
        "mode": "gpu" if uses_gpu else "cpu",
        "nGpuLayers": n_gpu_layers if uses_gpu else 0,
        "requestedNGpuLayers": n_gpu_layers,
        "translationGpuIndex": main_gpu if uses_gpu else None,
        "requestedTranslationGpuIndex": main_gpu,
        "fallback": False,
    }


def cached_gguf_runtime(
    model_path: Path,
    n_ctx: int,
    n_gpu_layers: int,
    main_gpu: int,
) -> dict[str, Any]:
    key = (str(model_path), n_ctx, n_gpu_layers, main_gpu)
    with _LLAMA_CACHE_LOCK:
        return dict(_LLAMA_RUNTIME.get(key) or gguf_runtime_status(n_gpu_layers, main_gpu))


def _llama(model_path: Path, n_ctx: int, n_gpu_layers: int, main_gpu: int) -> Any:
    key = (str(model_path), n_ctx, n_gpu_layers, main_gpu)
    with _LLAMA_CACHE_LOCK:
        if key in _LLAMA_CACHE:
            return _LLAMA_CACHE[key]

        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise TranslationRuntimeError(
                "缺少 llama-cpp-python，无法加载 GGUF 翻译模型。请先安装后再运行翻译测试。"
            ) from exc
        runtime = gguf_runtime_status(n_gpu_layers, main_gpu)
        effective_gpu_layers = runtime["nGpuLayers"]

        try:
            _LLAMA_CACHE[key] = Llama(
                model_path=str(model_path),
                n_ctx=n_ctx,
                n_gpu_layers=effective_gpu_layers,
                main_gpu=main_gpu,
                verbose=False,
            )
        except Exception:
            if effective_gpu_layers <= 0:
                raise
            _LLAMA_CACHE[key] = Llama(
                model_path=str(model_path),
                n_ctx=n_ctx,
                n_gpu_layers=0,
                main_gpu=main_gpu,
                verbose=False,
            )
            runtime = {
                **runtime,
                "mode": "cpu",
                "nGpuLayers": 0,
                "translationGpuIndex": None,
                "fallback": True,
            }
        _LLAMA_RUNTIME[key] = runtime
        return _LLAMA_CACHE[key]


def _language_label(language: str | None) -> str:
    if not language or language.lower() == "auto":
        return "the detected source language"
    labels = {
        "zh": "Chinese",
        "en": "English",
        "ja": "Japanese",
        "ko": "Korean",
        "ar": "Arabic",
    }
    return labels.get(language.lower(), language)


def _completion_text(result: dict[str, Any]) -> str:
    choices = result.get("choices") or []
    if not choices:
        return ""
    choice = choices[0]
    message = choice.get("message") or {}
    return str(message.get("content") or choice.get("text") or "").strip()


def _trim_context(context: str, limit: int) -> str:
    text = " ".join(context.split())
    if len(text) <= limit:
        return text
    return text[-limit:]


def _append_context(context: str, source_text: str, translated_text: str, limit: int) -> str:
    item = f"Source: {source_text}\nTranslation: {translated_text}".strip()
    return _trim_context(f"{context}\n{item}".strip(), limit)


def translate_segments(
    segments: list[dict[str, Any]],
    model_path: Path,
    source_language: str | None,
    target_language: str,
    update: Callable[..., None],
    n_ctx: int = 4096,
    n_gpu_layers: int = 0,
    main_gpu: int = 0,
    previous_context: str = "",
    context_window_chars: int = 800,
) -> list[dict[str, Any]]:
    if not target_language.strip():
        raise TranslationRuntimeError("请填写目标语言。")

    gguf_path = resolve_gguf_model_path(model_path)
    update(message=f"Loading translation model: {gguf_path.name}", progress=None)
    llm = _llama(gguf_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, main_gpu=main_gpu)

    source = _language_label(source_language)
    rolling_context = _trim_context(previous_context, context_window_chars)
    translated_segments: list[dict[str, Any]] = []
    total = max(len(segments), 1)
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text") or "").strip()
        translated_text = ""
        if text:
            context_block = (
                f"Previous subtitle context for continuity:\n{rolling_context}\n\n"
                if rolling_context
                else ""
            )
            with _LLAMA_INFERENCE_LOCK:
                result = llm.create_chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a subtitle translator. Translate faithfully and naturally. "
                                "Keep names, numbers, and punctuation sensible. Return only the translation."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"{context_block}"
                                f"Translate this subtitle from {source} to {target_language}:\n"
                                f"{text}"
                            ),
                        },
                    ],
                    temperature=0.1,
                    max_tokens=256,
                )
            translated_text = _completion_text(result)
            rolling_context = _append_context(
                rolling_context,
                source_text=text,
                translated_text=translated_text,
                limit=context_window_chars,
            )

        translated_segments.append({**segment, "translation": translated_text})
        update(
            message="Translating subtitles",
            progress=min(0.98, index / total),
        )

    return translated_segments
