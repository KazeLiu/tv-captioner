# TV Captioner Backend AI 接口调用说明

本文档给外部前端 AI / 自动化代理使用。请严格按本文档调用，不要猜接口路径。

默认后端地址：

```text
http://127.0.0.1:8765
ws://127.0.0.1:8765
```

## 重要结论

1. 获取模型列表时，优先调用：

```http
GET /api/models
```

也可以分别调用：

```text
GET /api/models/asr
GET /api/models/translate
```

2. `/api/status` 是环境状态接口，可以不带参数调用。`asr_model` 只表示“检查哪个首选 ASR 模型”，不是获取模型列表必须参数。

3. `/api/models/asr/custom` 和 `/api/models/translate/custom` 只返回自定义模型，不返回内置模型。一般前端不要用它们做完整模型列表。

4. 如果只需要语音转文字，不需要翻译或双语字幕，请使用：

```text
ws://127.0.0.1:8765/api/live/asr-ws
```

不要连接 `/api/live/ws`，因为 `/api/live/ws` 会要求翻译模型可用。

5. WebSocket 实时字幕接口只接收原始 PCM 二进制音频流，当前推荐：

```text
codec=pcm_s16le
sampleRate=16000
channels=1
```

不要把 WebM / Opus / AAC / MP3 容器数据直接发给 WebSocket。

6. 中文转写默认会输出简体中文。需要切换时传：

```text
chineseScript=simplified   简体中文，默认
chineseScript=traditional  繁体中文
chineseScript=original     保留模型原始输出
```

注意：`sourceLanguage=zh` 只表示“中文语音”，不负责区分简体/繁体。简体/繁体是输出文字格式，由 `chineseScript` 控制。

## 正确调用顺序

1. 调用 `/api/models` 获取模型列表。
2. 从返回值里筛选 `ready === true` 的 ASR 模型和翻译模型。
3. 如果没有可用 ASR 模型或翻译模型，停止实时字幕流程，并提示用户放置模型文件。
4. 用选中的模型 key 建立 `/api/live/ws` WebSocket。
5. WebSocket 建立后，持续发送 PCM 二进制块。
6. 收到 `type: "partial"` 可以先显示临时字幕；收到 `type: "segment"` 后用最终字幕替换对应临时字幕，并把 `segments[].translation` 显示成字幕。

如果只需要实时语音转文字：

1. 调用 `/api/models` 获取模型列表。
2. 从 `readyAsrModels` 里选择 ASR 模型。
3. 建立 `/api/live/asr-ws` WebSocket。
4. 持续发送 PCM 二进制块。
5. 收到 `type: "partial"` 可以先显示临时字幕；收到 `type: "segment"` 后用最终字幕替换对应临时字幕，并显示 `segments[].text`。

## 获取可用模型

请求：

```http
GET /api/models
```

返回示例：

```json
{
  "asrModels": [],
  "translationModels": [],
  "readyAsrModels": [],
  "readyTranslationModels": []
}
```

字段含义：

```text
asrModels                 全部 ASR 模型列表，包含内置和自定义
translationModels         全部 GGUF 翻译模型列表，包含内置和自定义
readyAsrModels            已可用 ASR 模型列表
readyTranslationModels    已可用 GGUF 翻译模型列表
ready                     单个模型是否可用
key                       后续接口要传的模型标识
path                      本地模型路径
validation.errors         模型不可用原因
```

可用模型筛选示例：

```js
async function getReadyModels(baseUrl = "http://127.0.0.1:8765") {
  const response = await fetch(`${baseUrl}/api/models`);
  if (!response.ok) {
    throw new Error(`models failed: ${response.status}`);
  }
  const models = await response.json();

  const asrModels = models.readyAsrModels || (models.asrModels || []).filter((model) => model.ready);
  const translationModels =
    models.readyTranslationModels || (models.translationModels || []).filter((model) => model.ready);

  return {
    models,
    asrModels,
    translationModels,
    defaultAsrModel: asrModels[0]?.key || null,
    defaultTranslationModel: translationModels[0]?.key || null,
  };
}
```

常见失败原因：

```text
asrModels 为空或全是 ready=false:
  用户还没有把 faster-whisper / CTranslate2 模型放到 models/asr/<model-key>。

translationModels 为空或全是 ready=false:
  用户还没有把 .gguf 文件放到 models/translate/<model-key>。

translationReady=false:
  可能没有 GGUF 文件，也可能缺少 llama-cpp-python 运行库。
```

如需检查环境总状态，可以调用：

```http
GET /api/status
```

如果想让状态页检查某个特定 ASR 模型，可以传：

```http
GET /api/status?asr_model=<asr-model-key>
```

## WebSocket 实时字幕接口

### 实时双语字幕

连接地址：

```text
ws://127.0.0.1:8765/api/live/ws
```

推荐完整示例：

```text
ws://127.0.0.1:8765/api/live/ws?sourceLanguage=auto&targetLanguage=Chinese&asrModel=<ready-asr-model-key>&translationModel=<ready-translation-model-key>&codec=pcm_s16le&sampleRate=16000&channels=1&silenceMs=300&maxSegmentMs=5000&chineseScript=simplified
```

查询参数：

```text
sourceLanguage      源语言；auto 或空字符串表示自动检测；也可传 ja/en/ko/zh 等
targetLanguage      目标语言；默认 Chinese
asrModel            ASR 模型 key，必须来自 ready ASR 模型
translationModel    翻译模型 key，必须来自 ready 翻译模型
device              faster-whisper device，默认 auto
computeType         faster-whisper compute_type，默认 auto
nCtx                llama.cpp 上下文长度，默认 4096
nGpuLayers          llama.cpp GPU 层数，默认 0
codec               当前只支持 pcm_s16le
sampleRate          PCM 采样率，推荐 16000
channels            声道数，支持 1 或 2，推荐 1
silenceMs           VAD 断句静音时长，默认 300，最小 200
maxSegmentMs        单次最终转写音频最大时长，默认 5000；数字越大，最终 ASR 音频越长，对后端性能要求越高；新闻频道建议 4000-6000
minSegmentMs        小于该时长的片段会丢弃，默认 300
vadThreshold        VAD 阈值，默认 0.5
chineseScript       中文输出书写格式，默认 simplified；可选 simplified/traditional/original
```

建立连接后，服务端先返回：

```json
{
  "type": "ready",
  "sessionId": "xxxxxxxx",
  "codec": "pcm_s16le",
  "sampleRate": 16000,
  "channels": 1
}
```

之后前端持续发送二进制 PCM 块。建议每块 20-100ms。

前端可发送 JSON 文本控制消息：

```json
{"type": "flush"}
```

```json
{"type": "ping"}
```

```json
{"type": "close"}
```

服务端可能返回的消息类型：

```text
ready              连接已准备好
speech_start       VAD 检测到人声开始
partial            临时 ASR 字幕预览，最终 segment 尚未生成
speech_end         VAD 判断一句话结束，已进入处理队列
processing         某个断句片段正在 ASR/翻译
segment            已生成字幕结果
speech_discarded   片段太短，被丢弃
pong               ping 响应
error              参数或处理错误
```

`partial` 返回示例：

```json
{
  "type": "partial",
  "id": "partial-session-0",
  "finalId": "session-0",
  "start": 12.3,
  "end": 14.1,
  "translationEnabled": false,
  "chineseScript": "simplified",
  "segments": [
    {
      "id": "0",
      "start": 12.3,
      "end": 14.1,
      "text": "临时识别文本"
    }
  ]
}
```

`partial` 是临时 ASR 预览，不是最终字幕。后端会在人声还没有达到 `silenceMs` 或 `maxSegmentMs` 时按节流间隔生成，通常最多约每 800-1500ms 一次。同一连接同一时间最多只会跑一个 partial ASR 任务；如果任务返回时当前音频 buffer 已经结束或换成下一句，旧 partial 会被丢弃。

`partial.finalId` 一定等于之后最终 `segment.id`。前端可以用 `partial.id` 或 `partial-${finalId}` 原地更新临时字幕；收到 `segment.id === partial.finalId` 的最终消息时，移除该临时字幕并显示最终 `segment`。翻译开启时，`partial` 仍然只做 ASR 预览，可以只有 `segments[].text`，不保证有 `segments[].translation`；最终 `segment` 才会执行翻译。

`partial` 不会写入最终字幕队列，不会更新 source/translation 上下文，也不会影响最终 `segment.forced` 标记。

`segment` 返回示例：

```json
{
  "type": "segment",
  "id": "session-0",
  "sourceLanguage": "ja",
  "targetLanguage": "Chinese",
  "start": 1.25,
  "end": 4.8,
  "forced": false,
  "chineseScript": "simplified",
  "segments": [
    {
      "id": 1,
      "start": 1.32,
      "end": 4.2,
      "text": "原文片段",
      "translation": "中文片段"
    }
  ]
}
```

前端显示字幕时优先使用：

```text
segments[].translation
```

如果翻译为空，可回退显示：

```text
segments[].text
```

### 实时语音转文字

只需要转写原文、不需要翻译、不需要双语字幕时使用这个接口。

连接地址：

```text
ws://127.0.0.1:8765/api/live/asr-ws
```

完整示例：

```text
ws://127.0.0.1:8765/api/live/asr-ws?sourceLanguage=auto&asrModel=<ready-asr-model-key>&codec=pcm_s16le&sampleRate=16000&channels=1&silenceMs=300&maxSegmentMs=5000&chineseScript=simplified
```

查询参数：

```text
sourceLanguage      源语言；auto 或空字符串表示自动检测；也可传 ja/en/ko/zh 等
asrModel            ASR 模型 key，必须来自 ready ASR 模型
device              faster-whisper device，默认 auto
computeType         faster-whisper compute_type，默认 auto
codec               当前只支持 pcm_s16le
sampleRate          PCM 采样率，推荐 16000
channels            声道数，支持 1 或 2，推荐 1
silenceMs           VAD 断句静音时长，默认 300，最小 200
maxSegmentMs        单次最终转写音频最大时长，默认 5000；数字越大，最终 ASR 音频越长，对后端性能要求越高；新闻频道建议 4000-6000
minSegmentMs        小于该时长的片段会丢弃，默认 300
vadThreshold        VAD 阈值，默认 0.5
chineseScript       中文输出书写格式，默认 simplified；可选 simplified/traditional/original
```

这个接口不需要传 `targetLanguage` 和 `translationModel`。

返回消息格式和双语字幕接口基本一致，但：

```text
translationEnabled=false
targetLanguage=null
partial 只有 ASR 临时文本，finalId 等于之后最终 segment.id
segments[].translation 不存在
```

返回示例：

```json
{
  "type": "segment",
  "id": "session-0",
  "sourceLanguage": "ja",
  "targetLanguage": null,
  "translationEnabled": false,
  "start": 1.25,
  "end": 4.8,
  "forced": true,
  "chineseScript": "simplified",
  "segments": [
    {
      "id": 1,
      "start": 1.32,
      "end": 4.2,
      "text": "調査は朝日新聞社と東京大学の研究室が実施しました"
    }
  ]
}
```

前端显示时使用：

```text
segments[].text
```

## WebSocket 调用示例

### 双语字幕示例

```js
async function startLiveCaptioning() {
  const { asrModels, translationModels } = await getReadyModels();
  if (!asrModels.length) throw new Error("没有可用 ASR 模型");
  if (!translationModels.length) throw new Error("没有可用翻译模型");

  const params = new URLSearchParams({
    sourceLanguage: "auto",
    targetLanguage: "Chinese",
    asrModel: asrModels[0].key,
    translationModel: translationModels[0].key,
    codec: "pcm_s16le",
    sampleRate: "16000",
    channels: "1",
    silenceMs: "300",
    maxSegmentMs: "5000",
    chineseScript: "simplified",
  });

  const ws = new WebSocket(`ws://127.0.0.1:8765/api/live/ws?${params}`);
  ws.binaryType = "arraybuffer";

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "segment") {
      for (const segment of message.segments || []) {
        const subtitle = segment.translation || segment.text || "";
        if (subtitle) {
          console.log(`[${segment.start}-${segment.end}] ${subtitle}`);
        }
      }
    }
    if (message.type === "error") {
      console.error(message.message);
    }
  };

  return ws;
}
```

音频发送伪代码：

```js
// 必须发送 16-bit little-endian PCM，不是 Float32Array 原样字节。
// 如果前端从 Web Audio API 拿到 Float32，需要先转成 Int16 PCM。
function float32ToPcmS16le(float32) {
  const buffer = new ArrayBuffer(float32.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < float32.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return buffer;
}

// ws.send(float32ToPcmS16le(audioChunk));
```

### 只转文字示例

```js
async function startLiveTranscription() {
  const { asrModels } = await getReadyModels();
  if (!asrModels.length) throw new Error("没有可用 ASR 模型");

  const params = new URLSearchParams({
    sourceLanguage: "auto",
    asrModel: asrModels[0].key,
    codec: "pcm_s16le",
    sampleRate: "16000",
    channels: "1",
    silenceMs: "300",
    maxSegmentMs: "5000",
    chineseScript: "simplified",
  });

  const ws = new WebSocket(`ws://127.0.0.1:8765/api/live/asr-ws?${params}`);
  ws.binaryType = "arraybuffer";

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "segment") {
      for (const segment of message.segments || []) {
        const text = segment.text || "";
        if (text) {
          console.log(`[${segment.start}-${segment.end}] ${text}`);
        }
      }
    }
    if (message.type === "error") {
      console.error(message.message);
    }
  };

  return ws;
}
```

## 同步音频翻译接口

适合短音频，不适合实时流。

```http
POST /api/audio/translate
Content-Type: multipart/form-data
```

表单字段：

```text
file                音频文件
source_path         本机已有音频路径；file 和 source_path 二选一
source_language     auto 或语言代码；默认 auto
target_language     默认 Chinese
asr_model           ASR 模型 key
translation_model   翻译模型 key
audio_source        可选，仅用于日志
device              默认 auto
compute_type        默认 auto
n_ctx               默认 4096
n_gpu_layers        默认 0
chinese_script      中文输出书写格式，默认 simplified；可选 simplified/traditional/original
```

返回重点字段：

```json
{
  "sourceLanguage": "ja",
  "targetLanguage": "Chinese",
  "chineseScript": "simplified",
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

## 异步任务接口

创建转写任务：

```http
POST /api/jobs/transcribe
Content-Type: multipart/form-data
```

可传 `chinese_script=simplified` 控制中文输出为简体。

创建转写 + 翻译任务：

```http
POST /api/jobs/translate-test
Content-Type: multipart/form-data
```

可传 `chinese_script=simplified` 控制中文输出为简体。

查询任务：

```http
GET /api/tasks/{taskId}
```

任务完成后，`result.outputs` 里会包含可下载结果地址，例如：

```json
{
  "outputs": {
    "json": "/api/outputs/xxx.json",
    "sourceSrt": "/api/outputs/xxx.source.srt",
    "translatedSrt": "/api/outputs/xxx.translated.srt",
    "bilingualSrt": "/api/outputs/xxx.bilingual.srt"
  }
}
```

下载输出文件：

```http
GET /api/outputs/{filename}
```

## 自定义模型接口

获取自定义 ASR 模型：

```http
GET /api/models/asr/custom
```

添加自定义 ASR 模型：

```http
POST /api/models/asr/custom
Content-Type: application/json

{
  "key": "my-large-v2",
  "label": "My large-v2",
  "path": "D:\\models\\asr\\large-v2",
  "description": ""
}
```

后端会把 key 存为：

```text
custom:my-large-v2
```

获取自定义翻译模型：

```http
GET /api/models/translate/custom
```

添加自定义翻译模型：

```http
POST /api/models/translate/custom
Content-Type: application/json

{
  "key": "my-qwen",
  "label": "My Qwen GGUF",
  "path": "D:\\models\\translate\\qwen.gguf",
  "description": ""
}
```

后端会把 key 存为：

```text
custom:my-qwen
```

校验 ASR 模型路径：

```http
POST /api/models/asr/validate
Content-Type: application/json

{
  "path": "D:\\models\\asr\\large-v2"
}
```

校验翻译模型路径：

```http
POST /api/models/translate/validate
Content-Type: application/json

{
  "path": "D:\\models\\translate\\qwen.gguf"
}
```

## 旧直播片段上传接口

这个接口只是上传并保存片段，不会自动 ASR/翻译。实时字幕请优先使用 `/api/live/ws`。

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

上传片段：

```http
POST /api/live/sessions/{sessionId}/chunks
Content-Type: multipart/form-data

chunk=<audio bytes>
sequence=1
start_ms=0
duration_ms=1000
```

## 常见错误排查

### 获取有效模型失败

推荐做法：

```text
GET /api/models
```

也可以分别获取：

```text
GET /api/models/asr
GET /api/models/translate
```

然后筛选 `ready === true`，或直接使用 `/api/models` 返回的：

```text
ASR:        readyAsrModels
翻译模型:   readyTranslationModels
```

### WebSocket 一连接就收到 error 并关闭

检查：

```text
codec 是否为 pcm_s16le
sampleRate 是否大于 0
channels 是否为 1 或 2
silenceMs 是否 >= 200
targetLanguage 是否非空
asrModel 是否 ready
translationModel 是否 ready
```

### 有人声但没有字幕

检查：

```text
发送的是不是 PCM s16le，而不是 Float32Array 原始内存或 WebM/Opus。
音频采样率是否和 sampleRate 参数一致。
音量是否太小。
silenceMs 是否过大导致迟迟不断句。
前端是否发送了 flush 控制消息结束最后一句。
```

### 字幕延迟高

可以尝试：

```text
使用更小的 ASR 模型，例如 large-v3-turbo 或 small。
使用更小的 GGUF 翻译模型。
把 silenceMs 调到 300-400。
新闻频道可以把 maxSegmentMs 调到 4000-6000，避免连续播报拖到十几秒才出字幕。
有 partial 后可以适当调大 maxSegmentMs，让最终字幕更完整；但 maxSegmentMs 数字越大，单次最终 ASR 音频越长、后端压力越高，仍建议保留兜底切段。
确保前端每 20-100ms 发送一次音频块。
```
