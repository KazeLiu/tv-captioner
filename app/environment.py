from __future__ import annotations

import importlib.util
from typing import Any

from .catalog import ASR_MODELS, TRANSLATION_MODELS, asr_model_path, builtin_asr_model_entry, is_asr_model_ready, translation_model_entry
from .custom_models import (
    custom_model_by_key,
    load_custom_models,
    load_custom_translation_models,
    validate_custom_model_path,
    validate_translation_model_path,
)


def environment_status(
    preferred_asr_model: str,
) -> dict[str, Any]:
    custom_model = custom_model_by_key(preferred_asr_model) if preferred_asr_model.startswith("custom:") else None
    asr_ready = (
        bool(custom_model and custom_model.get("ready"))
        if preferred_asr_model.startswith("custom:")
        else is_asr_model_ready(preferred_asr_model)
        if preferred_asr_model in ASR_MODELS
        else False
    )
    asr_model = ASR_MODELS.get(preferred_asr_model)
    model_detail = (
        str(custom_model.get("path"))
        if custom_model
        else str(asr_model_path(preferred_asr_model))
        if preferred_asr_model in ASR_MODELS
        else "未知模型"
    )

    transcription_checks = [
        {
            "key": "asr_model",
            "label": f"转写模型 {preferred_asr_model}",
            "required": True,
            "ok": asr_ready,
            "detail": model_detail,
            "action": None
            if asr_ready or preferred_asr_model.startswith("custom:") or preferred_asr_model not in ASR_MODELS
            else {
                "type": "link",
                "label": "打开模型页",
                "url": asr_model["url"] if asr_model else "https://huggingface.co/Systran",
            },
        },
    ]

    translation_models = [translation_model_entry(key) for key in TRANSLATION_MODELS]
    custom_translation_models = [
        {
            **model,
            "custom": True,
            "ready": (validation := validate_translation_model_path(str(model.get("path", ""))))["ok"],
            "sizeBytes": validation["sizeBytes"],
            "files": validation["files"],
            "validation": validation,
        }
        for model in load_custom_translation_models()
    ]
    ready_translation_models = [model for model in [*translation_models, *custom_translation_models] if model["ready"]]
    translation_runtime_ready = importlib.util.find_spec("llama_cpp") is not None
    translation_checks = [
        {
            "key": "translation_model",
            "label": "翻译模型文件",
            "required": True,
            "ok": bool(ready_translation_models),
            "detail": (
                f"已发现 {len(ready_translation_models)} 个可用 GGUF 模型。"
                if ready_translation_models
                else "未发现 GGUF 模型文件，请先在下方选择模型页面下载并放到对应目录。"
            ),
            "action": {
                "type": "link",
                "label": "打开推荐模型页",
                "url": TRANSLATION_MODELS["qwen2.5-3b-instruct-gguf"]["url"],
            }
            if not ready_translation_models
            else None,
        },
        {
            "key": "translation_runtime",
            "label": "GGUF 运行库",
            "required": True,
            "ok": translation_runtime_ready,
            "detail": "已安装 llama-cpp-python，可直接加载 GGUF 模型。"
            if translation_runtime_ready
            else "未发现 GGUF 运行库。便携版/安装包应内置该运行库；源码调试请先运行“首次安装并启动.bat”。",
            "action": None,
        },
    ]
    transcription_ready = all(item["ok"] for item in transcription_checks)
    translation_ready = all(item["ok"] for item in translation_checks)

    return {
        "ready": transcription_ready,
        "checks": transcription_checks,
        "transcriptionReady": transcription_ready,
        "transcriptionChecks": transcription_checks,
        "translationReady": translation_ready,
        "translationChecks": translation_checks,
        "tools": {},
        "asrModels": [builtin_asr_model_entry(key) for key in ASR_MODELS],
        "translationModels": translation_models,
        "customAsrModels": [
            {
                **model,
                "custom": True,
                "ready": (validation := validate_custom_model_path(str(model.get("path", ""))))["ok"],
                "sizeBytes": validation["sizeBytes"],
                "validation": validation,
            }
            for model in load_custom_models()
        ],
        "customTranslationModels": custom_translation_models,
    }
