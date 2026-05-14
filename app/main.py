from __future__ import annotations

import asyncio
import importlib.util
import array
import json
import math
import os
import queue
import shutil
import subprocess
import sys
import time
import uuid
import wave
from pathlib import Path
from typing import Annotated, Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .asr import transcribe_media, write_bilingual_srt, write_json, write_srt
from .catalog import (
    ASR_MODELS,
    OUTPUT_DIR,
    TRANSLATION_MODELS,
    UPLOAD_DIR,
    asr_model_path,
    builtin_asr_model_entry,
    ensure_dirs,
    is_asr_model_ready,
    translation_model_entry,
    translation_model_path,
)
from .custom_models import (
    add_custom_model,
    add_custom_translation_model,
    custom_model_by_key,
    custom_model_path,
    custom_translation_model_by_key,
    custom_translation_model_path,
    delete_custom_model,
    delete_custom_translation_model,
    load_custom_models,
    load_custom_translation_models,
    validate_custom_model_path,
    validate_translation_model_path,
)
from .chinese import convert_segment_texts, normalize_chinese_script
from .environment import environment_status
from .live_defaults import load_live_defaults, save_live_defaults
from .live_audio import create_live_session, get_live_session, list_live_sessions, save_live_chunk
from .live_stream import LiveAudioProcessor, LiveStreamConfig, disconnect_live_connection, list_live_connections
from .logs import list_events, log_event, subscribe_events, unsubscribe_events
from .tasks import TaskStore
from .translate import (
    TranslationRuntimeError,
    deepseek_chat_completion,
    deeplx_translate_text,
    translate_segments,
    translate_segments_online,
)
from .translation_settings import (
    DEEPSEEK_MODEL,
    load_translation_settings,
    public_translation_settings,
    save_translation_settings,
)
from .version import APP_NAME, APP_VERSION, version_info


ensure_dirs()

app = FastAPI(title=APP_NAME, version=APP_VERSION)
tasks = TaskStore(max_workers=1)
ONLINE_TRANSLATION_MODEL_KEYS = {"deepseek", "deeplx"}


def _restart_backend_process() -> None:
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = ""
    env["PYTHONHOME"] = ""
    env["PYTHONNOUSERSITE"] = "1"
    env.setdefault("TV_CAPTIONER_HOST", "0.0.0.0")
    env.setdefault("TV_CAPTIONER_PORT", "8765")

    if getattr(sys, "frozen", False):
        target_args = [sys.executable]
    else:
        target_args = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            env["TV_CAPTIONER_HOST"],
            "--port",
            env["TV_CAPTIONER_PORT"],
        ]

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    out_path = root / "uvicorn.stdout.log"
    err_path = root / "uvicorn.stderr.log"
    launcher = (
        "import os, subprocess, sys, time\n"
        "root, out_path, err_path, flags = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])\n"
        "args = sys.argv[5:]\n"
        "time.sleep(1.5)\n"
        "stdout = open(out_path, 'ab')\n"
        "stderr = open(err_path, 'ab')\n"
        "subprocess.Popen(args, cwd=root, env=os.environ.copy(), stdout=stdout, stderr=stderr, creationflags=flags)\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", launcher, str(root), str(out_path), str(err_path), str(creation_flags), *target_args],
        cwd=root,
        env=env,
        creationflags=creation_flags,
        close_fds=True,
    )
    time.sleep(0.2)
    os._exit(0)


class LiveSessionCreate(BaseModel):
    sourceLanguage: str = ""
    targetLanguage: str = "Chinese"
    codec: str = "pcm_s16le"
    sampleRate: int = 16000
    channels: int = 1
    note: str = ""


class CustomAsrModelCreate(BaseModel):
    key: str
    label: str
    path: str
    description: str = ""


class CustomTranslationModelCreate(BaseModel):
    key: str
    label: str
    path: str
    description: str = ""


class ModelPathValidate(BaseModel):
    path: str


class LiveDefaultsUpdate(BaseModel):
    device: str = "auto"
    deviceIndex: int = 0
    computeType: str = "auto"
    nGpuLayers: int = 0
    translationGpuIndex: int = 0


class TranslationSettingsUpdate(BaseModel):
    mode: str = "local"
    onlineProvider: str = "deepseek"
    deepseek: dict[str, Any] = {}
    deeplx: dict[str, Any] = {}


def _validate_asr_model(asr_model: str) -> Path:
    model_path = custom_model_path(asr_model) if asr_model.startswith("custom:") else None
    if asr_model not in ASR_MODELS and model_path is None:
        raise HTTPException(status_code=400, detail="Unknown ASR model")
    if asr_model in ASR_MODELS and not is_asr_model_ready(asr_model):
        raise HTTPException(status_code=400, detail=f"ASR model is not downloaded: {asr_model}")
    if asr_model.startswith("custom:"):
        model = custom_model_by_key(asr_model)
        if not model or not model.get("ready"):
            raise HTTPException(status_code=400, detail=f"Custom ASR model is not valid: {asr_model}")
    return model_path or asr_model_path(asr_model)


def _validate_translation_model(translation_model: str) -> Path:
    if importlib.util.find_spec("llama_cpp") is None:
        raise HTTPException(
            status_code=400,
            detail="未发现 GGUF 运行库。便携版/安装包应内置该运行库；源码调试请先运行“首次安装并启动.bat”。",
        )

    model_path = (
        custom_translation_model_path(translation_model)
        if translation_model.startswith("custom:")
        else None
    )
    if translation_model not in TRANSLATION_MODELS and model_path is None:
        raise HTTPException(status_code=400, detail="Unknown translation model")
    if translation_model.startswith("custom:"):
        model = custom_translation_model_by_key(translation_model)
        if not model or not model.get("ready"):
            raise HTTPException(status_code=400, detail=f"Custom translation model is not valid: {translation_model}")
        return model_path or Path(model["path"])

    validation = validate_translation_model_path(str(translation_model_path(translation_model)))
    if not validation["ok"]:
        raise HTTPException(status_code=400, detail=f"Translation model is not ready: {translation_model}")
    return Path(validation["path"])


def _online_translation_ready(settings: dict[str, Any]) -> bool:
    provider = settings.get("onlineProvider") or "deepseek"
    if provider == "deeplx":
        deeplx = settings.get("deeplx") or {}
        return bool(str(deeplx.get("apiKey") or "").strip())
    deepseek = settings.get("deepseek") or {}
    return bool(
        str(deepseek.get("apiUrl") or "").strip()
        and str(deepseek.get("apiKey") or "").strip()
        and str(deepseek.get("prompt") or "").strip()
    )


def _online_translation_model_label(settings: dict[str, Any]) -> str:
    if settings.get("onlineProvider") == "deeplx":
        return "DeepLX"
    return str((settings.get("deepseek") or {}).get("model") or DEEPSEEK_MODEL)


def _translation_engine_label(settings: dict[str, Any]) -> str:
    if settings["mode"] != "online":
        return "llama-cpp-python"
    return "deeplx" if settings.get("onlineProvider") == "deeplx" else "deepseek"


def _require_online_translation_settings(provider: str | None = None) -> dict[str, Any]:
    settings = load_translation_settings()
    if provider in ONLINE_TRANSLATION_MODEL_KEYS:
        settings = {**settings, "mode": "online", "onlineProvider": provider}
    if settings["mode"] != "online":
        return settings
    if not _online_translation_ready(settings):
        provider_label = "DeepLX Key" if settings.get("onlineProvider") == "deeplx" else "DeepSeek API 地址、Key 和提示词"
        raise HTTPException(status_code=400, detail=f"请先在翻译页填写 {provider_label}。")
    return settings


def _translation_settings_for_model(translation_model: str) -> dict[str, Any]:
    provider = translation_model if translation_model in ONLINE_TRANSLATION_MODEL_KEYS else None
    return _require_online_translation_settings(provider)


def _validate_translation_model_for_settings(translation_model: str, settings: dict[str, Any]) -> Path | None:
    if settings["mode"] == "online":
        return None
    return _validate_translation_model(translation_model)


def _translate_segments_for_current_mode(
    *,
    segments: list[dict[str, Any]],
    settings: dict[str, Any],
    translation_model_path_value: Path | None,
    source_language: str | None,
    target_language: str,
    update,
    n_ctx: int = 4096,
    n_gpu_layers: int = 0,
    main_gpu: int = 0,
) -> list[dict[str, Any]]:
    if settings["mode"] == "online":
        return translate_segments_online(
            segments=segments,
            settings=settings,
            source_language=source_language,
            target_language=target_language,
            update=update,
        )
    if translation_model_path_value is None:
        raise TranslationRuntimeError("缺少本地翻译模型。")
    return translate_segments(
        segments=segments,
        model_path=translation_model_path_value,
        source_language=source_language,
        target_language=target_language,
        update=update,
        n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers,
        main_gpu=main_gpu,
    )


def _store_media(
    job_id: str,
    file: UploadFile | None,
    source_path: str | None,
) -> tuple[Path, str]:
    if file is None and not source_path:
        raise HTTPException(status_code=400, detail="Upload a file or provide source_path")

    if file is not None:
        suffix = Path(file.filename or "media").suffix
        media_path = UPLOAD_DIR / f"{job_id}{suffix}"
        with media_path.open("wb") as output:
            shutil.copyfileobj(file.file, output)
        return media_path, file.filename or media_path.name

    media_path = Path(source_path or "").expanduser()
    if not media_path.exists():
        raise HTTPException(status_code=400, detail=f"source_path does not exist: {media_path}")
    return media_path, media_path.name


def _scaled_update(update, start: float, span: float):
    def wrapped(**changes):
        progress = changes.get("progress")
        if progress is not None:
            changes["progress"] = start + float(progress) * span
        update(**changes)

    return wrapped


def _text_preview(value: str, limit: int = 500) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _segments_preview(segments: list[dict], key: str) -> str:
    text = " ".join(str(segment.get(key) or "").strip() for segment in segments[:5]).strip()
    return _text_preview(text)


def _normalize_source_language(language: str | None) -> str | None:
    value = (language or "").strip()
    if not value or value.lower() == "auto":
        return None
    labels = {
        "chinese": "zh",
        "中文": "zh",
        "zh-cn": "zh",
        "japanese": "ja",
        "日本語": "ja",
        "日语": "ja",
        "korean": "ko",
        "韩语": "ko",
        "english": "en",
        "英语": "en",
        "arabic": "ar",
        "阿拉伯语": "ar",
    }
    return labels.get(value.lower(), value)


def _normalize_chinese_script_or_400(script: str | None) -> str:
    try:
        return normalize_chinese_script(script)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _validate_nonnegative_index(value: int, name: str) -> int:
    if value < 0:
        raise HTTPException(status_code=400, detail=f"{name} must be greater than or equal to 0")
    return value


def _validate_live_defaults(payload: LiveDefaultsUpdate) -> dict:
    device = payload.device.strip().lower() or "auto"
    if device not in {"auto", "cuda", "cpu"}:
        raise HTTPException(status_code=400, detail="device must be auto, cuda, or cpu")
    compute_type = payload.computeType.strip() or "auto"
    settings = {
        "device": device,
        "deviceIndex": _validate_nonnegative_index(payload.deviceIndex, "deviceIndex"),
        "computeType": compute_type,
        "nGpuLayers": _validate_nonnegative_index(payload.nGpuLayers, "nGpuLayers"),
        "translationGpuIndex": _validate_nonnegative_index(payload.translationGpuIndex, "translationGpuIndex"),
    }
    return settings


def _live_value(value, defaults: dict, key: str):
    return defaults[key] if value is None else value


def _asr_model_entries() -> list[dict]:
    return [
        *[builtin_asr_model_entry(key) for key in ASR_MODELS],
        *[
            {
                **model,
                "custom": True,
                "ready": (validation := validate_custom_model_path(str(model.get("path", ""))))["ok"],
                "sizeBytes": validation["sizeBytes"],
                "validation": validation,
            }
            for model in load_custom_models()
        ],
    ]


def _translation_model_entries() -> list[dict]:
    settings = load_translation_settings()
    deepseek = settings["deepseek"]
    deeplx = settings["deeplx"]
    deepseek_ready = _online_translation_ready({**settings, "mode": "online", "onlineProvider": "deepseek"})
    deeplx_ready = _online_translation_ready({**settings, "mode": "online", "onlineProvider": "deeplx"})
    online_models = [
        {
            "key": "deepseek",
            "label": f"DeepSeek {deepseek.get('model') or DEEPSEEK_MODEL}",
            "nameCn": f"DeepSeek 在线翻译（{deepseek.get('model') or DEEPSEEK_MODEL}）",
            "repoId": "online/deepseek",
            "url": "https://api-docs.deepseek.com/api/create-chat-completion",
            "description": "在线翻译模型。APK 选择该模型 key 后，后端会调用当前 DeepSeek 配置并返回翻译结果。",
            "ready": deepseek_ready,
            "path": deepseek.get("apiUrl") or "",
            "sizeBytes": 0,
            "files": [],
            "custom": False,
            "online": True,
            "provider": "deepseek",
            "validation": {
                "ok": deepseek_ready,
                "errors": [] if deepseek_ready else ["请先在翻译页填写 DeepSeek API 地址、Key 和提示词。"],
                "warnings": [],
            },
        },
        {
            "key": "deeplx",
            "label": "DeepLX",
            "nameCn": "DeepLX 在线翻译",
            "repoId": "online/deeplx",
            "url": "https://github.com/OwO-Network/DeepLX",
            "description": "在线翻译模型。APK 选择该模型 key 后，后端会调用当前 DeepLX Key 并返回翻译结果。",
            "ready": deeplx_ready,
            "path": deeplx.get("apiUrl") or "",
            "sizeBytes": 0,
            "files": [],
            "custom": False,
            "online": True,
            "provider": "deeplx",
            "validation": {
                "ok": deeplx_ready,
                "errors": [] if deeplx_ready else ["请先在翻译页填写 DeepLX Key。"],
                "warnings": [],
            },
        },
    ]
    return [
        *online_models,
        *[translation_model_entry(key) for key in TRANSLATION_MODELS],
        *[
            {
                **model,
                "custom": True,
                "ready": (validation := validate_translation_model_path(str(model.get("path", ""))))["ok"],
                "sizeBytes": validation["sizeBytes"],
                "files": validation["files"],
                "validation": validation,
            }
            for model in load_custom_translation_models()
        ],
    ]


def _audio_stats(media_path: Path) -> dict:
    stats = {
        "fileBytes": media_path.stat().st_size if media_path.exists() else 0,
        "maxSample": None,
        "rms": None,
        "rmsDbFS": None,
        "isSilent": None,
    }
    try:
        with wave.open(str(media_path), "rb") as wav:
            sample_width = wav.getsampwidth()
            frames = wav.getnframes()
            stats.update(
                {
                    "sampleRate": wav.getframerate(),
                    "channels": wav.getnchannels(),
                    "duration": frames / wav.getframerate() if wav.getframerate() else 0,
                }
            )
            if sample_width != 2:
                return stats
            samples = array.array("h")
            samples.frombytes(wav.readframes(frames))
            if sys.byteorder == "big":
                samples.byteswap()
            if not samples:
                return stats
            max_sample = max(abs(sample) for sample in samples)
            rms = math.sqrt(sum(float(sample) * float(sample) for sample in samples) / len(samples))
            stats.update(
                {
                    "maxSample": max_sample,
                    "rms": round(rms, 2),
                    "rmsDbFS": round(20 * math.log10(rms / 32768), 1) if rms > 0 else None,
                    "isSilent": max_sample <= 16,
                }
            )
    except (EOFError, wave.Error, OSError):
        pass
    return stats


if getattr(sys, "frozen", False):
    STATIC_DIR = Path(getattr(sys, "_MEIPASS")) / "app" / "static"
else:
    STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def log_api_requests(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        if request.url.path.startswith("/api"):
            log_event(
                "error",
                f"接口异常：{request.method} {request.url.path}",
                category="api",
                details={"error": str(exc)},
            )
        raise

    path = request.url.path
    is_noisy_poll = path in {
        "/api/status",
        "/api/tasks",
        "/api/logs",
        "/api/logs/events",
        "/api/live/connections",
        "/api/live/connections/events",
    } or path.startswith("/api/tasks/")
    if path.startswith("/api") and not is_noisy_poll:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        level = "error" if response.status_code >= 500 else "warning" if response.status_code >= 400 else "info"
        log_event(
            level,
            f"接口调用：{request.method} {path}",
            category="api",
            details={"statusCode": response.status_code, "elapsedMs": elapsed_ms},
        )

    return response


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/static/index.html")


@app.get("/api/status")
def status(
    asr_model: str = "large-v2",
) -> dict:
    data = environment_status(
        preferred_asr_model=asr_model,
    )
    settings = load_translation_settings()
    data["translationSettings"] = public_translation_settings(settings)
    if settings["mode"] == "online":
        deepseek = settings["deepseek"]
        deeplx = settings["deeplx"]
        provider = settings.get("onlineProvider") or "deepseek"
        provider_label = "DeepLX" if provider == "deeplx" else "DeepSeek"
        provider_model = "DeepLX" if provider == "deeplx" else deepseek.get("model") or DEEPSEEK_MODEL
        ready = _online_translation_ready(settings)
        data["translationReady"] = ready
        data["translationChecks"] = [
            {
                "key": "translation_mode",
                "label": "翻译模式",
                "ok": True,
                "detail": f"当前使用 {provider_label} 在线翻译，不需要本地 GGUF 翻译模型。",
            },
            {
                "key": f"{provider}_config",
                "label": f"{provider_label} 配置",
                "ok": ready,
                "detail": (
                    (
                        f"API 地址 {deeplx.get('apiUrl') or '-'}，Key 已填写。"
                        if provider == "deeplx"
                        else f"模型 {deepseek.get('model') or DEEPSEEK_MODEL}，API 地址 {deepseek.get('apiUrl') or '-'}，Key 已填写。"
                    )
                    if ready
                    else f"请在翻译页填写 {provider_label} 配置。"
                ),
            },
        ]
        data["translationRuntime"] = {
            "available": ready,
            "mode": "online",
            "provider": provider,
            "model": provider_model,
        }
    return data


@app.get("/api/version")
def get_version() -> dict:
    return version_info()


@app.post("/api/restart")
def restart_backend(background_tasks: BackgroundTasks) -> dict:
    log_event("info", "后端重启已请求", category="system", details={"source": "settings"})
    background_tasks.add_task(_restart_backend_process)
    return {"restarting": True}


@app.get("/api/translation/settings")
def get_translation_settings() -> dict:
    return public_translation_settings(load_translation_settings())


@app.put("/api/translation/settings")
def update_translation_settings(payload: TranslationSettingsUpdate) -> dict:
    settings = save_translation_settings(payload.model_dump())
    log_event(
        "info",
        "翻译设置已保存",
        category="settings",
        details={
            "mode": settings["mode"],
            "onlineProvider": settings["onlineProvider"],
            "deepseekModel": settings["deepseek"]["model"],
            "deepseekApiUrl": settings["deepseek"]["apiUrl"],
            "deepseekApiKeySet": bool(settings["deepseek"]["apiKey"]),
            "deeplxApiUrl": settings["deeplx"]["apiUrl"],
            "deeplxApiKeySet": bool(settings["deeplx"]["apiKey"]),
        },
    )
    return public_translation_settings(settings)


@app.post("/api/translation/deepseek/test")
def test_deepseek_translation(payload: TranslationSettingsUpdate) -> dict:
    settings = save_translation_settings(payload.model_dump())
    deepseek = settings["deepseek"]
    try:
        system_prompt = deepseek["prompt"].format(
            source_language="English",
            target_language="Chinese",
        )
    except (KeyError, ValueError):
        system_prompt = deepseek["prompt"]
    try:
        translated_text = deepseek_chat_completion(
            api_url=deepseek["apiUrl"],
            api_key=deepseek["apiKey"],
            model=deepseek["model"],
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {"role": "user", "content": "Translate this subtitle from English to Chinese:\nHello, this is a connection test."},
            ],
            max_tokens=128,
            timeout=30,
        )
    except Exception as exc:
        log_event(
            "warning",
            "DeepSeek 翻译连通性测试失败",
            category="translation",
            details={
                "mode": settings["mode"],
                "deepseekModel": deepseek["model"],
                "deepseekApiUrl": deepseek["apiUrl"],
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_event(
        "info",
        "DeepSeek 翻译连通性测试成功",
        category="translation",
        details={
            "deepseekModel": deepseek["model"],
            "deepseekApiUrl": deepseek["apiUrl"],
            "translatedText": translated_text,
        },
    )
    return {
        "ok": True,
        "model": deepseek["model"],
        "apiUrl": deepseek["apiUrl"],
        "translatedText": translated_text,
        "settings": public_translation_settings(settings),
    }


@app.post("/api/translation/deeplx/test")
def test_deeplx_translation(payload: TranslationSettingsUpdate) -> dict:
    settings = save_translation_settings(payload.model_dump())
    deeplx = settings["deeplx"]
    try:
        translated_text = deeplx_translate_text(
            api_url=deeplx["apiUrl"],
            api_key=deeplx["apiKey"],
            text="Hello, this is a connection test.",
            source_language="English",
            target_language="Chinese",
            timeout=30,
        )
    except Exception as exc:
        log_event(
            "warning",
            "DeepLX 翻译连通性测试失败",
            category="translation",
            details={
                "mode": settings["mode"],
                "deeplxApiUrl": deeplx["apiUrl"],
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_event(
        "info",
        "DeepLX 翻译连通性测试成功",
        category="translation",
        details={
            "deeplxApiUrl": deeplx["apiUrl"],
            "translatedText": translated_text,
        },
    )
    return {
        "ok": True,
        "provider": "deeplx",
        "apiUrl": deeplx["apiUrl"],
        "translatedText": translated_text,
        "settings": public_translation_settings(settings),
    }


@app.get("/api/tasks")
def list_tasks() -> list[dict]:
    return [record.to_dict() for record in tasks.list()]


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    record = tasks.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    return record.to_dict()


@app.get("/api/logs")
def get_logs(level: str | None = None, limit: int = 200) -> list[dict]:
    return list_events(level=level, limit=limit)


@app.get("/api/logs/events")
async def stream_logs() -> StreamingResponse:
    async def events():
        subscriber = subscribe_events()
        try:
            while True:
                try:
                    event = await asyncio.to_thread(subscriber.get, True, 15)
                except queue.Empty:
                    yield ": heartbeat\n\n"
                    continue
                payload = json.dumps(event, ensure_ascii=False)
                yield f"event: log\ndata: {payload}\n\n"
        finally:
            unsubscribe_events(subscriber)

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/live/defaults")
def get_live_defaults() -> dict:
    return load_live_defaults()


@app.put("/api/live/defaults")
def update_live_defaults(payload: LiveDefaultsUpdate) -> dict:
    return save_live_defaults(_validate_live_defaults(payload))


@app.get("/api/live/connections")
def get_live_connections() -> list[dict]:
    return list_live_connections()


@app.delete("/api/live/connections/{session_id}")
async def close_live_connection(session_id: str) -> dict:
    disconnected = await disconnect_live_connection(session_id, reason="Disconnected from backend console")
    if not disconnected:
        raise HTTPException(status_code=404, detail="Live connection not found")
    return {"disconnected": True, "id": session_id}


@app.get("/api/live/connections/events")
async def stream_live_connections() -> StreamingResponse:
    async def events():
        while True:
            payload = json.dumps(list_live_connections(), ensure_ascii=False)
            yield f"event: connections\ndata: {payload}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/models")
def list_models() -> dict:
    asr_models = _asr_model_entries()
    translation_models = _translation_model_entries()
    return {
        "asrModels": asr_models,
        "translationModels": translation_models,
        "readyAsrModels": [model for model in asr_models if model.get("ready")],
        "readyTranslationModels": [model for model in translation_models if model.get("ready")],
    }


@app.get("/api/models/asr")
def list_asr_models() -> list[dict]:
    return _asr_model_entries()


@app.get("/api/models/translate")
def list_translation_models() -> list[dict]:
    return _translation_model_entries()


@app.get("/api/models/asr/custom")
def list_custom_asr_models() -> list[dict]:
    return load_custom_models()


@app.post("/api/models/asr/custom")
def create_custom_asr_model(payload: CustomAsrModelCreate) -> dict:
    try:
        return add_custom_model(
            key=payload.key,
            label=payload.label,
            path=payload.path,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.delete("/api/models/asr/custom/{model_key:path}")
def remove_custom_asr_model(model_key: str) -> dict:
    try:
        model = delete_custom_model(model_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Custom ASR model not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"deleted": True, "model": model}


@app.post("/api/models/asr/validate")
def validate_asr_model_path(payload: ModelPathValidate) -> dict:
    return validate_custom_model_path(payload.path)


@app.get("/api/models/translate/custom")
def list_custom_translation_models() -> list[dict]:
    return load_custom_translation_models()


@app.post("/api/models/translate/custom")
def create_custom_translation_model(payload: CustomTranslationModelCreate) -> dict:
    try:
        return add_custom_translation_model(
            key=payload.key,
            label=payload.label,
            path=payload.path,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.delete("/api/models/translate/custom/{model_key:path}")
def remove_custom_translation_model(model_key: str) -> dict:
    try:
        model = delete_custom_translation_model(model_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Custom translation model not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"deleted": True, "model": model}


@app.post("/api/models/translate/validate")
def validate_translate_model_path(payload: ModelPathValidate) -> dict:
    return validate_translation_model_path(payload.path)


@app.post("/api/live/sessions")
def create_session(payload: LiveSessionCreate) -> dict:
    session = create_live_session(payload.model_dump())
    log_event(
        "info",
        "创建直播音频会话",
        category="live",
        details={
            "sessionId": session["id"],
            "sourceLanguage": session.get("sourceLanguage") or "auto",
            "targetLanguage": session.get("targetLanguage"),
            "codec": session.get("codec"),
            "sampleRate": session.get("sampleRate"),
            "channels": session.get("channels"),
        },
    )
    return session


@app.get("/api/live/sessions")
def list_sessions() -> list[dict]:
    return list_live_sessions()


@app.get("/api/live/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = get_live_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Live session not found")
    return session


@app.post("/api/live/sessions/{session_id}/chunks")
async def receive_live_chunk(
    session_id: str,
    chunk: Annotated[UploadFile, File()],
    sequence: Annotated[int, Form()],
    start_ms: Annotated[int | None, Form()] = None,
    duration_ms: Annotated[int | None, Form()] = None,
) -> dict:
    try:
        record = save_live_chunk(
            session_id=session_id,
            sequence=sequence,
            content=await chunk.read(),
            filename=chunk.filename or "chunk.bin",
            content_type=chunk.content_type,
            start_ms=start_ms,
            duration_ms=duration_ms,
        )
    except KeyError:
        log_event(
            "warning",
            "直播音频片段上传失败：会话不存在",
            category="live",
            details={"sessionId": session_id, "sequence": sequence},
        )
        raise HTTPException(status_code=404, detail="Live session not found") from None
    log_event(
        "info",
        "收到直播音频片段",
        category="live",
        details={
            "sessionId": session_id,
            "sequence": sequence,
            "filename": record["filename"],
            "sizeBytes": record["sizeBytes"],
            "contentType": record.get("contentType"),
            "startMs": start_ms,
            "durationMs": duration_ms,
        },
    )
    return {"accepted": True, "chunk": record}


@app.websocket("/api/live/ws")
async def live_websocket(
    websocket: WebSocket,
    source_language: Annotated[str, Query(alias="sourceLanguage")] = "",
    target_language: Annotated[str, Query(alias="targetLanguage")] = "Chinese",
    asr_model: Annotated[str, Query(alias="asrModel")] = "large-v2",
    translation_model: Annotated[str, Query(alias="translationModel")] = "qwen2.5-1.5b-instruct-gguf",
    device: str | None = None,
    device_index: Annotated[int | None, Query(alias="deviceIndex")] = None,
    compute_type: Annotated[str | None, Query(alias="computeType")] = None,
    n_ctx: Annotated[int, Query(alias="nCtx")] = 4096,
    n_gpu_layers: Annotated[int | None, Query(alias="nGpuLayers")] = None,
    translation_gpu_index: Annotated[int | None, Query(alias="translationGpuIndex")] = None,
    codec: str = "pcm_s16le",
    sample_rate: Annotated[int, Query(alias="sampleRate")] = 16000,
    channels: int = 1,
    silence_ms: Annotated[int, Query(alias="silenceMs")] = 300,
    max_segment_ms: Annotated[int, Query(alias="maxSegmentMs")] = 5000,
    min_segment_ms: Annotated[int, Query(alias="minSegmentMs")] = 300,
    vad_threshold: Annotated[float, Query(alias="vadThreshold")] = 0.5,
    partial_beam_size: Annotated[int, Query(alias="partialBeamSize")] = 1,
    final_beam_size: Annotated[int, Query(alias="finalBeamSize")] = 3,
    chinese_script: Annotated[str, Query(alias="chineseScript")] = "simplified",
) -> None:
    try:
        live_defaults = load_live_defaults()
        device = _live_value(device, live_defaults, "device")
        device_index = _live_value(device_index, live_defaults, "deviceIndex")
        compute_type = _live_value(compute_type, live_defaults, "computeType")
        n_gpu_layers = _live_value(n_gpu_layers, live_defaults, "nGpuLayers")
        translation_gpu_index = _live_value(translation_gpu_index, live_defaults, "translationGpuIndex")
        if codec != "pcm_s16le":
            raise HTTPException(status_code=400, detail="WebSocket live mode currently expects codec=pcm_s16le")
        if sample_rate <= 0:
            raise HTTPException(status_code=400, detail="sampleRate must be greater than 0")
        if channels < 1 or channels > 2:
            raise HTTPException(status_code=400, detail="channels must be 1 or 2")
        if silence_ms < 200:
            raise HTTPException(status_code=400, detail="silenceMs must be at least 200")
        if partial_beam_size < 1 or partial_beam_size > 5:
            raise HTTPException(status_code=400, detail="partialBeamSize must be between 1 and 5")
        if final_beam_size < 1 or final_beam_size > 5:
            raise HTTPException(status_code=400, detail="finalBeamSize must be between 1 and 5")
        if not target_language.strip():
            raise HTTPException(status_code=400, detail="targetLanguage is required")
        device_index = _validate_nonnegative_index(device_index, "deviceIndex")
        translation_gpu_index = _validate_nonnegative_index(translation_gpu_index, "translationGpuIndex")

        asr_model_path_value = _validate_asr_model(asr_model)
        translation_settings = _translation_settings_for_model(translation_model)
        translation_model_path_value = _validate_translation_model_for_settings(translation_model, translation_settings)
    except HTTPException as exc:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": exc.detail})
        await websocket.close(code=1008)
        return

    requested_language = _normalize_source_language(source_language)
    processor = LiveAudioProcessor(
        websocket=websocket,
        config=LiveStreamConfig(
            source_language=requested_language,
            target_language=target_language.strip(),
            asr_model_path=asr_model_path_value,
            asr_model_key=asr_model,
            translation_model_path=translation_model_path_value,
            translation_model_key=(
                _online_translation_model_label(translation_settings)
                if translation_settings["mode"] == "online"
                else translation_model
            ),
            translation_engine=translation_settings["mode"],
            online_translation_settings=translation_settings if translation_settings["mode"] == "online" else None,
            chinese_script=_normalize_chinese_script_or_400(chinese_script),
            device=device,
            device_index=device_index,
            compute_type=compute_type,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            translation_gpu_index=translation_gpu_index,
            codec=codec,
            sample_rate=sample_rate,
            channels=channels,
            silence_ms=silence_ms,
            max_segment_ms=max_segment_ms,
            min_segment_ms=min_segment_ms,
            partial_beam_size=partial_beam_size,
            final_beam_size=final_beam_size,
            vad_threshold=vad_threshold,
        ),
    )
    await processor.run()


@app.websocket("/api/live/asr-ws")
async def live_asr_websocket(
    websocket: WebSocket,
    source_language: Annotated[str, Query(alias="sourceLanguage")] = "",
    asr_model: Annotated[str, Query(alias="asrModel")] = "large-v2",
    device: str | None = None,
    device_index: Annotated[int | None, Query(alias="deviceIndex")] = None,
    compute_type: Annotated[str | None, Query(alias="computeType")] = None,
    codec: str = "pcm_s16le",
    sample_rate: Annotated[int, Query(alias="sampleRate")] = 16000,
    channels: int = 1,
    silence_ms: Annotated[int, Query(alias="silenceMs")] = 300,
    max_segment_ms: Annotated[int, Query(alias="maxSegmentMs")] = 5000,
    min_segment_ms: Annotated[int, Query(alias="minSegmentMs")] = 300,
    vad_threshold: Annotated[float, Query(alias="vadThreshold")] = 0.5,
    partial_beam_size: Annotated[int, Query(alias="partialBeamSize")] = 1,
    final_beam_size: Annotated[int, Query(alias="finalBeamSize")] = 3,
    chinese_script: Annotated[str, Query(alias="chineseScript")] = "simplified",
) -> None:
    try:
        live_defaults = load_live_defaults()
        device = _live_value(device, live_defaults, "device")
        device_index = _live_value(device_index, live_defaults, "deviceIndex")
        compute_type = _live_value(compute_type, live_defaults, "computeType")
        if codec != "pcm_s16le":
            raise HTTPException(status_code=400, detail="WebSocket ASR mode currently expects codec=pcm_s16le")
        if sample_rate <= 0:
            raise HTTPException(status_code=400, detail="sampleRate must be greater than 0")
        if channels < 1 or channels > 2:
            raise HTTPException(status_code=400, detail="channels must be 1 or 2")
        if silence_ms < 200:
            raise HTTPException(status_code=400, detail="silenceMs must be at least 200")
        if partial_beam_size < 1 or partial_beam_size > 5:
            raise HTTPException(status_code=400, detail="partialBeamSize must be between 1 and 5")
        if final_beam_size < 1 or final_beam_size > 5:
            raise HTTPException(status_code=400, detail="finalBeamSize must be between 1 and 5")
        device_index = _validate_nonnegative_index(device_index, "deviceIndex")

        asr_model_path_value = _validate_asr_model(asr_model)
    except HTTPException as exc:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": exc.detail})
        await websocket.close(code=1008)
        return

    processor = LiveAudioProcessor(
        websocket=websocket,
        config=LiveStreamConfig(
            source_language=_normalize_source_language(source_language),
            target_language="",
            asr_model_path=asr_model_path_value,
            asr_model_key=asr_model,
            translation_model_path=None,
            translate_enabled=False,
            chinese_script=_normalize_chinese_script_or_400(chinese_script),
            device=device,
            device_index=device_index,
            compute_type=compute_type,
            codec=codec,
            sample_rate=sample_rate,
            channels=channels,
            silence_ms=silence_ms,
            max_segment_ms=max_segment_ms,
            min_segment_ms=min_segment_ms,
            partial_beam_size=partial_beam_size,
            final_beam_size=final_beam_size,
            vad_threshold=vad_threshold,
        ),
    )
    await processor.run()


@app.post("/api/audio/translate")
def translate_audio_now(
    request: Request,
    file: Annotated[UploadFile | None, File()] = None,
    source_path: Annotated[str | None, Form()] = None,
    source_language: Annotated[str, Form()] = "",
    target_language: Annotated[str, Form()] = "Chinese",
    asr_model: Annotated[str, Form()] = "large-v2",
    translation_model: Annotated[str, Form()] = "qwen2.5-1.5b-instruct-gguf",
    audio_source: Annotated[str, Form()] = "",
    device: Annotated[str, Form()] = "auto",
    device_index: Annotated[int, Form()] = 0,
    compute_type: Annotated[str, Form()] = "auto",
    n_ctx: Annotated[int, Form()] = 4096,
    n_gpu_layers: Annotated[int, Form()] = 0,
    translation_gpu_index: Annotated[int, Form()] = 0,
    chinese_script: Annotated[str, Form()] = "simplified",
) -> dict:
    request_id = uuid.uuid4().hex
    asr_model_path_value = _validate_asr_model(asr_model)
    translation_settings = _translation_settings_for_model(translation_model)
    translation_model_path_value = _validate_translation_model_for_settings(translation_model, translation_settings)
    device_index = _validate_nonnegative_index(device_index, "device_index")
    translation_gpu_index = _validate_nonnegative_index(translation_gpu_index, "translation_gpu_index")
    media_path, label = _store_media(request_id, file, source_path)
    audio_stats = _audio_stats(media_path)
    requested_language = _normalize_source_language(source_language)
    output_chinese_script = _normalize_chinese_script_or_400(chinese_script)
    target = target_language.strip()
    client_ip = request.client.host if request.client else ""

    log_event(
        "warning" if audio_stats.get("isSilent") else "info",
        "收到音频",
        category="audio",
        details={
            "requestId": request_id,
            "clientIp": client_ip,
            "label": label,
            "sourceLanguage": requested_language or "auto",
            "targetLanguage": target,
            "asrModel": asr_model,
            "translationModel": (
                _online_translation_model_label(translation_settings)
                if translation_settings["mode"] == "online"
                else translation_model
            ),
            "translationEngine": translation_settings["mode"],
            "device": device,
            "deviceIndex": device_index,
            "computeType": compute_type,
            "nGpuLayers": n_gpu_layers,
            "translationGpuIndex": translation_gpu_index,
            "chineseScript": output_chinese_script,
            "audioSource": audio_source.strip() or "unknown",
            "audioStats": audio_stats,
            "mediaPath": str(media_path),
        },
    )

    def update(**changes):
        pass

    try:
        asr_result = transcribe_media(
            media_path=media_path,
            model_path=asr_model_path_value,
            language=requested_language,
            device=device,
            device_index=device_index,
            compute_type=compute_type,
            update=_scaled_update(update, 0.0, 0.55),
        )
        asr_result["segments"] = convert_segment_texts(asr_result["segments"], output_chinese_script)
        detected_language = asr_result["language"]
        log_event(
            "info",
            "同步音频转写完成" if asr_result["segments"] else "同步音频转写完成但未识别到文本",
            category="asr",
            details={
                "requestId": request_id,
                "sourceLanguage": detected_language,
                "requestedSourceLanguage": requested_language or "auto",
                "languageProbability": asr_result["languageProbability"],
                "duration": asr_result["duration"],
                "segmentCount": len(asr_result["segments"]),
                "sourceText": _segments_preview(asr_result["segments"], "text"),
            },
        )

        segments = _translate_segments_for_current_mode(
            segments=asr_result["segments"],
            settings=translation_settings,
            translation_model_path_value=translation_model_path_value,
            source_language=requested_language or detected_language,
            target_language=target,
            update=_scaled_update(update, 0.55, 0.43),
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            main_gpu=translation_gpu_index,
        )
        segments = convert_segment_texts(segments, output_chinese_script)
    except Exception as exc:
        log_event(
            "error",
            "同步音频翻译失败",
            category="translation",
            details={"requestId": request_id, "error": str(exc)},
        )
        raise

    source_text = _segments_preview(segments, "text")
    translated_text = _segments_preview(segments, "translation")
    log_event(
        "info",
        "同步音频翻译完成",
        category="translation",
        details={
            "requestId": request_id,
            "sourceLanguage": requested_language or detected_language,
            "targetLanguage": target,
            "segmentCount": len(segments),
            "sourceText": source_text,
            "translatedText": translated_text,
        },
    )

    return {
        "requestId": request_id,
        "sourceLanguage": detected_language,
        "requestedSourceLanguage": requested_language or "auto",
        "languageProbability": asr_result["languageProbability"],
        "targetLanguage": target,
        "chineseScript": output_chinese_script,
        "device": device,
        "deviceIndex": device_index,
        "computeType": compute_type,
        "nGpuLayers": n_gpu_layers,
        "translationGpuIndex": translation_gpu_index,
        "translationEngine": translation_settings["mode"],
        "duration": asr_result["duration"],
        "segmentCount": len(segments),
        "sourceText": source_text,
        "translatedText": translated_text,
        "segments": segments,
    }


@app.post("/api/jobs/transcribe")
def create_transcription_job(
    file: Annotated[UploadFile | None, File()] = None,
    source_path: Annotated[str | None, Form()] = None,
    source_language: Annotated[str, Form()] = "",
    asr_model: Annotated[str, Form()] = "large-v2",
    device: Annotated[str, Form()] = "auto",
    device_index: Annotated[int, Form()] = 0,
    compute_type: Annotated[str, Form()] = "auto",
    chinese_script: Annotated[str, Form()] = "simplified",
) -> dict:
    job_id = uuid.uuid4().hex
    model_path = _validate_asr_model(asr_model)
    device_index = _validate_nonnegative_index(device_index, "device_index")
    output_chinese_script = _normalize_chinese_script_or_400(chinese_script)
    media_path, label = _store_media(job_id, file, source_path)
    log_event(
        "info",
        "创建转写任务",
        category="task",
        details={
            "jobId": job_id,
            "label": label,
            "sourceLanguage": source_language or "auto",
            "asrModel": asr_model,
            "device": device,
            "deviceIndex": device_index,
            "computeType": compute_type,
            "chineseScript": output_chinese_script,
            "mediaPath": str(media_path),
        },
    )

    def worker(task_id: str, update) -> dict:
        try:
            output_prefix = OUTPUT_DIR / task_id
            language = source_language.strip()
            language = None if not language or language == "auto" else language
            asr_result = transcribe_media(
                media_path=media_path,
                model_path=model_path,
                language=language,
                device=device,
                device_index=device_index,
                compute_type=compute_type,
                update=update,
            )
            segments = convert_segment_texts(asr_result["segments"], output_chinese_script)
            log_event(
                "info",
                "音频转写完成" if segments else "音频转写完成但未识别到文本",
                category="asr",
                details={
                    "taskId": task_id,
                    "sourceLanguage": asr_result["language"],
                    "languageProbability": asr_result["languageProbability"],
                    "duration": asr_result["duration"],
                    "segmentCount": len(segments),
                    "sourceText": _segments_preview(segments, "text"),
                },
            )

            payload = {
                "mediaPath": str(media_path),
                "asrModel": asr_model,
                "device": device,
                "deviceIndex": device_index,
                "computeType": compute_type,
                "sourceLanguage": asr_result["language"],
                "languageProbability": asr_result["languageProbability"],
                "duration": asr_result["duration"],
                "translationEngine": None,
                "targetLanguage": None,
                "chineseScript": output_chinese_script,
                "segments": segments,
            }
            json_path = output_prefix.with_suffix(".json")
            source_srt_path = output_prefix.with_name(f"{output_prefix.name}.source.srt")

            write_json(payload, json_path)
            write_srt(segments, source_srt_path, "text")
            outputs = {
                "json": f"/api/outputs/{json_path.name}",
                "sourceSrt": f"/api/outputs/{source_srt_path.name}",
            }

            return {"outputs": outputs, "segmentCount": len(segments)}
        except Exception as exc:
            log_event(
                "error",
                "转写任务失败",
                category="asr",
                details={"taskId": task_id, "error": str(exc)},
            )
            raise

    record = tasks.submit(kind="transcribe", label=f"转写 {label}", worker=worker)
    return record.to_dict()


@app.post("/api/jobs/translate-test")
def create_translation_test_job(
    file: Annotated[UploadFile | None, File()] = None,
    source_path: Annotated[str | None, Form()] = None,
    source_language: Annotated[str, Form()] = "",
    target_language: Annotated[str, Form()] = "Chinese",
    asr_model: Annotated[str, Form()] = "large-v2",
    translation_model: Annotated[str, Form()] = "qwen2.5-1.5b-instruct-gguf",
    device: Annotated[str, Form()] = "auto",
    device_index: Annotated[int, Form()] = 0,
    compute_type: Annotated[str, Form()] = "auto",
    n_ctx: Annotated[int, Form()] = 4096,
    n_gpu_layers: Annotated[int, Form()] = 0,
    translation_gpu_index: Annotated[int, Form()] = 0,
    chinese_script: Annotated[str, Form()] = "simplified",
) -> dict:
    job_id = uuid.uuid4().hex
    asr_model_path_value = _validate_asr_model(asr_model)
    translation_settings = _translation_settings_for_model(translation_model)
    translation_model_path_value = _validate_translation_model_for_settings(translation_model, translation_settings)
    device_index = _validate_nonnegative_index(device_index, "device_index")
    translation_gpu_index = _validate_nonnegative_index(translation_gpu_index, "translation_gpu_index")
    output_chinese_script = _normalize_chinese_script_or_400(chinese_script)
    media_path, label = _store_media(job_id, file, source_path)
    log_event(
        "info",
        "创建转写翻译任务",
        category="task",
        details={
            "jobId": job_id,
            "label": label,
            "sourceLanguage": source_language or "auto",
            "targetLanguage": target_language,
            "asrModel": asr_model,
            "translationModel": (
                _online_translation_model_label(translation_settings)
                if translation_settings["mode"] == "online"
                else translation_model
            ),
            "translationEngine": translation_settings["mode"],
            "device": device,
            "deviceIndex": device_index,
            "computeType": compute_type,
            "nGpuLayers": n_gpu_layers,
            "translationGpuIndex": translation_gpu_index,
            "chineseScript": output_chinese_script,
            "mediaPath": str(media_path),
        },
    )

    def worker(task_id: str, update) -> dict:
        try:
            output_prefix = OUTPUT_DIR / task_id
            requested_language = source_language.strip()
            requested_language = None if not requested_language or requested_language == "auto" else requested_language
            asr_result = transcribe_media(
                media_path=media_path,
                model_path=asr_model_path_value,
                language=requested_language,
                device=device,
                device_index=device_index,
                compute_type=compute_type,
                update=_scaled_update(update, 0.0, 0.55),
            )
            asr_result["segments"] = convert_segment_texts(asr_result["segments"], output_chinese_script)
            detected_language = asr_result["language"]
            log_event(
                "info",
                "音频转写完成" if asr_result["segments"] else "音频转写完成但未识别到文本",
                category="asr",
                details={
                    "taskId": task_id,
                    "sourceLanguage": detected_language,
                    "requestedSourceLanguage": requested_language or "auto",
                    "languageProbability": asr_result["languageProbability"],
                    "duration": asr_result["duration"],
                    "segmentCount": len(asr_result["segments"]),
                    "sourceText": _segments_preview(asr_result["segments"], "text"),
                },
            )

            segments = _translate_segments_for_current_mode(
                segments=asr_result["segments"],
                settings=translation_settings,
                translation_model_path_value=translation_model_path_value,
                source_language=requested_language or detected_language,
                target_language=target_language.strip(),
                update=_scaled_update(update, 0.55, 0.43),
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                main_gpu=translation_gpu_index,
            )
            segments = convert_segment_texts(segments, output_chinese_script)
            log_event(
                "info",
                "字幕翻译完成",
                category="translation",
                details={
                    "taskId": task_id,
                    "sourceLanguage": requested_language or detected_language,
                    "targetLanguage": target_language.strip(),
                    "segmentCount": len(segments),
                    "sourceText": _segments_preview(segments, "text"),
                    "translatedText": _segments_preview(segments, "translation"),
                },
            )

            payload = {
                "mediaPath": str(media_path),
                "asrModel": asr_model,
                "translationModel": (
                    _online_translation_model_label(translation_settings)
                    if translation_settings["mode"] == "online"
                    else translation_model
                ),
                "device": device,
                "deviceIndex": device_index,
                "computeType": compute_type,
                "nGpuLayers": n_gpu_layers,
                "translationGpuIndex": translation_gpu_index,
                "sourceLanguage": detected_language,
                "requestedSourceLanguage": requested_language or "auto",
                "languageProbability": asr_result["languageProbability"],
                "duration": asr_result["duration"],
                "translationEngine": _translation_engine_label(translation_settings),
                "targetLanguage": target_language.strip(),
                "chineseScript": output_chinese_script,
                "segments": segments,
            }
            json_path = output_prefix.with_suffix(".json")
            source_srt_path = output_prefix.with_name(f"{output_prefix.name}.source.srt")
            translated_srt_path = output_prefix.with_name(f"{output_prefix.name}.translated.srt")
            bilingual_srt_path = output_prefix.with_name(f"{output_prefix.name}.bilingual.srt")

            write_json(payload, json_path)
            write_srt(segments, source_srt_path, "text")
            write_srt(segments, translated_srt_path, "translation")
            write_bilingual_srt(segments, bilingual_srt_path)
            outputs = {
                "json": f"/api/outputs/{json_path.name}",
                "sourceSrt": f"/api/outputs/{source_srt_path.name}",
                "translatedSrt": f"/api/outputs/{translated_srt_path.name}",
                "bilingualSrt": f"/api/outputs/{bilingual_srt_path.name}",
            }

            return {"outputs": outputs, "segmentCount": len(segments)}
        except Exception as exc:
            log_event(
                "error",
                "转写翻译任务失败",
                category="translation",
                details={"taskId": task_id, "error": str(exc)},
            )
            raise

    record = tasks.submit(kind="translate-test", label=f"翻译测试 {label}", worker=worker)
    return record.to_dict()


@app.get("/api/outputs/{filename}")
def get_output(filename: str) -> FileResponse:
    path = OUTPUT_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Output not found")
    return FileResponse(path)
