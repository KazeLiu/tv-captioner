from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from app.main import app


def runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> None:
    root = runtime_dir()
    os.environ["TV_CAPTIONER_HOME"] = str(root)
    os.environ["PYTHONPATH"] = ""
    os.environ["PYTHONHOME"] = ""
    os.environ["PYTHONNOUSERSITE"] = "1"

    host = os.environ.get("TV_CAPTIONER_HOST", "0.0.0.0")
    port = int(os.environ.get("TV_CAPTIONER_PORT", "8765"))
    local_url = f"http://127.0.0.1:{port}"
    lan_hint = f"http://<这台电脑的局域网IP>:{port}"
    print("TV Captioner 后端正在启动...")
    print(f"本机网页控制台: {local_url}")
    print(f"手机/模拟器访问地址: {lan_hint}")
    print("关闭这个窗口即可停止后端。")

    def open_browser() -> None:
        if os.environ.get("TV_CAPTIONER_NO_BROWSER") == "1":
            return
        time.sleep(1.5)
        webbrowser.open(local_url)

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
