const transcriptionChecklist = document.querySelector("#transcriptionChecklist");
const transcriptionReadyBadge = document.querySelector("#transcriptionReadyBadge");
const translationChecklist = document.querySelector("#translationChecklist");
const translationReadyBadge = document.querySelector("#translationReadyBadge");
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
const refreshBtn = document.querySelector("#refreshBtn");
const jobForm = document.querySelector("#jobForm");
const customModelForm = document.querySelector("#customModelForm");
const customModelResult = document.querySelector("#customModelResult");
const validateModelBtn = document.querySelector("#validateModelBtn");
const customTranslationModelForm = document.querySelector("#customTranslationModelForm");
const customTranslationModelResult = document.querySelector("#customTranslationModelResult");
const validateTranslationModelBtn = document.querySelector("#validateTranslationModelBtn");
const translationTestForm = document.querySelector("#translationTestForm");
let autoSelectedModel = false;
let autoSelectedTranslationModel = false;
let latestLogs = [];
let refreshTimer = null;

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
            <div class="meta">本地目录：${model.path}</div>
            <div class="meta">当前大小：${fmtBytes(model.sizeBytes)}</div>
            ${issues}
          </details>
        </div>
        ${model.url ? `<a class="action-link" href="${model.url}" target="_blank" rel="noreferrer">打开模型页</a>` : ""}
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
            <div class="meta">本地目录：${model.path}</div>
            <div class="meta">模型文件：${files}</div>
            <div class="meta">当前大小：${fmtBytes(model.sizeBytes)}</div>
            ${issues}
          </details>
        </div>
        ${model.url ? `<a class="action-link" href="${model.url}" target="_blank" rel="noreferrer">打开模型页</a>` : ""}
      </div>`,
    );
  }
}

function syncAsrModelOptions(models) {
  syncAsrModelSelect(jobForm.elements.asr_model, models, true);
  if (translationTestForm) {
    syncAsrModelSelect(translationTestForm.elements.asr_model, models, false);
  }
}

function syncAsrModelSelect(select, models, allowAutoSelect) {
  const selected = select.value || "large-v2";
  const existing = new Set([...select.options].map((option) => option.value));
  for (const model of models) {
    if (existing.has(model.key)) continue;
    const option = document.createElement("option");
    option.value = model.key;
    option.textContent = model.nameCn || model.label;
    select.appendChild(option);
  }
  const hasSelected = [...select.options].some((option) => option.value === selected);
  if (hasSelected) {
    select.value = selected;
  }

  const selectedModel = models.find((model) => model.key === select.value);
  const readyCustomModel = models.find((model) => model.custom && model.ready);
  if (allowAutoSelect && !autoSelectedModel && readyCustomModel && (!selectedModel || !selectedModel.ready)) {
    autoSelectedModel = true;
    select.value = readyCustomModel.key;
    setTimeout(refreshStatus, 0);
  }
}

function syncTranslationModelOptions(models) {
  if (!translationTestForm) return;
  const select = translationTestForm.elements.translation_model;
  const selected = select.value || "qwen2.5-1.5b-instruct-gguf";
  const existing = new Set([...select.options].map((option) => option.value));
  for (const model of models) {
    if (existing.has(model.key)) continue;
    const option = document.createElement("option");
    option.value = model.key;
    option.textContent = model.nameCn || model.label;
    select.appendChild(option);
  }
  const hasSelected = [...select.options].some((option) => option.value === selected);
  if (hasSelected) {
    select.value = selected;
  }

  const selectedModel = models.find((model) => model.key === select.value);
  const readyModel = models.find((model) => model.ready);
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

async function refreshTasks() {
  const response = await fetch("/api/tasks");
  const tasks = await response.json();
  renderTaskList(taskList, tasks.filter((task) => task.kind === "transcribe"), "开始转写后会显示在这里。");
  renderTaskList(
    translationTaskList,
    tasks.filter((task) => task.kind === "translate-test"),
    "开始翻译测试后会显示在这里。",
  );
}

async function refreshLogs() {
  if (!logList) return;
  const params = new URLSearchParams({ limit: "1000" });
  const response = await fetch(`/api/logs?${params}`);
  latestLogs = await response.json();
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

  if (groupedLogs.length) {
    logList.insertAdjacentHTML("beforeend", `<div class="log-section-title">音频处理日志</div>`);
    for (const group of groupedLogs) {
      renderAudioLogGroup(group);
    }
  }

  if (filteredOtherLogs.length) {
    logList.insertAdjacentHTML("beforeend", `<div class="log-section-title">接口和系统日志</div>`);
    for (const item of filteredOtherLogs) {
      renderFlatLog(item);
    }
  }

  if (!groupedLogs.length && !filteredOtherLogs.length) {
    logList.innerHTML = `<div class="tile"><span>没有符合条件的日志</span><div class="meta">可以放宽时间、IP 或类别条件。</div></div>`;
  }
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
  logList.insertAdjacentHTML(
    "beforeend",
    `<article class="log-row audio-block ${escapeHtml(level)}">
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
  const details = item.details && Object.keys(item.details).length
    ? `<pre>${escapeHtml(JSON.stringify(item.details, null, 2))}</pre>`
    : "";
  logList.insertAdjacentHTML(
    "beforeend",
    `<article class="log-row ${escapeHtml(level)}">
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
  return timestamp ? new Date(timestamp).toLocaleString() : "";
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
    await Promise.all([refreshStatus(), refreshTasks(), refreshLogs()]);
  } finally {
    refreshBtn.disabled = false;
  }
}

function renderCachedLogs() {
  renderLogs(latestLogs);
}

function syncAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  if (autoRefreshToggle.checked) {
    refreshTimer = setInterval(refreshAll, 3500);
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
for (const filter of [logLevelFilter, logTypeFilter, logFromFilter, logToFilter, logIpFilter]) {
  filter.addEventListener("input", renderCachedLogs);
  filter.addEventListener("change", renderCachedLogs);
}
autoRefreshToggle.addEventListener("change", syncAutoRefresh);

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
  await refreshAll();
});

translationTestForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const selectedAsrModel = translationTestForm.elements.asr_model.value;
  const selectedTranslationModel = translationTestForm.elements.translation_model.value;
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
  await refreshAll();
});

refreshBtn.addEventListener("click", refreshAll);
document.querySelectorAll("[data-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-tab]").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#tab-${button.dataset.tab}`).classList.add("active");
  });
});
refreshAll();
