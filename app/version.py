from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_NAME = "TV Captioner Backend"
APP_VERSION = "0.2"


def version_info() -> dict[str, Any]:
    packaged = bool(getattr(sys, "frozen", False))
    runtime_path = Path(sys.executable).resolve() if packaged else Path(__file__).resolve().parents[1]
    timestamp_path = runtime_path if packaged else Path(__file__).resolve()
    modified_at = None
    try:
        modified_at = datetime.fromtimestamp(timestamp_path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        pass

    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "packaged": packaged,
        "runtime": "packaged" if packaged else "source",
        "executable": str(runtime_path),
        "executableModifiedAt": modified_at,
    }
