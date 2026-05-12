from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .catalog import DATA_DIR, dir_size


CUSTOM_MODELS_PATH = DATA_DIR / "custom_asr_models.json"
CUSTOM_TRANSLATION_MODELS_PATH = DATA_DIR / "custom_translation_models.json"
MODEL_KEY_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")


def load_custom_models() -> list[dict[str, Any]]:
    return _load_model_file(CUSTOM_MODELS_PATH)


def load_custom_translation_models() -> list[dict[str, Any]]:
    return _load_model_file(CUSTOM_TRANSLATION_MODELS_PATH)


def _load_model_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def save_custom_models(models: list[dict[str, Any]]) -> None:
    _save_model_file(CUSTOM_MODELS_PATH, models)


def save_custom_translation_models(models: list[dict[str, Any]]) -> None:
    _save_model_file(CUSTOM_TRANSLATION_MODELS_PATH, models)


def _save_model_file(path: Path, models: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(models, ensure_ascii=False, indent=2), encoding="utf-8")


def add_custom_model(key: str, label: str, path: str, description: str = "") -> dict[str, Any]:
    key = key.strip()
    label = label.strip() or key
    path = path.strip().strip('"')
    description = description.strip()

    if not MODEL_KEY_RE.match(key):
        raise ValueError("模型标识只能包含字母、数字、点、下划线和短横线，长度 1-64。")

    validation = validate_custom_model_path(path)
    model = {
        "key": f"custom:{key}",
        "label": label,
        "nameCn": f"{label}（自定义）",
        "repoId": "local/custom",
        "url": "",
        "description": description or "自定义本地 faster-whisper / CTranslate2 模型目录。",
        "path": validation["path"],
        "ready": validation["ok"],
        "sizeBytes": validation["sizeBytes"],
        "validation": validation,
        "createdAt": time.time(),
    }

    models = [item for item in load_custom_models() if item.get("key") != model["key"]]
    models.append(model)
    save_custom_models(models)
    return model


def add_custom_translation_model(key: str, label: str, path: str, description: str = "") -> dict[str, Any]:
    key = key.strip()
    label = label.strip() or key
    path = path.strip().strip('"')
    description = description.strip()

    if not MODEL_KEY_RE.match(key):
        raise ValueError("模型标识只能包含字母、数字、点、下划线和短横线，长度 1-64。")

    validation = validate_translation_model_path(path)
    model = {
        "key": f"custom:{key}",
        "label": label,
        "nameCn": f"{label}（自定义）",
        "repoId": "local/custom",
        "url": "",
        "description": description or "自定义本地 GGUF 翻译模型。可以选择单个 .gguf 文件，也可以选择包含 .gguf 的目录。",
        "path": validation["path"],
        "ready": validation["ok"],
        "sizeBytes": validation["sizeBytes"],
        "files": validation["files"],
        "validation": validation,
        "createdAt": time.time(),
        "custom": True,
    }

    models = [item for item in load_custom_translation_models() if item.get("key") != model["key"]]
    models.append(model)
    save_custom_translation_models(models)
    return model


def validate_custom_model_path(path_value: str) -> dict[str, Any]:
    raw = path_value.strip().strip('"')
    if not raw:
        return _validation(False, "", ["请填写模型目录。"], [])

    path = Path(raw).expanduser()
    if not path.exists():
        return _validation(False, str(path), ["路径不存在。"], [])
    if path.is_file():
        suffix = path.suffix.lower()
        message = "当前后端需要 faster-whisper / CTranslate2 模型目录，不是单个模型文件。"
        if suffix in {".bin", ".gguf"}:
            message += " 你选的可能是 whisper.cpp 模型，后续需要接 whisper.cpp 运行时才能直接用。"
        return _validation(False, str(path), [message], [])

    files = {item.name.lower() for item in path.iterdir() if item.is_file()}
    errors: list[str] = []
    warnings: list[str] = []

    if "model.bin" not in files:
        errors.append("缺少 model.bin。")
    if "config.json" not in files:
        errors.append("缺少 config.json。")
    if not ({"tokenizer.json", "vocabulary.json"} & files):
        warnings.append("没有看到 tokenizer.json 或 vocabulary.json；部分模型可能仍可用，但建议确认目录是否完整。")

    return _validation(not errors, str(path), errors, warnings, dir_size(path))


def validate_translation_model_path(path_value: str) -> dict[str, Any]:
    raw = path_value.strip().strip('"')
    if not raw:
        return _validation(False, "", ["请填写 GGUF 模型文件或模型目录。"], [], files=[])

    path = Path(raw).expanduser()
    if not path.exists():
        return _validation(False, str(path), ["路径不存在。"], [], files=[])

    errors: list[str] = []
    warnings: list[str] = []
    gguf_files: list[str] = []
    size_bytes = 0

    if path.is_file():
        size_bytes = path.stat().st_size
        if path.suffix.lower() != ".gguf":
            errors.append("翻译模型当前需要 GGUF 文件；请选择后缀为 .gguf 的模型文件。")
        else:
            gguf_files = [path.name]
    else:
        gguf_files = sorted(item.name for item in path.glob("*.gguf") if item.is_file())
        size_bytes = dir_size(path)
        if not gguf_files:
            errors.append("目录里没有发现 .gguf 模型文件。")

    if len(gguf_files) > 1:
        warnings.append("目录里有多个 .gguf 文件；后续运行时会需要你指定具体使用哪一个。")

    return _validation(not errors, str(path), errors, warnings, size_bytes, gguf_files)


def custom_model_by_key(model_key: str) -> dict[str, Any] | None:
    for model in load_custom_models():
        if model.get("key") == model_key:
            validation = validate_custom_model_path(str(model.get("path", "")))
            model = {**model, "ready": validation["ok"], "sizeBytes": validation["sizeBytes"], "validation": validation}
            return model
    return None


def custom_model_path(model_key: str) -> Path | None:
    model = custom_model_by_key(model_key)
    if not model:
        return None
    return Path(model["path"])


def custom_translation_model_by_key(model_key: str) -> dict[str, Any] | None:
    for model in load_custom_translation_models():
        if model.get("key") == model_key:
            validation = validate_translation_model_path(str(model.get("path", "")))
            model = {
                **model,
                "ready": validation["ok"],
                "sizeBytes": validation["sizeBytes"],
                "files": validation["files"],
                "validation": validation,
                "custom": True,
            }
            return model
    return None


def custom_translation_model_path(model_key: str) -> Path | None:
    model = custom_translation_model_by_key(model_key)
    if not model:
        return None
    return Path(model["path"])


def _validation(
    ok: bool,
    path: str,
    errors: list[str],
    warnings: list[str],
    size_bytes: int = 0,
    files: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "path": path,
        "errors": errors,
        "warnings": warnings,
        "sizeBytes": size_bytes,
        "files": files or [],
    }
