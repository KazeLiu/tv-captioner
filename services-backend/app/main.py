from __future__ import annotations

import importlib.util
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .asr import transcribe_media, write_bilingual_srt, write_json, write_srt
from .catalog import (
    ASR_MODELS,
    OUTPUT_DIR,
    TRANSLATION_MODELS,
    UPLOAD_DIR,
    asr_model_path,
    ensure_dirs,
    is_asr_model_ready,
    translation_model_path,
)
from .custom_models import (
    add_custom_model,
    add_custom_translation_model,
    custom_model_by_key,
    custom_model_path,
    custom_translation_model_by_key,
    custom_translation_model_path,
    load_custom_models,
    load_custom_translation_models,
    validate_custom_model_path,
    validate_translation_model_path,
)
from .environment import environment_status
from .live_audio import create_live_session, get_live_session, list_live_sessions, save_live_chunk
from .logs import list_events, log_event
from .tasks import TaskStore
from .translate import translate_segments


ensure_dirs()

app = FastAPI(title="TV Captioner Backend")
tasks = TaskStore(max_workers=1)


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
    is_noisy_poll = path in {"/api/status", "/api/tasks", "/api/logs"} or path.startswith("/api/tasks/")
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
    return environment_status(
        preferred_asr_model=asr_model,
    )


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


@app.post("/api/audio/translate")
def translate_audio_now(
    file: Annotated[UploadFile | None, File()] = None,
    source_path: Annotated[str | None, Form()] = None,
    source_language: Annotated[str, Form()] = "",
    target_language: Annotated[str, Form()] = "Chinese",
    asr_model: Annotated[str, Form()] = "large-v2",
    translation_model: Annotated[str, Form()] = "qwen2.5-1.5b-instruct-gguf",
    device: Annotated[str, Form()] = "auto",
    compute_type: Annotated[str, Form()] = "auto",
    n_ctx: Annotated[int, Form()] = 4096,
    n_gpu_layers: Annotated[int, Form()] = 0,
) -> dict:
    request_id = uuid.uuid4().hex
    asr_model_path_value = _validate_asr_model(asr_model)
    translation_model_path_value = _validate_translation_model(translation_model)
    media_path, label = _store_media(request_id, file, source_path)
    requested_language = source_language.strip()
    requested_language = None if not requested_language or requested_language == "auto" else requested_language
    target = target_language.strip()

    log_event(
        "info",
        "收到同步音频翻译请求",
        category="api",
        details={
            "requestId": request_id,
            "label": label,
            "sourceLanguage": requested_language or "auto",
            "targetLanguage": target,
            "asrModel": asr_model,
            "translationModel": translation_model,
            "mediaPath": str(media_path),
        },
    )

    progress_state = {"last": None}

    def update(**changes):
        message = changes.get("message")
        progress = changes.get("progress")
        bucket = None if progress is None else int(float(progress) * 10)
        progress_key = (message, bucket)
        if message and progress_key != progress_state["last"]:
            progress_state["last"] = progress_key
            log_event(
                "info",
                f"同步音频翻译进度：{message}",
                category="task",
                details={"requestId": request_id, "progress": progress},
            )

    try:
        asr_result = transcribe_media(
            media_path=media_path,
            model_path=asr_model_path_value,
            language=requested_language,
            device=device,
            compute_type=compute_type,
            update=_scaled_update(update, 0.0, 0.55),
        )
        detected_language = asr_result["language"]
        log_event(
            "info" if asr_result["segments"] else "warning",
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

        segments = translate_segments(
            segments=asr_result["segments"],
            model_path=translation_model_path_value,
            source_language=requested_language or detected_language,
            target_language=target,
            update=_scaled_update(update, 0.55, 0.43),
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
        )
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
    compute_type: Annotated[str, Form()] = "auto",
) -> dict:
    job_id = uuid.uuid4().hex
    model_path = _validate_asr_model(asr_model)
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
                compute_type=compute_type,
                update=update,
            )
            segments = asr_result["segments"]
            log_event(
                "info" if segments else "warning",
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
                "sourceLanguage": asr_result["language"],
                "languageProbability": asr_result["languageProbability"],
                "duration": asr_result["duration"],
                "translationEngine": None,
                "targetLanguage": None,
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
    compute_type: Annotated[str, Form()] = "auto",
    n_ctx: Annotated[int, Form()] = 4096,
    n_gpu_layers: Annotated[int, Form()] = 0,
) -> dict:
    job_id = uuid.uuid4().hex
    asr_model_path_value = _validate_asr_model(asr_model)
    translation_model_path_value = _validate_translation_model(translation_model)
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
            "translationModel": translation_model,
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
                compute_type=compute_type,
                update=_scaled_update(update, 0.0, 0.55),
            )
            detected_language = asr_result["language"]
            log_event(
                "info" if asr_result["segments"] else "warning",
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

            segments = translate_segments(
                segments=asr_result["segments"],
                model_path=translation_model_path_value,
                source_language=requested_language or detected_language,
                target_language=target_language.strip(),
                update=_scaled_update(update, 0.55, 0.43),
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
            )
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
                "translationModel": translation_model,
                "sourceLanguage": detected_language,
                "requestedSourceLanguage": requested_language or "auto",
                "languageProbability": asr_result["languageProbability"],
                "duration": asr_result["duration"],
                "translationEngine": "llama-cpp-python",
                "targetLanguage": target_language.strip(),
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
