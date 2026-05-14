const transcriptionChecklist = document.querySelector("#transcriptionChecklist");
const transcriptionReadyBadge = document.querySelector("#transcriptionReadyBadge");
const translationChecklist = document.querySelector("#translationChecklist");
const translationReadyBadge = document.querySelector("#translationReadyBadge");
const cudaRecommendation = document.querySelector("#cudaRecommendation");
const modelList = document.querySelector("#modelList");
const translationModelList = document.querySelector("#translationModelList");
const taskList = document.querySelector("#taskList");
const translationTaskList = document.querySelector("#translationTaskList");
const logList = document.querySelector("#logList");
const logLevelFilter = document.querySelector("#logLevelFilter");
const logTypeFilter = document.querySelector("#logTypeFilter");
const logFromFilter = document.querySelector("#logFromFilter");
const logToFilter = document.querySelector("#logToFilter");
const logIpFilter = document.querySelector("#logIpFilter");
const autoRefreshToggle = document.querySelector("#autoRefreshToggle");
const logPrevPageBtn = document.querySelector("#logPrevPageBtn");
const logNextPageBtn = document.querySelector("#logNextPageBtn");
const logPageInfo = document.querySelector("#logPageInfo");
const refreshBtn = document.querySelector("#refreshBtn");
const jobForm = document.querySelector("#jobForm");
const customModelForm = document.querySelector("#customModelForm");
const customModelResult = document.querySelector("#customModelResult");
const validateModelBtn = document.querySelector("#validateModelBtn");
const customTranslationModelForm = document.querySelector("#customTranslationModelForm");
const customTranslationModelResult = document.querySelector("#customTranslationModelResult");
const validateTranslationModelBtn = document.querySelector("#validateTranslationModelBtn");
const translationTestForm = document.querySelector("#translationTestForm");
const translationGpuHint = document.querySelector("#translationGpuHint");
const liveDefaultsForm = document.querySelector("#liveDefaultsForm");
const liveDefaultsResult = document.querySelector("#liveDefaultsResult");
const liveTranslationGpuHint = document.querySelector("#liveTranslationGpuHint");
const liveConnectionList = document.querySelector("#liveConnectionList");
const refreshConnectionsBtn = document.querySelector("#refreshConnectionsBtn");
const versionRuntimeBadge = document.querySelector("#versionRuntimeBadge");
const appVersionValue = document.querySelector("#appVersionValue");
const appRuntimeValue = document.querySelector("#appRuntimeValue");
const appBuildTimeValue = document.querySelector("#appBuildTimeValue");
const appExecutableValue = document.querySelector("#appExecutableValue");
const restartBackendBtn = document.querySelector("#restartBackendBtn");
const restartBackendResult = document.querySelector("#restartBackendResult");
let autoSelectedModel = false;
let autoSelectedTranslationModel = false;
let liveDefaultsLoaded = false;
let latestLogs = [];
let latestLiveConnections = [];
let refreshTimer = null;
let taskRefreshInFlight = false;
let liveConnectionEvents = null;
let logEvents = null;
let logPage = 1;
const LOG_PAGE_SIZE = 25;
const highlightedLogKeys = new Set();
const disconnectingLiveConnections = new Set();

const fmtBytes = (bytes) => {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
};

const statusLabels = {
  queued: "排队中",
  running: "处理中",
  succeeded: "已完成",
  failed: "失败",
};

const kindLabels = {
  transcribe: "转写",
  "translate-test": "翻译测试",
};

const messageLabels = {
  Started: "已开始",
  Finished: "已完成",
  Failed: "失败",
  "Loading ASR model": "正在加载转写模型",
  "Transcribing media": "正在转写媒体",
  "Translating subtitles": "正在翻译字幕",
};

const outputLabels = {
  json: "完整结果",
  sourceSrt: "原文字幕",
  translatedSrt: "翻译字幕",
  bilingualSrt: "双语字幕",
};

const logLevelLabels = {
  info: "info",
  warning: "warning",
  error: "error",
};

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const translateMessage = (message) => {
  if (!message) return "";
  if (message.startsWith("Loading translation model:")) {
    return `正在加载翻译模型：${message.replace("Loading translation model:", "").trim()}`;
  }
  return messageLabels[message] || message;
};

const taskStatus = (task) => {
  const progress = task.progress == null ? "" : ` · ${Math.round(task.progress * 100)}%`;
  return `${statusLabels[task.status] || task.status}${progress}`;
};

const fmtDuration = (seconds) => {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) return `${hours}小时${minutes}分${secs}秒`;
  if (minutes) return `${minutes}分${secs}秒`;
  return `${secs}秒`;
};

const fmtTime = (timestamp) => (timestamp ? new Date(timestamp * 1000).toLocaleString() : "-");
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const fmtIsoTime = (timestamp) => {
  if (!timestamp) return "-";
  const date = new Date(timestamp);
  return Number.isFinite(date.getTime()) ? date.toLocaleString() : "-";
};

const fmtAge = (timestamp) => {
  if (!timestamp) return "";
  const seconds = Math.max(0, Date.now() / 1000 - Number(timestamp));
  return fmtDuration(seconds);
};

async function refreshStatus() {
  const form = new FormData(jobForm);
  const asrModel = form.get("asr_model") || "large-v2";
  const response = await fetch(`/api/status?asr_model=${encodeURIComponent(asrModel)}`);
  const data = await response.json();

  renderReadyBadge(
    transcriptionReadyBadge,
    data.transcriptionReady ?? data.ready,
    "√ 转写可用",
    "转写未就绪",
  );
  renderReadyBadge(
    translationReadyBadge,
    data.translationReady,
    "√ 翻译模型可用",
    "未发现翻译模型",
  );
  renderChecks(transcriptionChecklist, data.transcriptionChecks || data.checks || []);
  renderChecks(translationChecklist, data.translationChecks || []);
  renderCudaRecommendation(data.cuda);
  renderTranslationGpuHint(data.translationRuntime);

  modelList.innerHTML = "";
  syncAsrModelOptions([...data.asrModels, ...(data.customAsrModels || [])]);
  for (const model of [...data.asrModels, ...(data.customAsrModels || [])]) {
    const validation = model.validation;
    const issues = validation
      ? [...(validation.errors || []), ...(validation.warnings || [])]
          .map((item) => `<div class="meta ${validation.errors?.length ? "bad" : ""}">${item}</div>`)
          .join("")
      : "";
    modelList.insertAdjacentHTML(
      "beforeend",
      `<div class="model">
        <div class="model-main">
          <strong>${model.nameCn || model.label} <span class="${model.ready ? "ok" : "bad"}">${model.ready ? "可用" : "不可用"}</span></strong>
          <details>
            <summary>查看详情</summary>
            <div class="meta">${model.description}</div>
            <div class="meta">模型仓库：${model.repoId}</div>
            <div class="meta">推荐本地目录：${escapeHtml(model.path)}</div>
            <div class="meta">当前大小：${fmtBytes(model.sizeBytes)}</div>
            ${issues}
          </details>
        </div>
        <div class="model-actions">
          ${model.url ? `<a class="action-link" href="${model.url}" target="_blank" rel="noreferrer">打开模型页</a>` : ""}
          ${deleteCustomModelButton(model, "asr")}
        </div>
      </div>`,
    );
  }

  const translationModels = [...(data.translationModels || []), ...(data.customTranslationModels || [])];
  syncTranslationModelOptions(translationModels);
  translationModelList.innerHTML = "";
  for (const model of translationModels) {
    const validation = model.validation;
    const files = (validation?.files || model.files || []).length
      ? (validation?.files || model.files).join(", ")
      : "未发现 .gguf 文件";
    const issues = validation
      ? [...(validation.errors || []), ...(validation.warnings || [])]
          .map((item) => `<div class="meta ${validation.errors?.length ? "bad" : ""}">${item}</div>`)
          .join("")
      : "";
    translationModelList.insertAdjacentHTML(
      "beforeend",
      `<div class="model">
        <div class="model-main">
          <strong>${model.nameCn || model.label} <span class="${model.ready ? "ok" : "bad"}">${model.ready ? "可用" : "未放置模型"}</span></strong>
          <details>
            <summary>查看详情</summary>
            <div class="meta">${model.description}</div>
            <div class="meta">模型仓库：${model.repoId}</div>
            <div class="meta">推荐本地目录：${escapeHtml(model.path)}</div>
            <div class="meta">模型文件：${files}</div>
            <div class="meta">当前大小：${fmtBytes(model.sizeBytes)}</div>
            ${issues}
          </details>
        </div>
        <div class="model-actions">
          ${model.url ? `<a class="action-link" href="${model.url}" target="_blank" rel="noreferrer">打开模型页</a>` : ""}
          ${deleteCustomModelButton(model, "translate")}
        </div>
      </div>`,
    );
  }
}

function deleteCustomModelButton(model, type) {
  if (!model.custom || model.ready) return "";
  return `<button class="danger-button" type="button" data-delete-custom-model="${escapeHtml(model.key)}" data-model-type="${type}">删除记录</button>`;
}

function renderTranslationGpuHint(runtime) {
  const supportsGpu = Boolean(runtime?.supportsGpuOffload);
  const runtimeVersion = runtime?.version ? ` ${runtime.version}` : "";
  const layers = Number(runtime?.nGpuLayers || 0);
  const gpuIndex = Number(runtime?.translationGpuIndex || 0);
  const usingGpu = runtime?.mode === "gpu";
  const text = usingGpu
    ? `当前 GGUF 运行库 llama-cpp-python${runtimeVersion} 会按直播默认设置尝试使用 GPU ${gpuIndex}，offload ${layers} 层；加载失败会退回 CPU。`
    : supportsGpu
      ? `当前 GGUF 运行库 llama-cpp-python${runtimeVersion} 是 CUDA 版，但直播默认 GPU 层数为 0，所以现在按 CPU 跑；要启用 GPU，请到直播高级参数设置 10-20 层试起。`
      : `当前 GGUF 运行库${runtime?.available ? ` llama-cpp-python${runtimeVersion}` : ""}是 CPU 版或不可用；GGUF 翻译 GPU 层数请保持 0。`;
  if (translationGpuHint) translationGpuHint.textContent = text;
  if (liveTranslationGpuHint) {
    liveTranslationGpuHint.textContent = usingGpu
      ? `直播默认翻译会尝试使用 GGUF GPU offload：GPU ${gpuIndex}，${layers} 层；如果显存不够会退回 CPU，卡顿时先降层数。`
      : supportsGpu
        ? `直播默认翻译当前按 CPU 跑；GGUF 运行库是 CUDA 版，可在高级设备参数里把 GPU 层数设为 10-20 试起。`
        : `直播默认翻译当前按 CPU 跑；GGUF 运行库是 CPU 版或不可用，GPU 层数请保持 0。`;
  }
}

async function refreshLiveDefaults(force = false) {
  if (liveDefaultsLoaded && !force) return;
  const response = await fetch("/api/live/defaults");
  const defaults = await response.json();
  liveDefaultsForm.elements.device.value = defaults.device || "auto";
  liveDefaultsForm.elements.deviceIndex.value = defaults.deviceIndex ?? 0;
  liveDefaultsForm.elements.computeType.value = defaults.computeType || "auto";
  liveDefaultsForm.elements.nGpuLayers.value = defaults.nGpuLayers ?? 0;
  liveDefaultsForm.elements.translationGpuIndex.value = defaults.translationGpuIndex ?? 0;
  liveDefaultsLoaded = true;
  liveDefaultsResult.textContent = "已加载";
  liveDefaultsResult.className = "ready-badge ready";
}

async function saveLiveDefaults(event) {
  event.preventDefault();
  const data = new FormData(liveDefaultsForm);
  const payload = {
    device: data.get("device") || "auto",
    deviceIndex: Number(data.get("deviceIndex") || 0),
    computeType: data.get("computeType") || "auto",
    nGpuLayers: Number(data.get("nGpuLayers") || 0),
    translationGpuIndex: Number(data.get("translationGpuIndex") || 0),
  };
  liveDefaultsResult.textContent = "保存中";
  liveDefaultsResult.className = "ready-badge pending";
  const response = await fetch("/api/live/defaults", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    liveDefaultsResult.textContent = result.detail || "保存失败";
    liveDefaultsResult.className = "ready-badge blocked";
    return;
  }
  liveDefaultsLoaded = false;
  await refreshLiveDefaults(true);
  liveDefaultsResult.textContent = "已保存";
}

async function refreshLiveConnections() {
  const response = await fetch("/api/live/connections");
  const connections = await response.json();
  renderLiveConnections(connections);
}

function renderLiveConnections(connections) {
  latestLiveConnections = Array.isArray(connections) ? connections : [];
  const openDetails = new Set(
    [...liveConnectionList.querySelectorAll(".connection details[open]")]
      .map((details) => details.closest(".connection")?.dataset.connectionId)
      .filter(Boolean),
  );
  liveConnectionList.innerHTML = "";
  if (!latestLiveConnections.length) {
    liveConnectionList.innerHTML = `<div class="tile"><strong>暂无直播连接</strong><div class="meta">WebSocket 连接建立后会出现在这里。</div></div>`;
    return;
  }
  for (const connection of latestLiveConnections) {
    const mode = connection.translationEnabled ? "双语字幕" : "只转写";
    const title = `${mode} · ${String(connection.id || "").slice(0, 8)}`;
    const device = `${connection.device || "auto"}:${connection.deviceIndex ?? 0} · ${connection.computeType || "auto"}`;
    const translationGpu = connection.translationEnabled
      ? ` · 翻译 GPU ${connection.translationGpuIndex ?? 0} · GPU 层 ${connection.nGpuLayers ?? 0}`
      : "";
    const runtimeLine = renderConnectionRuntime(connection);
    const recentTexts = renderRecentConnectionTexts(connection.recentTexts || []);
    const processingLogs = renderLiveProcessingLogs(connection.processingLogs || []);
    const isOpen = openDetails.has(connection.id) ? " open" : "";
    const isDisconnecting =
      disconnectingLiveConnections.has(connection.id) || connection.lastEvent === "disconnect_requested";
    const disconnectLabel = isDisconnecting ? "断开中" : "断开连接";
    const disconnectButton = connection.id
      ? `<button class="danger-button" type="button" data-disconnect-live="${escapeHtml(connection.id)}"${isDisconnecting ? " disabled" : ""}>${disconnectLabel}</button>`
      : "";
    const processing = renderLiveProcessing(connection);
    liveConnectionList.insertAdjacentHTML(
      "beforeend",
      `<article class="connection" data-connection-id="${escapeHtml(connection.id || "")}">
        <div class="connection-head">
          <div>
            <strong>${escapeHtml(title)}</strong>
            <div class="meta">IP ${escapeHtml(connection.clientIp || "-")} · 已连接 ${escapeHtml(fmtDuration(connection.connectedSeconds))} · 空闲 ${escapeHtml(fmtDuration(connection.idleSeconds))}</div>
            <div class="meta">ASR ${escapeHtml(connection.asrModel || "-")} · ${escapeHtml(device)}${escapeHtml(translationGpu)}</div>
            <div class="meta">${runtimeLine}</div>
            ${connection.disconnectReason ? `<div class="meta bad">断开原因：${escapeHtml(connection.disconnectReason)}</div>` : ""}
          </div>
          <div class="connection-actions">${disconnectButton}</div>
        </div>
        ${processing}
        ${processingLogs}
        ${recentTexts}
        <details${isOpen}>
          <summary>查看详情</summary>
          <div class="meta">连接 ID：${escapeHtml(connection.id || "-")}</div>
          <div class="meta">地址：${escapeHtml(connection.url || "-")}</div>
          <div class="meta">建立时间：${escapeHtml(fmtTime(connection.connectedAt))}</div>
          <div class="meta">最近活动：${escapeHtml(connection.lastEvent || "-")} · ${escapeHtml(fmtTime(connection.updatedAt))}</div>
          <div class="meta">音频：${escapeHtml(fmtBytes(connection.receivedBytes))} · ${escapeHtml(connection.audioChunks || 0)} 块 · ${escapeHtml(fmtDuration(connection.streamSeconds))}</div>
          <div class="meta">字幕：临时 ${escapeHtml(connection.partialCount || 0)} · 最终 ${escapeHtml(connection.segmentCount || 0)} · 队列 ${escapeHtml(connection.queuedSegments || 0)} · 错误 ${escapeHtml(connection.errorCount || 0)}</div>
          <div class="meta">采样：${escapeHtml(connection.codec || "-")} · ${escapeHtml(connection.sampleRate || "-")} Hz · ${escapeHtml(connection.channels || "-")} 声道</div>
          <div class="meta">断句：silenceMs=${escapeHtml(connection.silenceMs)} · maxSegmentMs=${escapeHtml(connection.maxSegmentMs)} · partialBeamSize=${escapeHtml(connection.partialBeamSize)} · finalBeamSize=${escapeHtml(connection.finalBeamSize)}</div>
          <div class="meta">语言：${escapeHtml(connection.sourceLanguage || "auto")} → ${escapeHtml(connection.targetLanguage || "-")} · ${escapeHtml(connection.chineseScript || "simplified")}</div>
          <div class="meta">User-Agent：${escapeHtml(connection.userAgent || "-")}</div>
        </details>
      </article>`,
    );
  }
}

function runtimeModeLabel(runtime, kind) {
  if (!runtime) return `${kind} -`;
  if (runtime.mode === "gpu") {
    const gpuIndex = runtime.deviceIndex ?? runtime.translationGpuIndex ?? 0;
    const layers = runtime.nGpuLayers ? ` · ${runtime.nGpuLayers} 层` : "";
    return `${kind} GPU ${gpuIndex}${layers}`;
  }
  const fallback = runtime.fallback ? "（GPU 加载失败，已退回）" : "";
  return `${kind} CPU${fallback}`;
}

function renderConnectionRuntime(connection) {
  const asrRuntime = connection.asrRuntime || {
    mode: connection.device === "cuda" ? "gpu" : "cpu",
    deviceIndex: connection.deviceIndex ?? 0,
  };
  const translationRuntime = connection.translationEnabled
    ? connection.translationRuntime || {
        mode: (connection.nGpuLayers || 0) > 0 ? "gpu" : "cpu",
        translationGpuIndex: connection.translationGpuIndex ?? 0,
        nGpuLayers: connection.nGpuLayers ?? 0,
      }
    : null;
  const parts = [`运行：${runtimeModeLabel(asrRuntime, "转写")}`];
  if (connection.translationEnabled) {
    parts.push(runtimeModeLabel(translationRuntime, "翻译"));
  }
  return escapeHtml(parts.join(" · "));
}

function renderLiveProcessing(connection) {
  const current = connection.currentProcessing;
  const pending = connection.pendingUtterances || [];
  const last = connection.lastProcessed;
  const queueText = `${connection.queuedSegments || 0} 段待完成`;
  if (!current && !pending.length && !last) {
    return `<div class="processing-state idle"><strong>处理状态</strong><span>等待音频 · ${escapeHtml(queueText)}</span></div>`;
  }

  const currentBlock = current
    ? `<div class="processing-main">
        <strong>当前处理 #${escapeHtml(current.sequence || "-")} · ${escapeHtml(current.message || "正在处理")}</strong>
        <span>${escapeHtml(fmtDuration(current.duration || 0))} 音频${current.startedAt ? ` · 已处理 ${escapeHtml(fmtAge(current.startedAt))}` : ""}${current.progress != null ? ` · ${escapeHtml(Math.round(Number(current.progress) * 100))}%` : ""}</span>
      </div>`
    : `<div class="processing-main">
        <strong>当前处理 · 空闲</strong>
        <span>${escapeHtml(queueText)}</span>
      </div>`;
  const pendingItems = pending.slice(0, 4).map((item) => {
    const waited = item.queuedAt ? ` · 等待 ${escapeHtml(fmtAge(item.queuedAt))}` : "";
    return `<span>#${escapeHtml(item.sequence || "-")} ${escapeHtml(fmtDuration(item.duration || 0))}${waited}</span>`;
  }).join("");
  const pendingBlock = pending.length
    ? `<div class="processing-pending"><span>排队 ${escapeHtml(pending.length)} 段</span>${pendingItems}</div>`
    : "";
  const lastBlock = last && !current
    ? `<div class="processing-last">最近完成 #${escapeHtml(last.sequence || "-")} · ${escapeHtml(last.message || "-")}${last.finishedAt ? ` · ${escapeHtml(fmtTime(last.finishedAt))}` : ""}</div>`
    : "";
  return `<div class="processing-state">${currentBlock}${pendingBlock}${lastBlock}</div>`;
}

function renderLiveProcessingLogs(logs) {
  if (!logs.length) {
    return "";
  }
  const items = [...logs]
    .reverse()
    .slice(0, 6)
    .map((item) => {
      const sequence = item.sequence != null ? `#${escapeHtml(item.sequence)} · ` : "";
      const progress = item.progress != null ? ` · ${escapeHtml(Math.round(Number(item.progress) * 100))}%` : "";
      const duration = item.duration != null ? ` · ${escapeHtml(fmtDuration(item.duration))} 音频` : "";
      const sourceText = item.sourceText
        ? `<span class="processing-log-text">${escapeHtml(item.sourceText)}</span>`
        : "";
      const errorText = item.error
        ? `<span class="processing-log-text bad">${escapeHtml(item.error)}</span>`
        : "";
      return `<div class="processing-log ${escapeHtml(item.level || "info")}">
        <span>${sequence}${escapeHtml(item.message || "-")}${duration}${progress}</span>
        <time>${escapeHtml(fmtTime(item.at))}</time>
        ${sourceText || errorText}
      </div>`;
    })
    .join("");
  return `<div class="processing-logs">
    <strong>处理日志</strong>
    ${items}
  </div>`;
}

function renderRecentConnectionTexts(recentTexts) {
  if (!recentTexts.length) {
    return `<div class="recent-texts empty">还没有识别文本</div>`;
  }
  const items = [...recentTexts]
    .reverse()
    .map((item) => {
      const label = item.type === "partial" ? "临时" : "最终";
      const translated = item.translatedText
        ? `<div class="recent-translation">${escapeHtml(item.translatedText)}</div>`
        : "";
      const source = item.sourceText && item.sourceText !== item.translatedText
        ? `<div class="recent-source">${escapeHtml(item.sourceText)}</div>`
        : "";
      return `<div class="recent-text">
        <span>${escapeHtml(label)} · ${escapeHtml(fmtTime(item.at))}</span>
        <strong>${escapeHtml(item.displayText || item.translatedText || item.sourceText || "")}</strong>
        ${translated && source ? source : ""}
      </div>`;
    })
    .join("");
  return `<div class="recent-texts">${items}</div>`;
}

async function disconnectLiveConnection(sessionId) {
  if (!sessionId || disconnectingLiveConnections.has(sessionId)) return;
  if (!confirm(`断开直播连接 ${sessionId.slice(0, 8)}？`)) return;
  disconnectingLiveConnections.add(sessionId);
  renderLiveConnections(latestLiveConnections);
  try {
    const response = await fetch(`/api/live/connections/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.detail || "断开失败");
    }
    await refreshLiveConnections();
  } catch (error) {
    alert(error instanceof Error ? error.message : "断开失败");
  } finally {
    disconnectingLiveConnections.delete(sessionId);
    await refreshLiveConnections();
  }
}

function connectLiveConnectionEvents() {
  if (!window.EventSource || liveConnectionEvents) return;
  liveConnectionEvents = new EventSource("/api/live/connections/events");
  liveConnectionEvents.addEventListener("connections", (event) => {
    try {
      renderLiveConnections(JSON.parse(event.data));
    } catch {
      // Ignore one malformed event; the stream will send the next snapshot.
    }
  });
  liveConnectionEvents.onerror = () => {
    liveConnectionEvents.close();
    liveConnectionEvents = null;
    setTimeout(connectLiveConnectionEvents, 2500);
  };
}

function syncAsrModelOptions(models) {
  syncAsrModelSelect(jobForm.elements.asr_model, models, true);
  if (translationTestForm) {
    syncAsrModelSelect(translationTestForm.elements.asr_model, models, false);
  }
}

function syncAsrModelSelect(select, models, allowAutoSelect) {
  const readyModels = models.filter((model) => model.ready);
  const selected = select.value || "large-v2";
  setModelSelectOptions(select, readyModels, "暂无可用 ASR 模型");
  const hasSelected = readyModels.some((model) => model.key === selected);
  if (hasSelected) {
    select.value = selected;
  }

  const selectedModel = readyModels.find((model) => model.key === select.value);
  const readyCustomModel = readyModels.find((model) => model.custom);
  if (allowAutoSelect && !autoSelectedModel && readyCustomModel && (!selectedModel || !selectedModel.ready)) {
    autoSelectedModel = true;
    select.value = readyCustomModel.key;
    setTimeout(refreshStatus, 0);
  }
}

function setModelSelectOptions(select, models, emptyText) {
  const previous = select.value;
  select.innerHTML = "";
  if (!models.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = emptyText;
    option.disabled = true;
    select.appendChild(option);
    select.disabled = true;
    return;
  }

  select.disabled = false;
  for (const model of models) {
    const option = document.createElement("option");
    option.value = model.key;
    option.textContent = model.nameCn || model.label;
    select.appendChild(option);
  }
  if (models.some((model) => model.key === previous)) {
    select.value = previous;
  }
}

function syncTranslationModelOptions(models) {
  if (!translationTestForm) return;
  const select = translationTestForm.elements.translation_model;
  const readyModels = models.filter((model) => model.ready);
  const selected = select.value || "qwen2.5-1.5b-instruct-gguf";
  setModelSelectOptions(select, readyModels, "暂无可用翻译模型");
  const hasSelected = readyModels.some((model) => model.key === selected);
  if (hasSelected) {
    select.value = selected;
  }

  const selectedModel = readyModels.find((model) => model.key === select.value);
  const readyModel = readyModels[0];
  if (!autoSelectedTranslationModel && readyModel && (!selectedModel || !selectedModel.ready)) {
    autoSelectedTranslationModel = true;
    select.value = readyModel.key;
  }
}

function renderAction(action) {
  if (!action) return "";
  if (action.type === "link") {
    return `<a class="action-link" href="${action.url}" target="_blank" rel="noreferrer">${action.label}</a>`;
  }
  if (action.type === "api") {
    return `<button type="button" data-api-action="${action.endpoint}">${action.label}</button>`;
  }
  return "";
}

function renderReadyBadge(target, ready, readyText, blockedText) {
  target.className = `ready-badge ${ready ? "ready" : "blocked"}`;
  target.textContent = ready ? readyText : blockedText;
}

function renderChecks(target, checks) {
  target.innerHTML = "";
  for (const check of checks) {
    const action = renderAction(check.action);
    const isOptional = check.required === false;
    const markClass = check.ok ? "ok" : isOptional ? "optional" : "bad";
    const markText = check.ok ? "√" : isOptional ? "可选" : "!";
    target.insertAdjacentHTML(
      "beforeend",
      `<div class="check-item">
        <div class="mark ${markClass}">${markText}</div>
        <div>
          <strong>${check.label}</strong>
          <div class="meta">${check.detail || ""}</div>
        </div>
        <div>${action}</div>
      </div>`,
    );
  }
}

function renderCudaRecommendation(cuda) {
  if (!cudaRecommendation) return;
  const available = Boolean(cuda?.available);
  const statusText = available ? "CUDA 已可用" : "推荐启用 CUDA";
  const detail = cuda?.detail || "安装 NVIDIA CUDA 12 后，ASR 可使用 GPU 加速；未配置时会继续使用 CPU。";
  const restartHint = " 安装或更新 CUDA 后需要在设置里重启后端；直播标签内 ASR 设备请选择 auto 或 cuda。";
  const runtimeHint = available
    ? restartHint
    : ` 本程序当前需要 CUDA 12 运行库；CUDA 13 不能替代缺失的 cublas64_12.dll。${restartHint}`;
  const action = available
    ? ""
    : `<a class="action-link" href="${escapeHtml(cuda?.downloadUrl || "https://developer.nvidia.com/cuda-12-6-3-download-archive")}" target="_blank" rel="noreferrer">下载 CUDA 12</a>`;
  cudaRecommendation.innerHTML = `<div class="cuda-recommendation-main">
      <div>
        <strong>${escapeHtml(statusText)}</strong>
        <div class="meta">${escapeHtml(detail + runtimeHint)}</div>
      </div>
      ${action}
    </div>`;
  cudaRecommendation.className = `cuda-recommendation ${available ? "ready" : "pending"}`;
}

async function refreshVersion() {
  const response = await fetch("/api/version");
  const info = await response.json();
  renderVersion(info);
}

function renderVersion(info) {
  const packaged = Boolean(info?.packaged);
  if (versionRuntimeBadge) {
    versionRuntimeBadge.textContent = packaged ? "打包运行" : "源码运行";
    versionRuntimeBadge.className = `ready-badge ${packaged ? "ready" : "pending"}`;
  }
  if (appVersionValue) appVersionValue.textContent = info?.version || "-";
  if (appRuntimeValue) appRuntimeValue.textContent = packaged ? "便携版/安装包" : "源码目录";
  if (appBuildTimeValue) appBuildTimeValue.textContent = fmtIsoTime(info?.executableModifiedAt);
  if (appExecutableValue) appExecutableValue.textContent = `程序路径：${info?.executable || "-"}`;
}

async function waitForBackendReady() {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await wait(1000);
    try {
      const response = await fetch(`/api/version?restartCheck=${Date.now()}`, { cache: "no-store" });
      if (response.ok) {
        await refreshAll();
        return true;
      }
    } catch {
      // The server is expected to be unavailable for a moment while restarting.
    }
  }
  return false;
}

async function restartBackend() {
  if (!restartBackendBtn || !restartBackendResult) return;
  if (!confirm("重启后端会断开当前直播连接，确定现在重启？")) return;
  restartBackendBtn.disabled = true;
  restartBackendResult.textContent = "正在请求重启...";
  restartBackendResult.className = "form-result";
  try {
    const response = await fetch("/api/restart", { method: "POST" });
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.detail || "重启请求失败");
    }
    restartBackendResult.textContent = "后端正在重启，页面会自动刷新状态...";
    const ready = await waitForBackendReady();
    restartBackendResult.textContent = ready
      ? "后端已重启。请到直播标签确认 ASR 设备为 auto 或 cuda，并让电视端重新连接。"
      : "已发送重启请求，但暂时没有等到后端恢复；请稍后手动刷新页面。";
  } catch (error) {
    restartBackendResult.textContent = error instanceof Error ? error.message : "重启请求失败";
  } finally {
    restartBackendBtn.disabled = false;
  }
}

async function refreshTasks() {
  if (taskRefreshInFlight) return;
  taskRefreshInFlight = true;
  try {
    const response = await fetch("/api/tasks");
    const tasks = await response.json();
    renderTaskList(taskList, tasks.filter((task) => task.kind === "transcribe"), "开始转写后会显示在这里。");
    renderTaskList(
      translationTaskList,
      tasks.filter((task) => task.kind === "translate-test"),
      "开始翻译测试后会显示在这里。",
    );
  } finally {
    taskRefreshInFlight = false;
  }
}

async function refreshLogs() {
  if (!logList) return;
  const params = new URLSearchParams({ limit: "1000" });
  const response = await fetch(`/api/logs?${params}`);
  latestLogs = await response.json();
  logPage = 1;
  renderLogs(latestLogs);
}

function renderLogs(logs) {
  logList.innerHTML = "";
  if (!logs.length) {
    logList.innerHTML = `<div class="tile"><strong>暂无日志</strong><div class="meta">接口调用、音频接收、转写和翻译结果会显示在这里。</div></div>`;
    return;
  }

  const audioGroups = new Map();
  const otherLogs = [];
  for (const item of logs) {
    const requestId = item.details?.requestId;
    const utteranceId = item.details?.utteranceId;
    const groupId = requestId || utteranceId;
    const isAudioFlow =
      groupId &&
      (["audio", "asr", "translation"].includes(item.category) ||
        (item.category === "live" && utteranceId));
    if (!isAudioFlow) {
      otherLogs.push(item);
      continue;
    }
    if (!audioGroups.has(groupId)) {
      audioGroups.set(groupId, []);
    }
    audioGroups.get(groupId).push(item);
  }

  const filters = currentLogFilters();
  const groupedLogs = [...audioGroups.entries()]
    .map(([requestId, items]) => ({
      requestId,
      items: items.sort((a, b) => Date.parse(a.timestamp || 0) - Date.parse(b.timestamp || 0)),
      latestAt: Math.max(...items.map((item) => Date.parse(item.timestamp || 0) || 0)),
    }))
    .filter((group) => matchesAudioGroupFilters(group, filters))
    .sort((a, b) => b.latestAt - a.latestAt);
  const filteredOtherLogs = otherLogs.filter((item) => matchesFlatLogFilters(item, filters));

  const entries = [
    ...groupedLogs.map((group) => ({ type: "audio", latestAt: group.latestAt, payload: group })),
    ...filteredOtherLogs.map((item) => ({
      type: "flat",
      latestAt: Date.parse(item.timestamp || 0) || 0,
      payload: item,
    })),
  ].sort((a, b) => b.latestAt - a.latestAt);

  if (!entries.length) {
    logList.innerHTML = `<div class="tile"><span>没有符合条件的日志</span><div class="meta">可以放宽时间、IP 或类别条件。</div></div>`;
    updateLogPager(0);
    return;
  }

  const totalPages = Math.max(1, Math.ceil(entries.length / LOG_PAGE_SIZE));
  logPage = Math.min(Math.max(1, logPage), totalPages);
  const pageEntries = entries.slice((logPage - 1) * LOG_PAGE_SIZE, logPage * LOG_PAGE_SIZE);
  for (const entry of pageEntries) {
    if (entry.type === "audio") {
      renderAudioLogGroup(entry.payload);
    } else {
      renderFlatLog(entry.payload);
    }
  }
  updateLogPager(entries.length);
}

function renderAudioLogGroup(group) {
  const level = group.items.some((item) => normalizedLogLevel(item) === "error")
    ? "error"
    : group.items.some((item) => normalizedLogLevel(item) === "warning")
      ? "warning"
      : "info";
  const received = group.items.find((item) => item.category === "audio") || group.items[0];
  const time = formatLogTime(received.timestamp);
  const ip = received.details?.clientIp || "-";
  const steps = group.items.map(renderAudioStep).join("");
  const isNew = group.items.some((item) => highlightedLogKeys.has(logEventKey(item)));
  logList.insertAdjacentHTML(
    "beforeend",
    `<article class="log-row audio-block ${escapeHtml(level)} ${isNew ? "is-new" : ""}">
      <div class="log-head">
        <span class="log-level">${escapeHtml(logLevelLabels[level] || level)}</span>
        <span class="meta">${escapeHtml(time)} · IP ${escapeHtml(ip)}</span>
      </div>
      <div class="log-group-title">音频处理 ${escapeHtml(group.requestId.slice(0, 8))}</div>
      <div class="log-steps">${steps}</div>
    </article>`,
  );
}

function renderAudioStep(item) {
  const details = item.details || {};
  const time = formatLogTime(item.timestamp);
  if (item.level === "error") {
    return `<div class="log-step error"><span>${escapeHtml(time)}</span><span>处理失败：${escapeHtml(details.error || item.message || "未知错误")}</span></div>`;
  }
  if (item.category === "audio") {
    const stats = details.audioStats || {};
    const source = audioSourceLabel(details.audioSource);
    const metrics = stats.maxSample != null
      ? ` · 峰值 ${stats.maxSample}${stats.rmsDbFS != null ? ` · ${stats.rmsDbFS} dBFS` : ""}${stats.isSilent ? " · 静音" : ""}`
      : "";
    return `<div class="log-step ${stats.isSilent ? "warning" : ""}"><span>${escapeHtml(time)}</span><span>收到音频${escapeHtml(source ? `（${source}${metrics}）` : metrics)}</span></div>`;
  }
  if (item.category === "live" && item.message === "收到音频") {
    const seconds = details.duration != null ? ` · ${Number(details.duration).toFixed(2)}s` : "";
    const bytes = details.sizeBytes != null ? ` · ${fmtBytes(details.sizeBytes)}` : "";
    return `<div class="log-step"><span>${escapeHtml(time)}</span><span>收到音频${escapeHtml(seconds + bytes)}</span></div>`;
  }
  if (item.category === "asr") {
    const sourceText = details.sourceText || "未识别到文本";
    return `<div class="log-step"><span>${escapeHtml(time)}</span><span>音频转写为「${escapeHtml(sourceText)}」</span></div>`;
  }
  if ((item.category === "asr" || item.category === "live") && details.sourceText != null && details.translatedText == null) {
    const sourceText = details.sourceText || "未识别到文本";
    return `<div class="log-step"><span>${escapeHtml(time)}</span><span>音频转写为「${escapeHtml(sourceText)}」</span></div>`;
  }
  if ((item.category === "translation" || item.category === "live") && details.translatedText != null) {
    const translatedText = details.translatedText || "";
    return `<div class="log-step"><span>${escapeHtml(time)}</span><span>翻译为「${escapeHtml(translatedText)}」</span></div>`;
  }
  return `<div class="log-step"><span>${escapeHtml(time)}</span><span>${escapeHtml(item.message || "")}</span></div>`;
}

function audioSourceLabel(value) {
  if (value === "system") return "系统播放声音";
  if (value === "microphone") return "麦克风";
  return "";
}

function renderFlatLog(item) {
  const level = item.level || "info";
  const time = formatLogTime(item.timestamp);
  const isNew = highlightedLogKeys.has(logEventKey(item));
  const details = item.details && Object.keys(item.details).length
    ? `<pre>${escapeHtml(JSON.stringify(item.details, null, 2))}</pre>`
    : "";
  logList.insertAdjacentHTML(
    "beforeend",
    `<article class="log-row ${escapeHtml(level)} ${isNew ? "is-new" : ""}">
      <div class="log-head">
        <span class="log-level">${escapeHtml(logLevelLabels[level] || level)}</span>
        <span class="meta">${escapeHtml(time)} · ${escapeHtml(item.category || "system")}</span>
      </div>
      <div class="log-message">${escapeHtml(item.message || "")}</div>
      ${details}
    </article>`,
  );
}

function formatLogTime(timestamp) {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return "";
  const millis = String(date.getMilliseconds()).padStart(3, "0");
  return `${date.toLocaleString()}.${millis}`;
}

function currentLogFilters() {
  return {
    level: logLevelFilter.value,
    type: logTypeFilter.value,
    from: parseLocalDateTime(logFromFilter.value),
    to: parseLocalDateTime(logToFilter.value),
    ip: logIpFilter.value.trim(),
  };
}

function parseLocalDateTime(value) {
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : null;
}

function updateLogPager(totalItems) {
  const totalPages = Math.max(1, Math.ceil(totalItems / LOG_PAGE_SIZE));
  logPageInfo.textContent = `第 ${Math.min(logPage, totalPages)} / ${totalPages} 页 · ${totalItems} 条`;
  logPrevPageBtn.disabled = logPage <= 1;
  logNextPageBtn.disabled = logPage >= totalPages;
}

function logEventKey(item) {
  const details = item.details || {};
  return [
    item.timestamp || "",
    item.level || "",
    item.category || "",
    item.message || "",
    details.requestId || "",
    details.utteranceId || "",
    details.statusCode || "",
  ].join("|");
}

function addLogEvent(item) {
  const key = logEventKey(item);
  if (latestLogs.some((existing) => logEventKey(existing) === key)) return;
  latestLogs.unshift(item);
  latestLogs = latestLogs.slice(0, 1000);
  highlightedLogKeys.add(key);
  logPage = 1;
  renderLogs(latestLogs);
  setTimeout(() => {
    highlightedLogKeys.delete(key);
  }, 4500);
}

function connectLogEvents() {
  if (!window.EventSource || logEvents || !autoRefreshToggle.checked) return;
  logEvents = new EventSource("/api/logs/events");
  logEvents.addEventListener("log", (event) => {
    try {
      addLogEvent(JSON.parse(event.data));
    } catch {
      // Ignore one malformed event; the stream will continue.
    }
  });
  logEvents.onerror = () => {
    logEvents.close();
    logEvents = null;
    if (autoRefreshToggle.checked) {
      setTimeout(connectLogEvents, 2500);
    }
  };
}

function disconnectLogEvents() {
  if (!logEvents) return;
  logEvents.close();
  logEvents = null;
}

function normalizedLogLevel(item) {
  if (item.level === "warning" && isUnrecognizedEvent(item)) {
    return "info";
  }
  return item.level || "info";
}

function isUnrecognizedEvent(item) {
  const details = item.details || {};
  const message = item.message || "";
  return (
    message.includes("未识别") ||
    message.includes("had no text") ||
    (details.sourceText != null && !String(details.sourceText).trim() && details.translatedText == null) ||
    Number(details.segmentCount) === 0
  );
}

function audioGroupType(group) {
  const hasTranslation = group.items.some((item) => item.details?.translatedText != null);
  const hasUnrecognized = group.items.some(isUnrecognizedEvent);
  const hasTranscription = group.items.some(
    (item) => item.details?.sourceText != null && String(item.details.sourceText).trim(),
  );
  if (hasUnrecognized && !hasTranslation) return "unrecognized";
  if (hasTranslation) return "translated";
  if (hasTranscription) return "transcribed";
  return "unrecognized";
}

function matchesAudioGroupFilters(group, filters) {
  if (filters.level && !group.items.some((item) => normalizedLogLevel(item) === filters.level)) {
    return false;
  }
  if (filters.type && audioGroupType(group) !== filters.type) {
    return false;
  }
  if (filters.from != null && group.latestAt < filters.from) {
    return false;
  }
  if (filters.to != null && group.latestAt > filters.to) {
    return false;
  }
  if (filters.ip) {
    const hasIp = group.items.some((item) => String(item.details?.clientIp || "").includes(filters.ip));
    if (!hasIp) return false;
  }
  return true;
}

function matchesFlatLogFilters(item, filters) {
  if (filters.type) return false;
  if (filters.level && normalizedLogLevel(item) !== filters.level) return false;
  const timestamp = Date.parse(item.timestamp || 0) || 0;
  if (filters.from != null && timestamp < filters.from) return false;
  if (filters.to != null && timestamp > filters.to) return false;
  if (filters.ip && !String(item.details?.clientIp || "").includes(filters.ip)) return false;
  return true;
}

function renderTaskList(target, tasks, emptyText) {
  target.innerHTML = "";
  if (!tasks.length) {
    target.innerHTML = `<div class="tile"><strong>暂无任务</strong><div class="meta">${emptyText}</div></div>`;
    return;
  }
  for (const task of tasks) {
    const outputs = task.result?.outputs || {};
    const links = Object.entries(outputs)
      .map(([label, href]) => `<a href="${href}" target="_blank" rel="noreferrer">${outputLabels[label] || label}</a>`)
      .join("");
    target.insertAdjacentHTML(
      "beforeend",
      `<div class="task">
        <strong>${task.label}</strong>
        <div class="meta">${kindLabels[task.kind] || task.kind} · ${taskStatus(task)} · ${translateMessage(task.message)}</div>
        ${task.error ? `<div class="meta bad">${task.error}</div>` : ""}
        ${links ? `<div class="links">${links}</div>` : ""}
      </div>`,
    );
  }
}

async function refreshAll() {
  refreshBtn.disabled = true;
  try {
    await Promise.all([
      refreshStatus(),
      refreshTasks(),
      refreshLogs(),
      refreshLiveDefaults(),
      refreshLiveConnections(),
      refreshVersion(),
    ]);
  } finally {
    refreshBtn.disabled = false;
  }
}

function startTaskAutoRefresh() {
  if (refreshTimer) return;
  refreshTimer = setInterval(() => {
    if (document.hidden) return;
    refreshTasks();
  }, 1500);
}

function renderCachedLogs() {
  renderLogs(latestLogs);
}

function syncAutoRefresh() {
  if (autoRefreshToggle.checked) {
    connectLogEvents();
  } else {
    disconnectLogEvents();
  }
}

for (const checklist of [transcriptionChecklist, translationChecklist]) {
  checklist.addEventListener("click", async (event) => {
    const apiButton = event.target.closest("[data-api-action]");
    if (apiButton) {
      apiButton.disabled = true;
      await fetch(apiButton.dataset.apiAction, { method: "POST" });
      setTimeout(refreshAll, 1200);
    }
  });
}

async function validateCustomModelPath() {
  const payload = customModelPayload();
  const response = await fetch("/api/models/asr/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: payload.path }),
  });
  const result = await response.json();
  renderValidation(result, customModelResult);
  return result;
}

async function validateCustomTranslationModelPath() {
  const payload = customTranslationModelPayload();
  const response = await fetch("/api/models/translate/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: payload.path }),
  });
  const result = await response.json();
  renderValidation(result, customTranslationModelResult);
  return result;
}

async function deleteCustomModel(key, type) {
  const label = type === "translate" ? "自定义翻译模型" : "自定义 ASR 模型";
  if (!confirm(`删除这个${label}记录？`)) return;
  const base = type === "translate" ? "/api/models/translate/custom" : "/api/models/asr/custom";
  const response = await fetch(`${base}/${encodeURIComponent(key)}`, { method: "DELETE" });
  if (!response.ok) {
    const result = await response.json();
    alert(result.detail || "删除失败");
    return;
  }
  await refreshAll();
}

function customModelPayload() {
  return {
    key: customModelForm.elements.key.value.trim(),
    label: customModelForm.elements.label.value.trim(),
    path: customModelForm.elements.path.value.trim(),
    description: customModelForm.elements.description.value.trim(),
  };
}

function customTranslationModelPayload() {
  return {
    key: customTranslationModelForm.elements.key.value.trim(),
    label: customTranslationModelForm.elements.label.value.trim(),
    path: customTranslationModelForm.elements.path.value.trim(),
    description: customTranslationModelForm.elements.description.value.trim(),
  };
}

function renderValidation(result, target = customModelResult) {
  const lines = [];
  if (result.ok) lines.push(`<span class="ok">校验通过。</span>`);
  if (result.files?.length) lines.push(`<span>发现模型文件：${result.files.join(", ")}</span>`);
  for (const item of result.errors || []) lines.push(`<span class="bad">${item}</span>`);
  for (const item of result.warnings || []) lines.push(`<span>${item}</span>`);
  target.innerHTML = lines.join("<br>");
}

validateModelBtn.addEventListener("click", validateCustomModelPath);
validateTranslationModelBtn.addEventListener("click", validateCustomTranslationModelPath);
liveDefaultsForm.addEventListener("submit", saveLiveDefaults);
refreshConnectionsBtn.addEventListener("click", refreshLiveConnections);
restartBackendBtn?.addEventListener("click", restartBackend);
liveConnectionList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-disconnect-live]");
  if (!button) return;
  button.disabled = true;
  try {
    await disconnectLiveConnection(button.dataset.disconnectLive);
  } finally {
    button.disabled = false;
  }
});
for (const list of [modelList, translationModelList]) {
  list.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-custom-model]");
    if (!button) return;
    button.disabled = true;
    try {
      await deleteCustomModel(button.dataset.deleteCustomModel, button.dataset.modelType);
    } finally {
      button.disabled = false;
    }
  });
}
for (const filter of [logLevelFilter, logTypeFilter, logFromFilter, logToFilter, logIpFilter]) {
  filter.addEventListener("input", () => {
    logPage = 1;
    renderCachedLogs();
  });
  filter.addEventListener("change", () => {
    logPage = 1;
    renderCachedLogs();
  });
}
autoRefreshToggle.addEventListener("change", syncAutoRefresh);
logPrevPageBtn.addEventListener("click", () => {
  logPage = Math.max(1, logPage - 1);
  renderCachedLogs();
});
logNextPageBtn.addEventListener("click", () => {
  logPage += 1;
  renderCachedLogs();
});

customModelForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await fetch("/api/models/asr/custom", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(customModelPayload()),
  });
  const result = await response.json();
  if (!response.ok) {
    customModelResult.innerHTML = `<span class="bad">${result.detail || "添加失败"}</span>`;
    return;
  }
  renderValidation(result.validation, customModelResult);
  customModelForm.reset();
  await refreshAll();
});

customTranslationModelForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await fetch("/api/models/translate/custom", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(customTranslationModelPayload()),
  });
  const result = await response.json();
  if (!response.ok) {
    customTranslationModelResult.innerHTML = `<span class="bad">${result.detail || "添加失败"}</span>`;
    return;
  }
  renderValidation(result.validation, customTranslationModelResult);
  customTranslationModelForm.reset();
  await refreshAll();
});

jobForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const selectedModel = jobForm.elements.asr_model.value;
  const selectedDevice = jobForm.elements.device.value;
  const selectedDeviceIndex = jobForm.elements.device_index.value;
  const selectedComputeType = jobForm.elements.compute_type.value;
  const data = new FormData(jobForm);
  if (!data.get("file")?.name) {
    data.delete("file");
  }
  const response = await fetch("/api/jobs/transcribe", {
    method: "POST",
    body: data,
  });
  if (!response.ok) {
    const error = await response.json();
    alert(error.detail || "任务创建失败");
    return;
  }
  jobForm.reset();
  jobForm.elements.asr_model.value = selectedModel;
  jobForm.elements.device.value = selectedDevice;
  jobForm.elements.device_index.value = selectedDeviceIndex;
  jobForm.elements.compute_type.value = selectedComputeType;
  await refreshTasks();
  await refreshAll();
});

translationTestForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const selectedAsrModel = translationTestForm.elements.asr_model.value;
  const selectedTranslationModel = translationTestForm.elements.translation_model.value;
  const selectedDevice = translationTestForm.elements.device.value;
  const selectedDeviceIndex = translationTestForm.elements.device_index.value;
  const selectedComputeType = translationTestForm.elements.compute_type.value;
  const selectedGpuLayers = translationTestForm.elements.n_gpu_layers.value;
  const selectedTranslationGpuIndex = translationTestForm.elements.translation_gpu_index.value;
  const data = new FormData(translationTestForm);
  if (!data.get("file")?.name) {
    data.delete("file");
  }
  const response = await fetch("/api/jobs/translate-test", {
    method: "POST",
    body: data,
  });
  if (!response.ok) {
    const error = await response.json();
    alert(error.detail || "翻译测试创建失败");
    return;
  }
  translationTestForm.reset();
  translationTestForm.elements.asr_model.value = selectedAsrModel;
  translationTestForm.elements.translation_model.value = selectedTranslationModel;
  translationTestForm.elements.device.value = selectedDevice;
  translationTestForm.elements.device_index.value = selectedDeviceIndex;
  translationTestForm.elements.compute_type.value = selectedComputeType;
  translationTestForm.elements.n_gpu_layers.value = selectedGpuLayers;
  translationTestForm.elements.translation_gpu_index.value = selectedTranslationGpuIndex;
  await refreshTasks();
  await refreshAll();
});

refreshBtn.addEventListener("click", refreshAll);
connectLiveConnectionEvents();
syncAutoRefresh();
startTaskAutoRefresh();
document.querySelectorAll("[data-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-tab]").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#tab-${button.dataset.tab}`).classList.add("active");
  });
});
refreshAll();
