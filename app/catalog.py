from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any


def app_root() -> Path:
    configured = os.environ.get("TV_CAPTIONER_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT_DIR = app_root()
MODEL_DIR = ROOT_DIR / "models"
ASR_MODEL_DIR = MODEL_DIR / "asr"
TRANSLATION_MODEL_DIR = MODEL_DIR / "translate"
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
LIVE_AUDIO_DIR = DATA_DIR / "live_audio"


ASR_MODELS = {
    "tiny": {
        "label": "Whisper tiny",
        "name_cn": "tiny（多语言，极小）",
        "repo_id": "Systran/faster-whisper-tiny",
        "url": "https://huggingface.co/Systran/faster-whisper-tiny",
        "description": "体积最小，速度最快，适合接口连通性测试；字幕质量不建议作为正式使用标准。",
    },
    "tiny.en": {
        "label": "Whisper tiny.en",
        "name_cn": "tiny.en（英语专用，极小）",
        "repo_id": "Systran/faster-whisper-tiny.en",
        "url": "https://huggingface.co/Systran/faster-whisper-tiny.en",
        "description": "英语专用极小模型，只适合英语节目；不适合日语、韩语、阿拉伯语。",
    },
    "base": {
        "label": "Whisper base",
        "name_cn": "base（多语言，基础）",
        "repo_id": "Systran/faster-whisper-base",
        "url": "https://huggingface.co/Systran/faster-whisper-base",
        "description": "比 tiny 稳一些，仍然很轻；适合低配置机器做快速验证。",
    },
    "base.en": {
        "label": "Whisper base.en",
        "name_cn": "base.en（英语专用，基础）",
        "repo_id": "Systran/faster-whisper-base.en",
        "url": "https://huggingface.co/Systran/faster-whisper-base.en",
        "description": "英语专用基础模型，只适合英语节目；比 tiny.en 稳一些。",
    },
    "small": {
        "label": "Whisper small",
        "name_cn": "small（多语言，小型）",
        "repo_id": "Systran/faster-whisper-small",
        "url": "https://huggingface.co/Systran/faster-whisper-small",
        "description": "速度和质量比较均衡，适合先测试日语、韩语、英语链路。",
    },
    "small.en": {
        "label": "Whisper small.en",
        "name_cn": "small.en（英语专用，小型）",
        "repo_id": "Systran/faster-whisper-small.en",
        "url": "https://huggingface.co/Systran/faster-whisper-small.en",
        "description": "英语专用小型模型，只适合英语节目；英语识别可作为轻量选择。",
    },
    "medium": {
        "label": "Whisper medium",
        "name_cn": "medium（多语言，中型）",
        "repo_id": "Systran/faster-whisper-medium",
        "url": "https://huggingface.co/Systran/faster-whisper-medium",
        "description": "质量明显好于 small，资源占用低于 large；适合正式使用前的折中选择。",
    },
    "medium.en": {
        "label": "Whisper medium.en",
        "name_cn": "medium.en（英语专用，中型）",
        "repo_id": "Systran/faster-whisper-medium.en",
        "url": "https://huggingface.co/Systran/faster-whisper-medium.en",
        "description": "英语专用中型模型，只适合英语节目；英语质量和速度较均衡。",
    },
    "large-v1": {
        "label": "Whisper large-v1",
        "name_cn": "large-v1（大型一代）",
        "repo_id": "Systran/faster-whisper-large-v1",
        "url": "https://huggingface.co/Systran/faster-whisper-large-v1",
        "description": "早期 large 模型，通常不作为首选；保留用于对比兼容性和效果。",
    },
    "large-v2": {
        "label": "Whisper large-v2",
        "name_cn": "large-v2（推荐基线）",
        "repo_id": "Systran/faster-whisper-large-v2",
        "url": "https://huggingface.co/Systran/faster-whisper-large-v2",
        "description": "推荐优先测试，适合作为日语、韩语、阿语、英语电视台的质量基线。",
    },
    "large-v3": {
        "label": "Whisper large-v3",
        "name_cn": "large-v3（大型三代）",
        "repo_id": "Systran/faster-whisper-large-v3",
        "url": "https://huggingface.co/Systran/faster-whisper-large-v3",
        "description": "更新的高质量模型，适合和 large-v2 对比；不同语言和节目类型可能各有胜负。",
    },
    "large-v3-turbo": {
        "label": "Whisper large-v3-turbo",
        "name_cn": "large-v3-turbo（高速版）",
        "repo_id": "deepdml/faster-whisper-large-v3-turbo-ct2",
        "url": "https://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2",
        "description": "偏实时和速度的 CT2 转换版本，质量通常低于完整 large-v3，但延迟更友好，适合后续直播字幕测试。",
    },
    "distil-small.en": {
        "label": "Distil-Whisper small.en",
        "name_cn": "distil-small.en（英语专用，蒸馏小型）",
        "repo_id": "Systran/faster-distil-whisper-small.en",
        "url": "https://huggingface.co/Systran/faster-distil-whisper-small.en",
        "description": "英语专用蒸馏模型，速度更友好；不适合日语、韩语、阿拉伯语。",
    },
    "distil-medium.en": {
        "label": "Distil-Whisper medium.en",
        "name_cn": "distil-medium.en（英语专用，蒸馏中型）",
        "repo_id": "Systran/faster-distil-whisper-medium.en",
        "url": "https://huggingface.co/Systran/faster-distil-whisper-medium.en",
        "description": "英语专用蒸馏中型模型，适合只看英语台时测试速度和质量。",
    },
    "distil-large-v2": {
        "label": "Distil-Whisper large-v2",
        "name_cn": "distil-large-v2（蒸馏大型二代）",
        "repo_id": "Systran/faster-distil-whisper-large-v2",
        "url": "https://huggingface.co/Systran/faster-distil-whisper-large-v2",
        "description": "蒸馏版 large-v2，偏速度；可用于和完整 large-v2 对比。",
    },
    "distil-large-v3": {
        "label": "Distil-Whisper large-v3",
        "name_cn": "distil-large-v3（蒸馏大型三代）",
        "repo_id": "Systran/faster-distil-whisper-large-v3",
        "url": "https://huggingface.co/Systran/faster-distil-whisper-large-v3",
        "description": "蒸馏版 large-v3，速度更友好；适合后续实时字幕延迟测试。",
    },
}


TRANSLATION_MODELS = {
    "qwen2.5-0.5b-instruct-gguf": {
        "label": "Qwen2.5 0.5B Instruct GGUF",
        "name_cn": "Qwen2.5 0.5B（极轻测试）",
        "repo_id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "description": "体积最小，适合测试翻译链路是否打通；正式字幕质量通常不够。",
    },
    "qwen2.5-1.5b-instruct-gguf": {
        "label": "Qwen2.5 1.5B Instruct GGUF",
        "name_cn": "Qwen2.5 1.5B（轻量）",
        "repo_id": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "description": "轻量翻译模型，适合低配置机器先跑通流程；复杂句子和专名可能一般。",
    },
    "qwen2.5-3b-instruct-gguf": {
        "label": "Qwen2.5 3B Instruct GGUF",
        "name_cn": "Qwen2.5 3B（推荐入门）",
        "repo_id": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF",
        "description": "推荐优先测试。速度、体积、翻译质量比较均衡。",
    },
    "qwen2.5-7b-instruct-gguf": {
        "label": "Qwen2.5 7B Instruct GGUF",
        "name_cn": "Qwen2.5 7B（质量基线）",
        "repo_id": "Qwen/Qwen2.5-7B-Instruct-GGUF",
        "url": "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF",
        "description": "中文能力和翻译自然度更好，适合作为字幕翻译质量基线；需要更多内存/显存。",
    },
    "qwen2.5-14b-instruct-gguf": {
        "label": "Qwen2.5 14B Instruct GGUF",
        "name_cn": "Qwen2.5 14B（高质量）",
        "repo_id": "Qwen/Qwen2.5-14B-Instruct-GGUF",
        "url": "https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-GGUF",
        "description": "翻译质量更好，但资源占用明显增加；适合性能较强的 Windows 主机。",
    },
    "qwen3-4b-gguf": {
        "label": "Qwen3 4B GGUF",
        "name_cn": "Qwen3 4B（新一代轻量）",
        "repo_id": "Qwen/Qwen3-4B-GGUF",
        "url": "https://huggingface.co/Qwen/Qwen3-4B-GGUF",
        "description": "Qwen3 轻量模型，适合测试新一代模型的翻译表现和延迟。",
    },
    "qwen3-8b-gguf": {
        "label": "Qwen3 8B GGUF",
        "name_cn": "Qwen3 8B（新一代质量基线）",
        "repo_id": "Qwen/Qwen3-8B-GGUF",
        "url": "https://huggingface.co/Qwen/Qwen3-8B-GGUF",
        "description": "Qwen3 系列中较适合做字幕翻译质量测试的体量，资源占用高于 4B。",
    },
}


def ensure_dirs() -> None:
    for path in (ASR_MODEL_DIR, TRANSLATION_MODEL_DIR, UPLOAD_DIR, OUTPUT_DIR, LIVE_AUDIO_DIR):
        path.mkdir(parents=True, exist_ok=True)


def asr_model_path(model_key: str) -> Path:
    if model_key not in ASR_MODELS:
        raise KeyError(model_key)
    return ASR_MODEL_DIR / ASR_MODELS[model_key]["repo_id"].rsplit("/", 1)[-1]


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def _is_asr_model_dir_ready(path: Path) -> bool:
    return path.exists() and (path / "model.bin").exists() and (path / "config.json").exists()


def is_asr_model_ready(model_key: str) -> bool:
    return _is_asr_model_dir_ready(asr_model_path(model_key))


def builtin_asr_model_entry(model_key: str) -> dict[str, Any]:
    model = ASR_MODELS[model_key]
    path = asr_model_path(model_key)
    ready = is_asr_model_ready(model_key)
    return {
        "key": model_key,
        "label": model["label"],
        "nameCn": model["name_cn"],
        "repoId": model["repo_id"],
        "url": model["url"],
        "description": model["description"],
        "ready": ready,
        "path": str(path),
        "sizeBytes": dir_size(path),
        "custom": False,
    }


def translation_model_path(model_key: str) -> Path:
    if model_key not in TRANSLATION_MODELS:
        raise KeyError(model_key)
    return TRANSLATION_MODEL_DIR / TRANSLATION_MODELS[model_key]["repo_id"].rsplit("/", 1)[-1]


def _translation_gguf_files(path: Path) -> list[str]:
    return sorted(item.name for item in path.glob("*.gguf")) if path.exists() else []


def translation_model_entry(model_key: str) -> dict[str, Any]:
    model = TRANSLATION_MODELS[model_key]
    path = translation_model_path(model_key)
    gguf_files = _translation_gguf_files(path)
    return {
        "key": model_key,
        "label": model["label"],
        "nameCn": model["name_cn"],
        "repoId": model["repo_id"],
        "url": model["url"],
        "description": model["description"],
        "ready": bool(gguf_files),
        "path": str(path),
        "sizeBytes": dir_size(path),
        "files": gguf_files,
    }
