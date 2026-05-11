# TV Captioner

TV Captioner 是一个面向电视/安卓设备的实时字幕实验项目：安卓端采集短音频片段，发送到 Windows 后端；后端在本地完成语音识别和翻译，再把字幕结果返回给前端显示。

当前项目还处在早期版本，重点是跑通本地 ASR、GGUF 翻译模型和安卓悬浮字幕的完整链路。

## 项目结构

```text
tv-captioner/
├── client-android/      # Android 客户端，负责录音、设置后端地址、显示悬浮字幕
└── services-backend/    # Windows 后端，负责 ASR、翻译、网页控制台和测试接口
```

## 当前功能

- Android 客户端
  - 配置 Windows 后端地址和端口。
  - 选择源语言、目标语言、ASR 模型和翻译模型。
  - 通过麦克风采集短音频片段。
  - 调用后端接口获取原文和翻译字幕。
  - 使用系统悬浮窗显示字幕，并支持调节字幕大小、背景和位置。

- Windows 后端
  - 提供网页控制台：`http://127.0.0.1:8765`
  - 检查 ASR 模型和 GGUF 翻译模型状态。
  - 支持本地音频转写、翻译测试和字幕文件输出。
  - 接收安卓端上传的直播音频片段。
  - 使用 `faster-whisper` 做语音识别，使用 `llama-cpp-python` 加载本地 GGUF 翻译模型。

## 快速开始

### 1. 启动 Windows 后端

进入后端目录：

```powershell
cd services-backend
```

第一次使用：

```powershell
.\首次安装并启动.bat
```

以后启动：

```powershell
.\启动后端.bat
```

启动后打开：

```text
http://127.0.0.1:8765
```

后端默认端口是 `8765`。如果安卓真机要访问后端，手机/电视和 Windows 主机需要在同一个局域网，并在客户端里填写 Windows 主机的局域网 IP，不能填写 `127.0.0.1`。

### 2. 准备模型

仓库不包含模型文件。请按后端网页提示手动下载并放到对应目录：

```text
services-backend/models/asr/
services-backend/models/translate/
```

ASR 推荐先用 faster-whisper / CTranslate2 格式模型做测试。翻译模型使用 GGUF 文件，例如 Qwen Instruct 的 GGUF 版本。

模型文件通常很大，不建议直接提交到 Git。当前 `.gitignore` 已经排除了 `services-backend/models/`。

### 3. 构建 Android 客户端

进入客户端目录：

```powershell
cd client-android
```

构建调试包：

```powershell
.\gradlew.bat assembleDebug
```

APK 输出位置：

```text
client-android/app/build/outputs/apk/debug/app-debug.apk
```

Android 首次使用悬浮字幕时，需要授予麦克风、通知和“显示在其他应用上层”权限。

## 开发环境

后端主要依赖：

- Python
- FastAPI
- faster-whisper
- llama-cpp-python
- uvicorn

Android 端主要配置：

- Android Gradle Plugin `7.4.2`
- `compileSdk 34`
- `minSdk 26`
- Java 8

## 重要说明

- 后端不负责拉直播流，也不做直播切片。
- 当前版本不依赖 FFmpeg，也不依赖 Ollama。
- 安卓端当前使用麦克风采集环境声音；如果后续要直接采集系统内声音，需要接入 Android MediaProjection。
- `services-backend/data/`、`services-backend/models/`、构建产物、日志和本机配置不会提交到仓库。

## 更多文档

- [Android 客户端说明](client-android/README.md)
- [Windows 后端说明](services-backend/README.md)
- [快速部署说明](services-backend/快速部署说明.md)
- [打包说明](services-backend/打包说明.md)

