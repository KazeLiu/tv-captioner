from __future__ import annotations

import importlib.util
from typing import Any

from .asr import CUDA_DOWNLOAD_URL, asr_cuda_status
from .catalog import ASR_MODELS, TRANSLATION_MODELS, builtin_asr_model_entry, translation_model_entry
from .custom_models import (
    load_custom_models,
    load_custom_translation_models,
    validate_custom_model_path,
    validate_translation_model_path,
)
from .live_defaults import load_live_defaults


def _model_names(models: list[dict[str, Any]], limit: int = 6) -> str:
    names = [str(model.get("nameCn") or model.get("label") or model.get("key") or "").strip() for model in models]
    names = [name for name in names if name]
    if not names:
        return ""
    shown = names[:limit]
    suffix = f" 等 {len(names)} 个模型" if len(names) > limit else ""
    return "、".join(shown) + suffix


def _required_checks_ready(checks: list[dict[str, Any]]) -> bool:
    return all(item["ok"] for item in checks if item.get("required") is not False)


def _translation_runtime_status(cuda_available: bool, live_defaults: dict[str, Any]) -> dict[str, Any]:
    n_gpu_layers = max(0, int(live_defaults.get("nGpuLayers") or 0))
    translation_gpu_index = max(0, int(live_defaults.get("translationGpuIndex") or 0))
    if importlib.util.find_spec("llama_cpp") is None:
        return {
            "available": False,
            "version": None,
            "supportsGpuOffload": False,
            "cudaAvailable": cuda_available,
            "mode": "unavailable",
            "nGpuLayers": n_gpu_layers,
            "translationGpuIndex": translation_gpu_index,
            "detail": "未发现 GGUF 翻译运行库。普通包应内置 CPU 版；源码调试请先运行“首次安装并启动.bat”。",
        }

    try:
        import llama_cpp

        supports_gpu = bool(
            getattr(llama_cpp, "llama_supports_gpu_offload", lambda: False)()
        )
        version = getattr(llama_cpp, "__version__", None)
    except Exception as exc:
        return {
            "available": False,
            "version": None,
            "supportsGpuOffload": False,
            "cudaAvailable": cuda_available,
            "mode": "unavailable",
            "nGpuLayers": n_gpu_layers,
            "translationGpuIndex": translation_gpu_index,
            "detail": f"GGUF 翻译运行库加载失败：{exc}",
        }

    uses_gpu = supports_gpu and cuda_available and n_gpu_layers > 0
    if uses_gpu:
        detail = (
            f"已安装 CUDA 版 llama-cpp-python {version}；当前直播默认会尝试使用 GPU "
            f"{translation_gpu_index} offload {n_gpu_layers} 层。层数表示把 GGUF 翻译模型的一部分层放进显卡，"
            "数字越大越吃显存；若模型加载失败，后端会退回 CPU。"
        )
    elif supports_gpu and cuda_available:
        detail = (
            f"已安装 GGUF CUDA 版 llama-cpp-python {version}，并且 CUDA 12 运行库可用；"
            "当前直播默认层数为 0，所以翻译仍走 CPU。GGUF 翻译 GPU 层数表示把多少层翻译模型放进显卡；"
            "4GB 显存建议从 2-4 层小步测试。"
        )
    elif supports_gpu:
        detail = (
            f"已安装 GGUF CUDA 版 llama-cpp-python {version}，但当前缺少可加载的 CUDA 12 运行库；"
            "GGUF 翻译会按 CPU 跑，GPU 层数请保持 0。要启用 GPU，请安装 CUDA 12 运行库或把 GPU DLC 放到后端目录。"
        )
    else:
        detail = (
            f"已安装 GGUF CPU 版 llama-cpp-python {version}；普通包默认就是这个状态，"
            "GGUF 翻译会使用 CPU，GPU 层数请保持 0。要启用 GGUF GPU offload，请安装 GPU DLC。"
        )
    return {
        "available": True,
        "version": version,
        "supportsGpuOffload": supports_gpu,
        "cudaAvailable": cuda_available,
        "mode": "gpu" if uses_gpu else "cpu",
        "nGpuLayers": n_gpu_layers,
        "translationGpuIndex": translation_gpu_index,
        "detail": detail,
    }


def environment_status(
    preferred_asr_model: str,
) -> dict[str, Any]:
    asr_models = [builtin_asr_model_entry(key) for key in ASR_MODELS]
    custom_asr_models = [
        {
            **model,
            "custom": True,
            "ready": (validation := validate_custom_model_path(str(model.get("path", ""))))["ok"],
            "sizeBytes": validation["sizeBytes"],
            "validation": validation,
        }
        for model in load_custom_models()
    ]
    ready_asr_models = [model for model in [*asr_models, *custom_asr_models] if model["ready"]]
    asr_model = ASR_MODELS.get(preferred_asr_model)

    cuda_status = asr_cuda_status()
    transcription_checks = [
        {
            "key": "asr_model",
            "label": "转写模型文件",
            "required": True,
            "ok": bool(ready_asr_models),
            "detail": (
                f"已安装：{_model_names(ready_asr_models)}。"
                if ready_asr_models
                else "未发现可用转写模型，请先在下方选择模型页面下载并放到对应目录。"
            ),
            "action": None
            if ready_asr_models or preferred_asr_model.startswith("custom:") or preferred_asr_model not in ASR_MODELS
            else {
                "type": "link",
                "label": "打开模型页",
                "url": asr_model["url"] if asr_model else "https://huggingface.co/Systran",
            },
        },
        {
            "key": "asr_cuda",
            "label": "转写 CUDA 运行库",
            "required": False,
            "ok": cuda_status["available"],
            "detail": cuda_status["detail"],
            "action": None
            if cuda_status["available"]
            else {
                "type": "link",
                "label": "下载 CUDA 12",
                "url": CUDA_DOWNLOAD_URL,
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
    live_defaults = load_live_defaults()
    translation_runtime = _translation_runtime_status(cuda_status["available"], live_defaults)
    translation_runtime_ready = translation_runtime["available"]
    translation_checks = [
        {
            "key": "translation_model",
            "label": "翻译模型文件",
            "required": True,
            "ok": bool(ready_translation_models),
            "detail": (
                f"已安装：{_model_names(ready_translation_models)}。"
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
            "label": "GGUF 翻译运行库",
            "required": True,
            "ok": translation_runtime_ready,
            "detail": translation_runtime["detail"],
            "action": None,
        },
    ]
    transcription_ready = _required_checks_ready(transcription_checks)
    translation_ready = _required_checks_ready(translation_checks)

    return {
        "ready": transcription_ready,
        "checks": transcription_checks,
        "transcriptionReady": transcription_ready,
        "transcriptionChecks": transcription_checks,
        "translationReady": translation_ready,
        "translationChecks": translation_checks,
        "tools": {},
        "cuda": cuda_status,
        "translationRuntime": translation_runtime,
        "asrModels": asr_models,
        "translationModels": translation_models,
        "customAsrModels": custom_asr_models,
        "customTranslationModels": custom_translation_models,
    }
