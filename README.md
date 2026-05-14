# TV Captioner Backend

TV Captioner Backend 是项目的 Windows 后端服务。它提供网页控制台、本地语音识别、本地 GGUF 翻译、字幕文件输出，以及给外部前端/客户端调用的音频片段接口。

```text
外部前端/客户端采集音频片段 -> 后端接收 -> 本地 ASR -> 本地 GGUF 翻译 -> 返回字幕
```

当前仓库只保留后端。原 `services-backend` 目录里的内容已经提升到项目根目录，原 Android 客户端目录已移除。后端不负责拉直播流，不做直播切片，不需要 FFmpeg，也不使用 Ollama。

## 项目结构

```text
tv-captioner/
├── app/                 # FastAPI 应用、模型检查、任务和接口实现
├── app/static/          # 网页控制台静态资源
├── packaging/           # 安装包配置和打包依赖
├── run_server.py        # 便携版/安装包入口
├── setup.ps1            # 创建虚拟环境并安装依赖
├── start.ps1            # 开发环境启动脚本
├── build-portable.ps1   # 构建便携版
└── requirements.txt     # 后端运行依赖
```

运行时生成的 `data/`、`models/`、`build/`、`dist/`、日志和 `.spec` 文件都在根目录下，并已被 `.gitignore` 忽略。

源码调试默认安装 CPU 版 GGUF 运行库。需要在源码模式测试 GGUF 翻译 GPU offload 时，可在安装基础依赖后运行：

```powershell
.\.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps -r requirements-gguf-cuda.txt
```

## 当前功能

- 网页控制台：`http://127.0.0.1:8765`
- 转写环境监测：ASR 模型状态检查
- 翻译环境监测：GGUF 翻译模型文件检查
- 模型按钮只打开网页，不由后端下载
- 本地文件 ASR 测试
- 本地文件转写 + 翻译测试，输出原文 SRT、翻译 SRT、双语 SRT 和 JSON
- 接收外部前端/客户端上传的直播音频片段
- WebSocket 实时接收 PCM 音频流，使用 faster-whisper 内置 Silero VAD 断句后转写和翻译
- 日志页面：记录接口调用、音频接收、转写原文、翻译结果、warning 和 error；日志自动保留最近 10 天

## 启动

推荐使用便携版或安装包。便携版基础包会内置 Python 运行时、后端依赖和 GGUF CPU 运行能力；GGUF 翻译 GPU 加速以单独的 CUDA DLC 文件夹发布。构建方式见：

```text
打包说明.md
```

源码目录可以直接启动：

第一次双击：

```text
首次安装并启动.bat
```

以后双击：

```text
启动后端.bat
```

## ASR 模型

网页里的“打开模型页”会打开 Hugging Face 页面。下载后，把模型文件放到对应目录：

```text
models\asr\large-v2
```

页面会列出常用 faster-whisper / distil-whisper ASR 模型，包括多语言、英语专用 `.en`、large、turbo、distil 系列。建议先用 `large-v2` 做质量基线，再用 `large-v3-turbo` 或 distil 系列测实时延迟。

如果你已经在 PotPlayer 里下载过模型，可以在网页“自定义模型”里填本地目录。当前后端直接支持的是 faster-whisper / CTranslate2 目录，基本结构需要包含：

```text
model.bin
config.json
tokenizer.json 或 vocabulary.json
```

当前直接支持 faster-whisper / CTranslate2 目录，暂不支持 whisper.cpp 的单个 `.bin` / `.gguf` 文件。

## 翻译模型

翻译不会用 Ollama。当前使用内置的 `llama-cpp-python` 直接加载 GGUF 模型，更接近 PotPlayer 调 `whisper.cpp` 的模式：下载模型文件，然后程序直接使用。

便携版/安装包基础包可直接用 CPU 加载 GGUF 模型，只需要准备 `.gguf` 模型文件。需要 GGUF 翻译 GPU 加速时，另行下载 `TVCaptionerBackend-GGUF-CUDA-DLC`，把其中的 `gguf-cuda-dlc` 文件夹复制到 `TVCaptionerBackend` 根目录，然后在“直播 > 高级设备参数”里设置 GGUF 翻译 GPU 层数。以后更新基础包时保留这个 `gguf-cuda-dlc` 文件夹即可继续使用 GPU 版运行库。

网页“翻译”标签页会列出 Qwen GGUF 模型。下载 `.gguf` 文件后，放到对应目录，例如：

```text
models\translate\qwen2.5-3b-instruct-gguf
```

也可以在“翻译”标签页添加自定义翻译模型。这里和 ASR 不一样：翻译模型当前按 GGUF 方案走，所以可以选择单个 `.gguf` 文件，也可以选择包含 `.gguf` 文件的目录。校验会检查路径是否存在、后缀是否为 `.gguf`，以及目录里是否真的有模型文件。

“翻译测试”会先用 ASR 转写音频，再用选中的 GGUF 模型翻译字幕。

## 直播音频片段 API

创建会话：

```http
POST /api/live/sessions
Content-Type: application/json

{
  "sourceLanguage": "ja",
  "targetLanguage": "Chinese",
  "codec": "pcm_s16le",
  "sampleRate": 16000,
  "channels": 1
}
```

上传音频片段：

```http
POST /api/live/sessions/{sessionId}/chunks
Content-Type: multipart/form-data

chunk=<audio bytes>
sequence=1
start_ms=0
duration_ms=1000
```

## 实时 WebSocket 字幕 API

实时模式用于新前端直接把二进制音频流推给后端。当前约定前端发送原始 PCM：

```text
codec=pcm_s16le
sampleRate=16000
channels=1
```

连接地址示例：

```text
ws://127.0.0.1:8765/api/live/ws?sourceLanguage=auto&targetLanguage=Chinese&asrModel=<ready-asr-model-key>&translationModel=<ready-translation-model-key>&sampleRate=16000&channels=1&silenceMs=300&maxSegmentMs=5000&chineseScript=simplified
```

连接建立后，前端持续发送二进制 PCM 块即可。建议每块 20-100ms，后端会为每个 WebSocket 连接维护独立缓冲区、VAD 状态和处理队列。Silero VAD 检测到人声结束后，若静音持续达到 `silenceMs`，后端会把当前句子送入 ASR；如果新闻主播连续说话没有明显停顿，后端也会在 `maxSegmentMs` 达到后强制切出一段，再带上上一段字幕上下文进行翻译。

双 GPU 服务器可以显式选卡：`device=cuda&deviceIndex=1` 指定 ASR 使用第二张 GPU；GGUF 翻译如果开启 GPU 层数，则用 `nGpuLayers=<层数>&translationGpuIndex=1` 指定翻译主 GPU。强制 CPU 时用 `device=cpu&nGpuLayers=0`。

如果客户端不传这些设备参数，后端会使用后台“直播”页签里的默认设备设置。对应接口是 `GET/PUT /api/live/defaults`，当前在线 WebSocket 连接可通过 `GET /api/live/connections` 查看；后台页面会用 `GET /api/live/connections/events` 的 SSE 长链接实时刷新，并显示最近几条转录/翻译文本。

中文输出默认转成简体中文。可用 `chineseScript=simplified`、`chineseScript=traditional` 或 `chineseScript=original` 切换；`sourceLanguage=zh` 只表示中文语音，不负责区分简体/繁体。

如果只需要实时语音转文字，不需要翻译模型，使用：

```text
ws://127.0.0.1:8765/api/live/asr-ws?sourceLanguage=auto&asrModel=<ready-asr-model-key>&sampleRate=16000&channels=1&silenceMs=300&maxSegmentMs=5000&chineseScript=simplified
```

这个接口返回 `translationEnabled=false`，前端直接显示 `segments[].text`。

前端可发送 JSON 文本控制消息：

```json
{"type": "flush"}
```

返回消息里最重要的是 `segment`：

```json
{
  "type": "segment",
  "id": "session-0",
  "sourceLanguage": "ja",
  "targetLanguage": "Chinese",
  "start": 1.25,
  "end": 4.8,
  "forced": false,
  "segments": [
    {
      "start": 1.32,
      "end": 4.2,
      "text": "原文片段",
      "translation": "中文片段"
    }
  ]
}
```

## 前端调用建议

短音频片段可以直接用同步接口：外部前端/客户端以 `multipart/form-data` 上传音频，同时带上目标语种，然后等待 JSON 返回。

```http
POST /api/audio/translate
Content-Type: multipart/form-data

file=<audio bytes>
source_language=auto
target_language=Chinese
asr_model=large-v2
translation_model=qwen2.5-1.5b-instruct-gguf
device=cuda
device_index=0
compute_type=float16
n_gpu_layers=0
translation_gpu_index=0
```

返回值里重点读：

```json
{
  "sourceLanguage": "ja",
  "targetLanguage": "Chinese",
  "sourceText": "识别出来的原文",
  "translatedText": "翻译后的中文",
  "segments": [
    {
      "start": 0.0,
      "end": 2.4,
      "text": "原文片段",
      "translation": "中文片段"
    }
  ]
}
```

长音频或可能处理很久的片段，建议继续走异步任务接口：`POST /api/jobs/translate-test` 创建任务，再轮询 `GET /api/tasks/{taskId}`，完成后读取 `result.outputs.json`。
