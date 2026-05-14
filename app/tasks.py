from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TaskRecord:
    id: str
    kind: str
    label: str
    status: str = "queued"
    progress: float | None = None
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


class TaskStore:
    def __init__(self, max_workers: int = 1) -> None:
        self._records: dict[str, TaskRecord] = {}
        self._futures: dict[str, Future[Any]] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(
        self,
        kind: str,
        label: str,
        worker: Callable[[str, Callable[..., None]], dict[str, Any] | None],
    ) -> TaskRecord:
        task_id = uuid.uuid4().hex
        record = TaskRecord(id=task_id, kind=kind, label=label)
        with self._lock:
            self._records[task_id] = record

        def update(**changes: Any) -> None:
            self.update(task_id, **changes)

        def run() -> None:
            self.update(task_id, status="running", progress=0.0, message="Started")
            try:
                result = worker(task_id, update)
                self.update(
                    task_id,
                    status="succeeded",
                    progress=1.0,
                    message="Finished",
                    result=result or {},
                )
            except Exception as exc:  # noqa: BLE001 - surfaced to local UI
                self.update(task_id, status="failed", error=str(exc), message="Failed")

        future = self._executor.submit(run)
        with self._lock:
            self._futures[task_id] = future
        return record

    def update(self, task_id: str, **changes: Any) -> None:
        with self._lock:
            record = self._records[task_id]
            for key, value in changes.items():
                setattr(record, key, value)
            record.updated_at = time.time()

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._records.get(task_id)

    def list(self) -> list[TaskRecord]:
        with self._lock:
            return sorted(self._records.values(), key=lambda item: item.created_at, reverse=True)
