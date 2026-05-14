from __future__ import annotations

import asyncio
import gc
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from faster_whisper.vad import VadOptions, get_speech_timestamps

from .asr import asr_runtime_status, clear_asr_model_cache, transcribe_audio_array
from .chinese import convert_segment_texts, normalize_chinese_script
from .logs import log_event
from .translate import (
    cached_gguf_runtime,
    clear_gguf_model_cache,
    gguf_runtime_status,
    resolve_gguf_model_path,
    translate_segments,
    translate_segments_online,
)


VAD_SAMPLE_RATE = 16000
LIVE_IDLE_TIMEOUT_SECONDS = 30 * 60
_LIVE_CONNECTIONS: dict[str, dict[str, Any]] = {}
_LIVE_PROCESSORS: dict[str, "LiveAudioProcessor"] = {}
_LIVE_CONNECTIONS_LOCK = threading.RLock()


def list_live_connections() -> list[dict[str, Any]]:
    now = time.time()
    with _LIVE_CONNECTIONS_LOCK:
        connections = []
        for connection in _LIVE_CONNECTIONS.values():
            connected_at = float(connection.get("connectedAt") or now)
            updated_at = float(connection.get("updatedAt") or connected_at)
            connections.append(
                {
                    **connection,
                    "connectedSeconds": max(0.0, now - connected_at),
                    "idleSeconds": max(0.0, now - updated_at),
                }
            )
    return sorted(connections, key=lambda item: item.get("connectedAt", 0), reverse=True)


def _update_live_connection(session_id: str, **changes: Any) -> None:
    with _LIVE_CONNECTIONS_LOCK:
        connection = _LIVE_CONNECTIONS.get(session_id)
        if not connection:
            return
        connection.update(changes)
        connection["updatedAt"] = time.time()


async def disconnect_live_connection(session_id: str, reason: str = "Disconnected") -> bool:
    with _LIVE_CONNECTIONS_LOCK:
        processor = _LIVE_PROCESSORS.get(session_id)
    if not processor:
        return False
    await processor.request_disconnect(reason)
    return True


def _text_preview(value: str, limit: int = 500) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _segments_preview(segments: list[dict[str, Any]], key: str) -> str:
    text = " ".join(str(segment.get(key) or "").strip() for segment in segments[:5]).strip()
    return _text_preview(text)


def _segments_text(segments: list[dict[str, Any]], key: str, limit: int = 240) -> str:
    text = " ".join(str(segment.get(key) or "").strip() for segment in segments if segment.get(key)).strip()
    return _text_preview(text, limit=limit)


_LIVE_ASR_HALLUCINATION_PHRASES = (
    "感谢观看",
    "谢谢观看",
    "下集待续",
    "下集再见",
    "欢迎订阅我的频道",
    "本期视频就分享到这里",
    "请不吝点赞订阅转发打赏支持",
)


def _compact_asr_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE).lower()


def _is_live_asr_hallucination(text: str) -> bool:
    compact = _compact_asr_text(text)
    if not compact:
        return False

    if "amara" in compact:
        return True

    if "字幕由" in compact and "提供" in compact:
        return True

    return any(_compact_asr_text(phrase) in compact for phrase in _LIVE_ASR_HALLUCINATION_PHRASES)


def _filter_live_asr_hallucinations(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [segment for segment in segments if not _is_live_asr_hallucination(str(segment.get("text") or ""))]


@dataclass
class LiveStreamConfig:
    source_language: str | None
    target_language: str
    asr_model_path: Path
    asr_model_key: str = ""
    translation_model_path: Path | None = None
    translation_model_key: str = ""
    translation_engine: str = "local"
    online_translation_settings: dict[str, Any] | None = None
    translate_enabled: bool = True
    chinese_script: str = "simplified"
    device: str = "auto"
    device_index: int = 0
    compute_type: str = "auto"
    n_ctx: int = 4096
    n_gpu_layers: int = 0
    translation_gpu_index: int = 0
    codec: str = "pcm_s16le"
    sample_rate: int = 16000
    channels: int = 1
    silence_ms: int = 300
    max_segment_ms: int = 5000
    min_segment_ms: int = 300
    partial_interval_ms: int = 1000
    partial_beam_size: int = 1
    final_beam_size: int = 3
    vad_threshold: float = 0.5


@dataclass
class LiveUtterance:
    id: str
    audio: bytes
    start: float
    end: float
    forced: bool = False


@dataclass
class LivePartialSnapshot:
    final_id: str
    final_sequence: int
    generation: int
    audio: bytes
    start: float
    end: float
    source_context: str


def pcm_s16le_to_float32(
    content: bytes,
    sample_rate: int,
    channels: int,
    target_rate: int = VAD_SAMPLE_RATE,
) -> np.ndarray:
    frame_width = max(channels, 1) * 2
    usable_bytes = len(content) - (len(content) % frame_width)
    if usable_bytes <= 0:
        return np.array([], dtype=np.float32)

    samples = np.frombuffer(content[:usable_bytes], dtype="<i2")
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    audio = samples.astype(np.float32) / 32768.0

    if sample_rate == target_rate or audio.size == 0:
        return audio.astype(np.float32, copy=False)

    duration = audio.size / sample_rate
    target_size = max(1, int(round(duration * target_rate)))
    source_positions = np.linspace(0, audio.size - 1, num=audio.size)
    target_positions = np.linspace(0, audio.size - 1, num=target_size)
    return np.interp(target_positions, source_positions, audio).astype(np.float32)


class LiveAudioProcessor:
    def __init__(self, websocket: WebSocket, config: LiveStreamConfig) -> None:
        self.websocket = websocket
        self.config = config
        self.session_id = uuid.uuid4().hex
        self.client_ip = websocket.client.host if websocket.client else ""
        self._queue: asyncio.Queue[LiveUtterance | None] = asyncio.Queue()
        self._send_lock = asyncio.Lock()
        self._cancel_requested = threading.Event()
        self._segment_buffer = bytearray()
        self._recent_buffer = bytearray()
        self._pre_speech_buffer = bytearray()
        self._in_speech = False
        self._segment_start_seconds = 0.0
        self._stream_frames = 0
        self._last_speech_seconds = 0.0
        self._sequence = 0
        self._partial_generation = 0
        self._partial_task: asyncio.Task[None] | None = None
        self._last_partial_end_seconds = 0.0
        self._source_context = ""
        self._translation_context = ""
        self._detected_language: str | None = None
        self._translation_gguf_path = (
            resolve_gguf_model_path(config.translation_model_path)
            if config.translate_enabled and config.translation_engine == "local" and config.translation_model_path
            else None
        )

        self._bytes_per_frame = max(config.channels, 1) * 2
        self._silence_seconds = config.silence_ms / 1000
        self._max_segment_seconds = config.max_segment_ms / 1000
        self._min_segment_seconds = config.min_segment_ms / 1000
        self._partial_interval_seconds = min(1.5, max(0.8, config.partial_interval_ms / 1000))
        self._recent_max_bytes = self._bytes_for_seconds(0.65)
        self._pre_speech_max_bytes = self._bytes_for_seconds(0.25)

    async def run(self) -> None:
        await self.websocket.accept()
        self._register_connection()
        await self._send_json(
            {
                "type": "ready",
                "sessionId": self.session_id,
                "codec": self.config.codec,
                "sampleRate": self.config.sample_rate,
                "channels": self.config.channels,
                "translationEnabled": self.config.translate_enabled,
                "translationEngine": self.config.translation_engine if self.config.translate_enabled else None,
                "chineseScript": normalize_chinese_script(self.config.chinese_script),
                "device": self.config.device,
                "deviceIndex": self.config.device_index,
                "computeType": self.config.compute_type,
                "nGpuLayers": self.config.n_gpu_layers,
                "translationGpuIndex": self.config.translation_gpu_index,
            }
        )
        log_event(
            "info",
            "WebSocket live session started",
            category="live",
            details={
                "sessionId": self.session_id,
                "sourceLanguage": self.config.source_language or "auto",
                "targetLanguage": self.config.target_language,
                "translationEnabled": self.config.translate_enabled,
                "translationEngine": self.config.translation_engine if self.config.translate_enabled else None,
                "chineseScript": normalize_chinese_script(self.config.chinese_script),
                "device": self.config.device,
                "deviceIndex": self.config.device_index,
                "computeType": self.config.compute_type,
                "nGpuLayers": self.config.n_gpu_layers,
                "translationGpuIndex": self.config.translation_gpu_index,
                "sampleRate": self.config.sample_rate,
                "channels": self.config.channels,
                "silenceMs": self.config.silence_ms,
            },
        )

        worker = asyncio.create_task(self._process_queue())
        idle_monitor = asyncio.create_task(self._monitor_idle_timeout())
        try:
            await self._receive_loop()
        finally:
            self._cancel_pending_work("连接已断开，已取消未处理队列")
            idle_monitor.cancel()
            try:
                await idle_monitor
            except asyncio.CancelledError:
                pass
            await self._stop_partial_task()
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
            self._unregister_connection()
            log_event(
                "info",
                "WebSocket live session closed",
                category="live",
                details={"sessionId": self.session_id},
            )

    async def request_disconnect(self, reason: str) -> None:
        _update_live_connection(
            self.session_id,
            status="disconnecting",
            lastEvent="disconnect_requested",
            disconnectReason=reason,
        )
        await self._send_json({"type": "close", "reason": reason})
        try:
            await self.websocket.close(code=1000, reason=reason[:120])
        except (RuntimeError, WebSocketDisconnect):
            pass

    async def _monitor_idle_timeout(self) -> None:
        while True:
            await asyncio.sleep(15)
            with _LIVE_CONNECTIONS_LOCK:
                connection = _LIVE_CONNECTIONS.get(self.session_id)
                updated_at = float(connection.get("updatedAt") or 0) if connection else 0
            if not updated_at:
                continue
            if time.time() - updated_at >= LIVE_IDLE_TIMEOUT_SECONDS:
                log_event(
                    "warning",
                    "WebSocket live session idle timeout",
                    category="live",
                    details={
                        "sessionId": self.session_id,
                        "clientIp": self.client_ip,
                        "idleSeconds": round(time.time() - updated_at, 3),
                    },
                )
                await self.request_disconnect("Idle for 30 minutes")
                return

    async def _receive_loop(self) -> None:
        while True:
            try:
                message = await self.websocket.receive()
            except WebSocketDisconnect:
                return

            message_type = message.get("type")
            if message_type == "websocket.disconnect":
                return

            content = message.get("bytes")
            if content is not None:
                await self._handle_audio_chunk(content)
                continue

            text = message.get("text")
            if text is not None:
                should_continue = await self._handle_control_message(text)
                if not should_continue:
                    return

    async def _handle_control_message(self, text: str) -> bool:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            await self._send_json({"type": "error", "message": "Control message must be JSON."})
            return True

        message_type = payload.get("type")
        if message_type == "flush":
            await self._flush_current(forced=True)
        elif message_type == "ping":
            await self._send_json({"type": "pong", "time": time.time()})
        elif message_type == "close":
            await self.websocket.close()
            return False
        else:
            await self._send_json({"type": "error", "message": f"Unknown control message: {message_type}"})
        return True

    async def _handle_audio_chunk(self, content: bytes) -> None:
        content = self._aligned(content)
        if not content:
            return

        chunk_frames = len(content) // self._bytes_per_frame
        chunk_end_seconds = (self._stream_frames + chunk_frames) / self.config.sample_rate
        self._stream_frames += chunk_frames
        self._update_connection_counters(
            audioChunks=1,
            receivedBytes=len(content),
            streamSeconds=round(self._stream_frames / self.config.sample_rate, 3),
            lastEvent="audio",
            lastAudioAt=time.time(),
        )

        self._append_limited(self._recent_buffer, content, self._recent_max_bytes)
        speech_end_offset = await asyncio.to_thread(self._detect_speech_end, bytes(self._recent_buffer))
        has_speech = speech_end_offset is not None
        if speech_end_offset is not None:
            recent_duration = self._frames_in_bytes(self._recent_buffer) / self.config.sample_rate
            detected_speech_end = max(0.0, chunk_end_seconds - recent_duration + speech_end_offset)
        else:
            detected_speech_end = None

        if self._in_speech:
            self._segment_buffer.extend(content)
            if detected_speech_end is not None:
                self._last_speech_seconds = max(self._last_speech_seconds, detected_speech_end)
            segment_duration = chunk_end_seconds - self._segment_start_seconds
            silence_duration = chunk_end_seconds - self._last_speech_seconds
            if silence_duration >= self._silence_seconds or segment_duration >= self._max_segment_seconds:
                await self._flush_current(forced=segment_duration >= self._max_segment_seconds)
            else:
                self._maybe_schedule_partial(chunk_end_seconds)
        else:
            self._append_limited(self._pre_speech_buffer, content, self._pre_speech_max_bytes)
            if has_speech:
                self._in_speech = True
                self._partial_generation += 1
                self._last_partial_end_seconds = 0.0
                self._segment_buffer = bytearray(self._pre_speech_buffer)
                preroll_seconds = self._frames_in_bytes(self._segment_buffer) / self.config.sample_rate
                self._segment_start_seconds = max(0.0, chunk_end_seconds - preroll_seconds)
                self._last_speech_seconds = detected_speech_end or chunk_end_seconds
                await self._send_json({"type": "speech_start", "start": self._segment_start_seconds})
                _update_live_connection(self.session_id, lastEvent="speech_start")

    async def _flush_current(self, forced: bool) -> None:
        if self._cancel_requested.is_set():
            return
        if not self._in_speech or not self._segment_buffer:
            return

        duration = self._frames_in_bytes(self._segment_buffer) / self.config.sample_rate
        utterance = LiveUtterance(
            id=f"{self.session_id}-{self._sequence}",
            audio=bytes(self._segment_buffer),
            start=self._segment_start_seconds,
            end=self._segment_start_seconds + duration,
            forced=forced,
        )
        self._sequence += 1
        self._in_speech = False
        self._partial_generation += 1
        self._segment_buffer = bytearray()
        self._pre_speech_buffer = bytearray(self._recent_buffer[-self._pre_speech_max_bytes :])

        if duration < self._min_segment_seconds:
            await self._send_json({"type": "speech_discarded", "id": utterance.id, "duration": duration})
            _update_live_connection(self.session_id, lastEvent="speech_discarded")
            return

        await self._queue.put(utterance)
        self._append_pending_utterance(utterance)
        self._update_connection_counters(queuedSegments=1, lastEvent="speech_end")
        log_event(
            "info",
            "收到音频",
            category="live",
            details={
                "sessionId": self.session_id,
                "utteranceId": utterance.id,
                "clientIp": self.client_ip,
                "start": utterance.start,
                "end": utterance.end,
                "duration": duration,
                "sizeBytes": len(utterance.audio),
                "forced": utterance.forced,
            },
        )
        await self._send_json(
            {
                "type": "speech_end",
                "id": utterance.id,
                "start": utterance.start,
                "end": utterance.end,
                "forced": utterance.forced,
            }
        )

    def _maybe_schedule_partial(self, chunk_end_seconds: float) -> None:
        if not self._in_speech or not self._segment_buffer:
            return

        if self._partial_task is not None and self._partial_task.done():
            self._partial_task = None
        if self._partial_task is not None:
            return

        duration = self._frames_in_bytes(self._segment_buffer) / self.config.sample_rate
        if duration < max(self._min_segment_seconds, self._partial_interval_seconds):
            return

        if (
            self._last_partial_end_seconds
            and chunk_end_seconds - self._last_partial_end_seconds < self._partial_interval_seconds
        ):
            return

        final_sequence = self._sequence
        snapshot = LivePartialSnapshot(
            final_id=f"{self.session_id}-{final_sequence}",
            final_sequence=final_sequence,
            generation=self._partial_generation,
            audio=bytes(self._segment_buffer),
            start=self._segment_start_seconds,
            end=self._segment_start_seconds + duration,
            source_context=self._source_context,
        )
        self._last_partial_end_seconds = snapshot.end
        self._partial_task = asyncio.create_task(self._run_partial(snapshot))

    async def _run_partial(self, snapshot: LivePartialSnapshot) -> None:
        try:
            payload = await asyncio.to_thread(self._process_partial, snapshot)
        except Exception as exc:  # noqa: BLE001 - partials are best-effort previews
            log_event(
                "warning",
                "WebSocket live partial failed",
                category="live",
                details={
                    "sessionId": self.session_id,
                    "utteranceId": snapshot.final_id,
                    "clientIp": self.client_ip,
                    "error": str(exc),
                },
            )
            self._update_connection_counters(errorCount=1, lastEvent="partial_error")
            return
        finally:
            task = asyncio.current_task()
            if task is self._partial_task:
                self._partial_task = None

        if payload is None or not self._is_partial_current(snapshot):
            return

        self._update_connection_counters(partialCount=1, lastEvent="partial")
        self._append_recent_text(
            kind="partial",
            utterance_id=snapshot.final_id,
            source_text=_segments_text(payload.get("segments") or [], "text"),
            translated_text="",
        )
        await self._send_json(payload)

    def _process_partial(self, snapshot: LivePartialSnapshot) -> dict[str, Any] | None:
        audio = pcm_s16le_to_float32(
            snapshot.audio,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
            target_rate=VAD_SAMPLE_RATE,
        )
        if audio.size == 0:
            return None

        def update(**changes: Any) -> None:
            pass

        asr_result = transcribe_audio_array(
            audio=audio,
            model_path=self.config.asr_model_path,
            language=self.config.source_language,
            device=self.config.device,
            device_index=self.config.device_index,
            compute_type=self.config.compute_type,
            update=update,
            beam_size=self.config.partial_beam_size,
            vad_filter=False,
            condition_on_previous_text=False,
        )

        segments: list[dict[str, Any]] = []
        for index, segment in enumerate(asr_result["segments"]):
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                {
                    "id": str(segment.get("id", index)),
                    "start": float(segment["start"]) + snapshot.start,
                    "end": float(segment["end"]) + snapshot.start,
                    "text": text,
                }
        )
        segments = convert_segment_texts(segments, self.config.chinese_script)
        segments = _filter_live_asr_hallucinations(segments)
        if not segments:
            return None

        return {
            "type": "partial",
            "id": f"partial-{snapshot.final_id}",
            "finalId": snapshot.final_id,
            "start": snapshot.start,
            "end": snapshot.end,
            "translationEnabled": self.config.translate_enabled,
            "chineseScript": normalize_chinese_script(self.config.chinese_script),
            "segments": segments,
        }

    def _is_partial_current(self, snapshot: LivePartialSnapshot) -> bool:
        return (
            self._in_speech
            and self._sequence == snapshot.final_sequence
            and self._partial_generation == snapshot.generation
            and bool(self._segment_buffer)
        )

    async def _stop_partial_task(self) -> None:
        task = self._partial_task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def _cancel_pending_work(self, reason: str) -> None:
        self._cancel_requested.set()
        self._in_speech = False
        self._partial_generation += 1
        self._segment_buffer = bytearray()
        self._pre_speech_buffer = bytearray()

        cancelled_count = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is not None:
                cancelled_count += 1

        now = time.time()
        with _LIVE_CONNECTIONS_LOCK:
            connection = _LIVE_CONNECTIONS.get(self.session_id)
            if not connection:
                return
            current = dict(connection.get("currentProcessing") or {})
            if current:
                current.update(
                    {
                        "status": "cancelling",
                        "message": "连接已断开，正在停止当前任务",
                        "updatedAt": now,
                    }
                )
                connection["currentProcessing"] = current
            connection["pendingUtterances"] = []
            connection["queuedSegments"] = 0
            connection["lastEvent"] = "cancelled"
            connection["updatedAt"] = now

        self._append_processing_log(
            reason,
            level="warning",
            cancelledQueuedSegments=cancelled_count,
        )
        log_event(
            "info",
            "WebSocket live pending work cancelled",
            category="live",
            details={
                "sessionId": self.session_id,
                "clientIp": self.client_ip,
                "cancelledQueuedSegments": cancelled_count,
            },
        )

    async def _process_queue(self) -> None:
        while True:
            utterance = await self._queue.get()
            if utterance is None:
                return
            if self._cancel_requested.is_set():
                self._finish_processing_utterance(
                    utterance,
                    status="cancelled",
                    message="连接已断开，已取消处理",
                )
                continue
            await self._send_json({"type": "processing", "id": utterance.id})
            self._start_processing_utterance(utterance)
            try:
                payload = await asyncio.to_thread(self._process_utterance, utterance)
            except asyncio.CancelledError:
                self._finish_processing_utterance(
                    utterance,
                    status="cancelled",
                    message="连接已断开，已停止等待当前任务",
                )
                raise
            except Exception as exc:  # noqa: BLE001 - surfaced to WebSocket client
                log_event(
                    "error",
                    "WebSocket live segment failed",
                    category="live",
                    details={
                        "sessionId": self.session_id,
                        "utteranceId": utterance.id,
                        "clientIp": self.client_ip,
                        "error": str(exc),
                    },
                )
                self._finish_processing_utterance(
                    utterance,
                    status="error",
                    message="处理失败",
                    error=str(exc),
                )
                self._update_connection_counters(errorCount=1, queuedSegments=-1, lastEvent="error")
                await self._send_json({"type": "error", "id": utterance.id, "message": str(exc)})
                continue

            source_text = _segments_text(payload.get("segments") or [], "text")
            self._finish_processing_utterance(
                utterance,
                status="done",
                message="处理完成",
                source_text=source_text,
            )
            self._update_connection_counters(segmentCount=1, queuedSegments=-1, lastEvent="segment")
            await self._send_json(payload)

    def _process_utterance(self, utterance: LiveUtterance) -> dict[str, Any]:
        if self._cancel_requested.is_set():
            return {
                "type": "segment",
                "id": utterance.id,
                "segments": [],
                "cancelled": True,
            }

        audio = pcm_s16le_to_float32(
            utterance.audio,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
            target_rate=VAD_SAMPLE_RATE,
        )
        if audio.size == 0:
            return {"type": "segment", "id": utterance.id, "segments": []}

        requested_language = self.config.source_language

        def update(**changes: Any) -> None:
            message = str(changes.get("message") or "")
            stage_labels = {
                "Loading ASR model": "正在加载 ASR 模型",
                "Transcribing media": "正在转写音频",
                "Translating subtitles": "正在翻译字幕",
                "Translation cancelled": "连接已断开，已停止后续翻译",
            }
            if message.startswith("Loading translation model:"):
                model_name = message.replace("Loading translation model:", "").strip()
                display_message = f"正在加载翻译模型：{model_name}" if model_name else "正在加载翻译模型"
            else:
                display_message = stage_labels.get(message, message or "正在处理")
            self._update_current_processing(
                status="processing",
                message=display_message,
                progress=changes.get("progress"),
            )
            self._append_processing_log(
                display_message,
                utterance,
                progress=changes.get("progress"),
            )

        asr_result = transcribe_audio_array(
            audio=audio,
            model_path=self.config.asr_model_path,
            language=requested_language,
            device=self.config.device,
            device_index=self.config.device_index,
            compute_type=self.config.compute_type,
            update=update,
            initial_prompt=self._source_context or None,
            beam_size=self.config.final_beam_size,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        self._set_runtime_status(asr_runtime=asr_result.get("runtime"))
        detected_language = asr_result.get("language") or requested_language
        self._detected_language = detected_language

        segments = []
        for segment in asr_result["segments"]:
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                {
                    **segment,
                    "start": float(segment["start"]) + utterance.start,
                    "end": float(segment["end"]) + utterance.start,
                }
            )
        segments = convert_segment_texts(segments, self.config.chinese_script)
        raw_segment_count = len(segments)
        segments = _filter_live_asr_hallucinations(segments)
        filtered_segment_count = raw_segment_count - len(segments)
        log_event(
            "info",
            "直播音频转写完成" if segments else "直播音频转写完成但未识别到文本",
            category="live",
            details={
                "sessionId": self.session_id,
                "utteranceId": utterance.id,
                "clientIp": self.client_ip,
                "sourceLanguage": detected_language or "auto",
                "segmentCount": len(segments),
                "filteredSegmentCount": filtered_segment_count,
                "sourceText": _segments_preview(segments, "text"),
            },
        )

        if self._cancel_requested.is_set():
            log_event(
                "info",
                "直播连接已断开，跳过后续翻译",
                category="live",
                details={
                    "sessionId": self.session_id,
                    "utteranceId": utterance.id,
                    "clientIp": self.client_ip,
                    "sourceLanguage": detected_language or "auto",
                    "segmentCount": len(segments),
                },
            )
            return {
                "type": "segment",
                "id": utterance.id,
                "sourceLanguage": detected_language,
                "targetLanguage": self.config.target_language if self.config.translate_enabled else None,
                "translationEnabled": False,
                "chineseScript": normalize_chinese_script(self.config.chinese_script),
                "start": utterance.start,
                "end": utterance.end,
                "forced": utterance.forced,
                "segments": segments,
                "cancelled": True,
            }

        if self.config.translate_enabled and (
            self.config.translation_model_path or self.config.online_translation_settings
        ):
            if self.config.translation_engine == "online":
                output_segments = translate_segments_online(
                    segments=segments,
                    settings=self.config.online_translation_settings or {},
                    source_language=requested_language or detected_language,
                    target_language=self.config.target_language,
                    update=update,
                    previous_context=self._translation_context,
                    cancelled=self._cancel_requested.is_set,
                )
            else:
                output_segments = translate_segments(
                    segments=segments,
                    model_path=self._translation_gguf_path or self.config.translation_model_path,
                    source_language=requested_language or detected_language,
                    target_language=self.config.target_language,
                    update=update,
                    n_ctx=self.config.n_ctx,
                    n_gpu_layers=self.config.n_gpu_layers,
                    main_gpu=self.config.translation_gpu_index,
                    previous_context=self._translation_context,
                    cancelled=self._cancel_requested.is_set,
                )
                if self._translation_gguf_path:
                    self._set_runtime_status(
                        translation_runtime=cached_gguf_runtime(
                            self._translation_gguf_path,
                            self.config.n_ctx,
                            self.config.n_gpu_layers,
                            self.config.translation_gpu_index,
                        )
                    )
            output_segments = convert_segment_texts(output_segments, self.config.chinese_script)
            self._update_context(output_segments)
            log_event(
                "info",
                "直播音频翻译完成" if output_segments else "直播音频翻译完成但没有文本",
                category="live",
                details={
                    "sessionId": self.session_id,
                    "utteranceId": utterance.id,
                    "clientIp": self.client_ip,
                    "sourceLanguage": detected_language or "auto",
                    "targetLanguage": self.config.target_language,
                    "translationEnabled": True,
                    "segmentCount": len(output_segments),
                    "sourceText": _segments_preview(output_segments, "text"),
                    "translatedText": _segments_preview(output_segments, "translation"),
                },
            )
        else:
            output_segments = segments
            self._update_context(output_segments)

        self._append_recent_text(
            kind="segment",
            utterance_id=utterance.id,
            source_text=_segments_text(output_segments, "text"),
            translated_text=_segments_text(output_segments, "translation"),
        )
        return {
            "type": "segment",
            "id": utterance.id,
            "sourceLanguage": detected_language,
            "targetLanguage": self.config.target_language if self.config.translate_enabled else None,
            "translationEnabled": self.config.translate_enabled,
            "chineseScript": normalize_chinese_script(self.config.chinese_script),
            "start": utterance.start,
            "end": utterance.end,
            "forced": utterance.forced,
            "segments": output_segments,
        }

    def _register_connection(self) -> None:
        now = time.time()
        with _LIVE_CONNECTIONS_LOCK:
            _LIVE_PROCESSORS[self.session_id] = self
            _LIVE_CONNECTIONS[self.session_id] = {
                "id": self.session_id,
                "status": "connected",
                "mode": "translate" if self.config.translate_enabled else "asr",
                "connectedAt": now,
                "updatedAt": now,
                "clientIp": self.client_ip,
                "url": str(self.websocket.url),
                "userAgent": self.websocket.headers.get("user-agent", ""),
                "sourceLanguage": self.config.source_language or "auto",
                "targetLanguage": self.config.target_language if self.config.translate_enabled else "",
                "translationEnabled": self.config.translate_enabled,
                "translationEngine": self.config.translation_engine if self.config.translate_enabled else None,
                "asrModel": self.config.asr_model_key,
                "translationModel": self.config.translation_model_key if self.config.translate_enabled else "",
                "device": self.config.device,
                "deviceIndex": self.config.device_index,
                "computeType": self.config.compute_type,
                "asrRuntime": asr_runtime_status(
                    self.config.device,
                    self.config.device_index,
                    self.config.compute_type,
                ),
                "nCtx": self.config.n_ctx,
                "nGpuLayers": self.config.n_gpu_layers,
                "translationGpuIndex": self.config.translation_gpu_index,
                "translationRuntime": (
                    {
                        "available": True,
                        "mode": "online",
                        "provider": (self.config.online_translation_settings or {}).get("onlineProvider") or "deepseek",
                        "model": self.config.translation_model_key,
                    }
                    if self.config.translate_enabled and self.config.translation_engine == "online"
                    else gguf_runtime_status(
                        self.config.n_gpu_layers,
                        self.config.translation_gpu_index,
                    )
                    if self.config.translate_enabled
                    else None
                ),
                "codec": self.config.codec,
                "sampleRate": self.config.sample_rate,
                "channels": self.config.channels,
                "silenceMs": self.config.silence_ms,
                "maxSegmentMs": self.config.max_segment_ms,
                "minSegmentMs": self.config.min_segment_ms,
                "partialBeamSize": self.config.partial_beam_size,
                "finalBeamSize": self.config.final_beam_size,
                "vadThreshold": self.config.vad_threshold,
                "chineseScript": normalize_chinese_script(self.config.chinese_script),
                "audioChunks": 0,
                "receivedBytes": 0,
                "streamSeconds": 0,
                "queuedSegments": 0,
                "partialCount": 0,
                "segmentCount": 0,
                "errorCount": 0,
                "recentTexts": [],
                "pendingUtterances": [],
                "currentProcessing": None,
                "lastProcessed": None,
                "processingLogs": [
                    {
                        "at": now,
                        "level": "info",
                        "message": "连接已建立，等待电视端发送音频",
                    }
                ],
                "lastEvent": "connected",
            }

    def _unregister_connection(self) -> None:
        should_clear_caches = False
        with _LIVE_CONNECTIONS_LOCK:
            _LIVE_CONNECTIONS.pop(self.session_id, None)
            _LIVE_PROCESSORS.pop(self.session_id, None)
            should_clear_caches = not _LIVE_CONNECTIONS
        if should_clear_caches:
            self._clear_runtime_caches()

    def _clear_runtime_caches(self) -> None:
        cleared_asr = clear_asr_model_cache()
        cleared_gguf = clear_gguf_model_cache()
        if cleared_asr or cleared_gguf:
            gc.collect()
            log_event(
                "info",
                "直播连接已清空，模型缓存已释放",
                category="live",
                details={
                    "sessionId": self.session_id,
                    "clearedAsrModels": cleared_asr,
                    "clearedGgufModels": cleared_gguf,
                },
            )

    def _update_connection_counters(self, **changes: Any) -> None:
        with _LIVE_CONNECTIONS_LOCK:
            connection = _LIVE_CONNECTIONS.get(self.session_id)
            if not connection:
                return
            for key, value in changes.items():
                if key in {
                    "audioChunks",
                    "receivedBytes",
                    "partialCount",
                    "segmentCount",
                    "errorCount",
                    "queuedSegments",
                }:
                    connection[key] = max(0, int(connection.get(key, 0)) + int(value))
                else:
                    connection[key] = value
            connection["updatedAt"] = time.time()

    def _set_runtime_status(
        self,
        asr_runtime: dict[str, Any] | None = None,
        translation_runtime: dict[str, Any] | None = None,
    ) -> None:
        changes: dict[str, Any] = {}
        if asr_runtime:
            changes["asrRuntime"] = asr_runtime
        if translation_runtime:
            changes["translationRuntime"] = translation_runtime
        if changes:
            _update_live_connection(self.session_id, **changes)

    def _append_recent_text(
        self,
        kind: str,
        utterance_id: str,
        source_text: str,
        translated_text: str,
    ) -> None:
        text = translated_text or source_text
        if not text:
            return
        with _LIVE_CONNECTIONS_LOCK:
            connection = _LIVE_CONNECTIONS.get(self.session_id)
            if not connection:
                return
            recent = list(connection.get("recentTexts") or [])
            recent.append(
                {
                    "type": kind,
                    "id": utterance_id,
                    "at": time.time(),
                    "sourceText": source_text,
                    "translatedText": translated_text,
                    "displayText": text,
                }
            )
            connection["recentTexts"] = recent[-8:]
            connection["updatedAt"] = time.time()

    def _utterance_summary(
        self,
        utterance: LiveUtterance,
        status: str,
        message: str,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "id": utterance.id,
            "sequence": utterance.id.rsplit("-", 1)[-1],
            "status": status,
            "message": message,
            "start": utterance.start,
            "end": utterance.end,
            "duration": max(0.0, utterance.end - utterance.start),
            "forced": utterance.forced,
            **extra,
        }

    def _append_processing_log(
        self,
        message: str,
        utterance: LiveUtterance | None = None,
        level: str = "info",
        **extra: Any,
    ) -> None:
        now = time.time()
        item = {
            "at": now,
            "level": level,
            "message": message,
            **extra,
        }
        if utterance is not None:
            item.update(
                {
                    "utteranceId": utterance.id,
                    "sequence": utterance.id.rsplit("-", 1)[-1],
                    "duration": max(0.0, utterance.end - utterance.start),
                }
            )

        with _LIVE_CONNECTIONS_LOCK:
            connection = _LIVE_CONNECTIONS.get(self.session_id)
            if not connection:
                return
            logs = list(connection.get("processingLogs") or [])
            last = logs[-1] if logs else {}
            if (
                last.get("message") == item.get("message")
                and last.get("utteranceId") == item.get("utteranceId")
                and last.get("level") == item.get("level")
            ):
                logs[-1] = {**last, **item}
            else:
                logs.append(item)
            connection["processingLogs"] = logs[-12:]
            connection["updatedAt"] = now

    def _append_pending_utterance(self, utterance: LiveUtterance) -> None:
        pending_item = self._utterance_summary(
            utterance,
            status="queued",
            message="排队等待处理",
            queuedAt=time.time(),
        )
        with _LIVE_CONNECTIONS_LOCK:
            connection = _LIVE_CONNECTIONS.get(self.session_id)
            if not connection:
                return
            pending = [
                item
                for item in list(connection.get("pendingUtterances") or [])
                if item.get("id") != utterance.id
            ]
            pending.append(pending_item)
            connection["pendingUtterances"] = pending[-12:]
            connection["updatedAt"] = time.time()
        self._append_processing_log("收到音频，已加入处理队列", utterance, queueSize=self._queue.qsize())

    def _start_processing_utterance(self, utterance: LiveUtterance) -> None:
        processing = self._utterance_summary(
            utterance,
            status="processing",
            message="准备处理音频",
            queuedAt=None,
            startedAt=time.time(),
        )
        with _LIVE_CONNECTIONS_LOCK:
            connection = _LIVE_CONNECTIONS.get(self.session_id)
            if not connection:
                return
            connection["pendingUtterances"] = [
                item
                for item in list(connection.get("pendingUtterances") or [])
                if item.get("id") != utterance.id
            ]
            connection["currentProcessing"] = processing
            connection["lastEvent"] = "processing"
            connection["updatedAt"] = time.time()
        self._append_processing_log("开始处理这段音频", utterance)

    def _update_current_processing(self, **changes: Any) -> None:
        with _LIVE_CONNECTIONS_LOCK:
            connection = _LIVE_CONNECTIONS.get(self.session_id)
            if not connection:
                return
            current = dict(connection.get("currentProcessing") or {})
            if not current:
                return
            current.update({key: value for key, value in changes.items() if value is not None})
            current["updatedAt"] = time.time()
            connection["currentProcessing"] = current
            connection["updatedAt"] = time.time()

    def _finish_processing_utterance(
        self,
        utterance: LiveUtterance,
        status: str,
        message: str,
        source_text: str = "",
        error: str = "",
    ) -> None:
        finished = self._utterance_summary(
            utterance,
            status=status,
            message=message,
            finishedAt=time.time(),
            sourceText=source_text,
            error=error,
        )
        with _LIVE_CONNECTIONS_LOCK:
            connection = _LIVE_CONNECTIONS.get(self.session_id)
            if not connection:
                return
            connection["currentProcessing"] = None
            connection["lastProcessed"] = finished
            connection["updatedAt"] = time.time()
        level = "error" if status == "error" else "info"
        self._append_processing_log(message, utterance, level=level, sourceText=source_text, error=error)

    def _update_context(self, segments: list[dict[str, Any]]) -> None:
        source_parts = [str(segment.get("text") or "").strip() for segment in segments]
        translation_parts = [
            f"Source: {str(segment.get('text') or '').strip()}\n"
            f"Translation: {str(segment.get('translation') or '').strip()}"
            for segment in segments
            if segment.get("text") or segment.get("translation")
        ]
        self._source_context = self._trim(" ".join(part for part in source_parts if part), 500)
        self._translation_context = self._trim(
            "\n".join([self._translation_context, *translation_parts]).strip(),
            800,
        )

    def _detect_speech_end(self, content: bytes) -> float | None:
        audio = pcm_s16le_to_float32(
            content,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
            target_rate=VAD_SAMPLE_RATE,
        )
        if audio.size < 256:
            return None
        timestamps = get_speech_timestamps(
            audio,
            VadOptions(
                threshold=self.config.vad_threshold,
                min_speech_duration_ms=64,
                min_silence_duration_ms=100,
                speech_pad_ms=0,
            ),
            sampling_rate=VAD_SAMPLE_RATE,
        )
        if not timestamps:
            return None
        return float(timestamps[-1]["end"]) / VAD_SAMPLE_RATE

    async def _send_json(self, payload: dict[str, Any]) -> None:
        async with self._send_lock:
            try:
                await self.websocket.send_json(payload)
            except (RuntimeError, WebSocketDisconnect):
                pass

    def _aligned(self, content: bytes) -> bytes:
        usable_bytes = len(content) - (len(content) % self._bytes_per_frame)
        return content[:usable_bytes]

    def _bytes_for_seconds(self, seconds: float) -> int:
        return int(round(seconds * self.config.sample_rate)) * self._bytes_per_frame

    def _frames_in_bytes(self, content: bytes | bytearray) -> int:
        return len(content) // self._bytes_per_frame

    @staticmethod
    def _append_limited(buffer: bytearray, content: bytes, max_bytes: int) -> None:
        buffer.extend(content)
        if len(buffer) > max_bytes:
            del buffer[: len(buffer) - max_bytes]

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[-limit:]
