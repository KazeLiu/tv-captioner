from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


_LLAMA_CACHE: dict[tuple[str, int, int], Any] = {}


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


def _llama(model_path: Path, n_ctx: int, n_gpu_layers: int) -> Any:
    key = (str(model_path), n_ctx, n_gpu_layers)
    if key in _LLAMA_CACHE:
        return _LLAMA_CACHE[key]

    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise TranslationRuntimeError(
            "缺少 llama-cpp-python，无法加载 GGUF 翻译模型。请先安装后再运行翻译测试。"
        ) from exc

    _LLAMA_CACHE[key] = Llama(
        model_path=str(model_path),
        n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers,
        verbose=False,
    )
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


def translate_segments(
    segments: list[dict[str, Any]],
    model_path: Path,
    source_language: str | None,
    target_language: str,
    update: Callable[..., None],
    n_ctx: int = 4096,
    n_gpu_layers: int = 0,
) -> list[dict[str, Any]]:
    if not target_language.strip():
        raise TranslationRuntimeError("请填写目标语言。")

    gguf_path = resolve_gguf_model_path(model_path)
    update(message=f"Loading translation model: {gguf_path.name}", progress=None)
    llm = _llama(gguf_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers)

    source = _language_label(source_language)
    translated_segments: list[dict[str, Any]] = []
    total = max(len(segments), 1)
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text") or "").strip()
        translated_text = ""
        if text:
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
                            f"Translate this subtitle from {source} to {target_language}:\n"
                            f"{text}"
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=256,
            )
            translated_text = _completion_text(result)

        translated_segments.append({**segment, "translation": translated_text})
        update(
            message="Translating subtitles",
            progress=min(0.98, index / total),
        )

    return translated_segments
