from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
import ctypes
from pathlib import Path

import uvicorn

_DLC_DLL_HANDLES: list[ctypes.WinDLL] = []


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
    configure_optional_gguf_cuda_dlc(root)

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
    from app.main import app

    uvicorn.run(app, host=host, port=port, log_level="info")


def configure_optional_gguf_cuda_dlc(root: Path) -> None:
    dlc_internal = root / "gguf-cuda-dlc" / "_internal"
    if not dlc_internal.exists():
        return

    sys.path.insert(0, str(dlc_internal))
    dll_dirs = [
        dlc_internal,
        dlc_internal / "llama_cpp" / "lib",
    ]
    for dll_dir in dll_dirs:
        if dll_dir.exists():
            os.add_dll_directory(str(dll_dir))
    path_entries = [str(dll_dir) for dll_dir in dll_dirs if dll_dir.exists()]
    existing_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join([*path_entries, existing_path]) if path_entries else existing_path

    dlls_to_preload = [
        dlc_internal / "cudart64_12.dll",
        dlc_internal / "cublasLt64_12.dll",
        dlc_internal / "cublas64_12.dll",
        dlc_internal / "llama_cpp" / "lib" / "ggml-cuda.dll",
    ]
    for dll_path in dlls_to_preload:
        if not dll_path.exists():
            continue
        try:
            _DLC_DLL_HANDLES.append(ctypes.WinDLL(str(dll_path)))
        except OSError as exc:
            print(f"可选 GPU DLC 运行库预加载失败：{dll_path.name}: {exc}")


if __name__ == "__main__":
    main()
