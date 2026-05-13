from __future__ import annotations

from functools import lru_cache
from typing import Any


SIMPLIFIED_ALIASES = {"simplified", "simple", "hans", "zh-hans", "zh-cn", "cn", "s", "简体", "简体中文"}
TRADITIONAL_ALIASES = {"traditional", "hant", "zh-hant", "zh-tw", "zh-hk", "tw", "hk", "t", "繁体", "繁體", "繁体中文", "繁體中文"}
ORIGINAL_ALIASES = {"", "original", "none", "off", "raw", "keep", "保持", "原文"}


def normalize_chinese_script(script: str | None) -> str:
    value = (script or "simplified").strip().lower()
    if value in ORIGINAL_ALIASES:
        return "original"
    if value in TRADITIONAL_ALIASES:
        return "traditional"
    return "simplified"


def convert_chinese_text(text: str, script: str | None) -> str:
    target = normalize_chinese_script(script)
    if target == "original" or not text:
        return text

    converter = _converter("t2s" if target == "simplified" else "s2t")
    return converter.convert(text)


def convert_segment_texts(segments: list[dict[str, Any]], script: str | None) -> list[dict[str, Any]]:
    target = normalize_chinese_script(script)
    if target == "original":
        return segments

    converted: list[dict[str, Any]] = []
    for segment in segments:
        updated = {**segment}
        if "text" in updated:
            updated["text"] = convert_chinese_text(str(updated.get("text") or ""), target)
        if "translation" in updated:
            updated["translation"] = convert_chinese_text(str(updated.get("translation") or ""), target)
        converted.append(updated)
    return converted


@lru_cache(maxsize=2)
def _converter(config: str):
    try:
        from opencc import OpenCC
    except ImportError as exc:
        raise RuntimeError(
            "缺少 opencc-python-reimplemented，无法进行简繁转换。请重新安装依赖。"
        ) from exc

    return OpenCC(config)
