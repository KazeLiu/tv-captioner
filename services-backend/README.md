# TV Captioner Windows 后端

TV Captioner Windows 后端负责接收安卓端上传的音频片段，在本地完成语音识别和翻译，并返回字幕结果。

```text
Android/TV 前端采集直播音频片段 -> Windows 后端接收 -> 本地 ASR -> 本地 GGUF 翻译 -> 返回字幕
```

后端不负责拉直播流，不做直播切片，不需要 FFmpeg，也不使用 Ollama。

## 当前功能

- 网页控制台：`http://127.0.0.1:8765`
- 转写环境监测：ASR 模型状态检查
- 翻译环境监测：GGUF 翻译模型文件检查
- 模型按钮只打开网页，不由后端下载
- 本地文件 ASR 测试
- 本地文件转写 + 翻译测试，输出原文 SRT、翻译 SRT、双语 SRT 和 JSON
- 接收前端上传的直播音频片段
- 日志页面：记录接口调用、音频接收、转写原文、翻译结果、warning 和 error；日志自动保留最近 10 天

## 启动

推荐使用便携版或安装包。便携版会内置 Python 运行时、后端依赖和 GGUF 运行库，不需要手动安装 `llama-cpp-python`。构建方式见：

```text
打包说明.md
```

源码目录也可以直接启动：

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
services-backend\models\asr\large-v2
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

便携版/安装包会内置 GGUF 运行库，只需要准备 `.gguf` 模型文件。

网页“翻译”标签页会列出 Qwen GGUF 模型。下载 `.gguf` 文件后，放到对应目录，例如：

```text
services-backend\models\translate\qwen2.5-3b-instruct-gguf
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

## 安卓端调用建议

短音频片段可以直接用同步接口：安卓端以 `multipart/form-data` 上传音频，同时带上目标语种，然后等待 JSON 返回。

```http
POST /api/audio/translate
Content-Type: multipart/form-data

file=<audio bytes>
source_language=auto
target_language=Chinese
asr_model=large-v2
translation_model=qwen2.5-1.5b-instruct-gguf
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
