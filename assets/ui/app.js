"use strict";

const elements = {};
const state = {
  busy: false,
  prepared: false,
  canUndo: false,
  mappingFile: "",
  mappingColumns: [],
  readyCount: 0,
  rows: [],
  visibleRows: [],
  processedThrough: 0,
  virtualStart: -1,
  virtualEnd: -1,
  virtualFrame: 0,
  trackingExecution: false,
  dragDepth: 0,
  filterTimer: 0,
};

document.addEventListener("DOMContentLoaded", () => {
  for (const id of [
    "appWindow", "titlebar", "minimizeWindow", "maximizeWindow", "closeWindow",
    "version", "rootInput", "rootBrowse", "operationSelect", "operationFields",
    "previewButton", "executeButton", "executeLabel", "undoButton", "statusLine",
    "statusText", "progressTrack", "progressFill", "tableScroll", "resultTable", "resultBody",
    "resultsToolbar", "resultSearch", "statusFilter", "filterCount",
    "emptyState", "emptyPreviewButton", "filterEmptyState", "dropOverlay", "footerState",
    "fileCount", "directoryName",
  ]) elements[id] = document.getElementById(id);
});

window.addEventListener("pywebviewready", async () => {
  bindEvents();
  try {
    const initial = await window.pywebview.api.initialize();
    elements.version.textContent = `v${initial.version}`;
    elements.rootInput.value = initial.root;
    elements.operationSelect.replaceChildren(...initial.operations.map(operationOption));
    renderOperationFields();
    updateDirectory(initial.root);
    setStatus("请选择目录和操作，然后生成预览。", "amber");
  } catch (error) {
    showError(error);
  }
});

function bindEvents() {
  elements.minimizeWindow.addEventListener("click", () => window.pywebview.api.minimize_window());
  elements.maximizeWindow.addEventListener("click", () => window.pywebview.api.toggle_maximize_window());
  elements.closeWindow.addEventListener("click", () => window.pywebview.api.close_window());
  elements.titlebar.addEventListener("dblclick", event => {
    if (!event.target.closest(".titlebar-controls")) window.pywebview.api.toggle_maximize_window();
  });
  elements.rootBrowse.addEventListener("click", chooseRoot);
  elements.operationSelect.addEventListener("change", () => {
    renderOperationFields();
    invalidatePreview();
  });
  elements.previewButton.addEventListener("click", preview);
  elements.emptyPreviewButton.addEventListener("click", preview);
  elements.executeButton.addEventListener("click", executePrepared);
  elements.undoButton.addEventListener("click", undoLast);
  elements.resultSearch.addEventListener("input", scheduleFilteredRender);
  elements.statusFilter.addEventListener("change", () => renderFilteredRows(true));
  elements.tableScroll.addEventListener("scroll", scheduleVirtualRender);
  window.addEventListener("resize", scheduleVirtualRender);
  setupDragAndDrop();
}

function operationOption(operation) {
  const option = document.createElement("option");
  option.value = operation.value;
  option.textContent = operation.label;
  return option;
}

function fieldRow(labelText, controls, extraClass = "") {
  const items = Array.isArray(controls) ? controls : [controls];
  const row = document.createElement("div");
  row.className = "field-row";
  const label = document.createElement("label");
  label.textContent = labelText;
  const labelledControl = items.find(control => control.id);
  if (labelledControl) label.htmlFor = labelledControl.id;
  const wrapper = document.createElement("div");
  wrapper.className = `field-control ${extraClass}`.trim();
  wrapper.append(...items);
  row.append(label, wrapper);
  return row;
}

function textInput(id, placeholder = "") {
  const input = document.createElement("input");
  input.id = id;
  input.type = "text";
  input.placeholder = placeholder;
  input.addEventListener("input", () => {
    updateHint();
    invalidatePreview();
  });
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !state.busy) {
      event.preventDefault();
      preview();
    }
  });
  return input;
}

function setupDragAndDrop() {
  for (const eventName of ["dragenter", "dragover", "dragleave", "drop"]) {
    document.addEventListener(eventName, event => {
      event.preventDefault();
      event.stopPropagation();
    });
  }
  document.addEventListener("dragenter", () => {
    if (state.busy) return;
    state.dragDepth += 1;
    elements.dropOverlay.hidden = false;
  });
  document.addEventListener("dragover", event => {
    if (!state.busy) event.dataTransfer.dropEffect = "copy";
  });
  document.addEventListener("dragleave", () => {
    state.dragDepth = Math.max(0, state.dragDepth - 1);
    if (!state.dragDepth) elements.dropOverlay.hidden = true;
  });
  document.addEventListener("drop", () => {
    state.dragDepth = 0;
    elements.dropOverlay.hidden = true;
  });
}

function renderOperationFields() {
  const operation = elements.operationSelect.value || "prefix";
  elements.operationFields.replaceChildren();
  if (["prefix", "suffix", "remove", "replace"].includes(operation)) {
    const labels = { prefix: "前缀", suffix: "后缀", remove: "删除内容", replace: "查找内容" };
    const primary = textInput("primaryInput", operation === "prefix" ? "例如：final_" : "");
    const hint = document.createElement("div");
    hint.id = "exampleHint";
    hint.className = "hint";
    elements.operationFields.append(fieldRow(labels[operation], [primary, hint]));
    if (operation === "replace") {
      elements.operationFields.append(fieldRow("替换为", textInput("secondaryInput")));
    }
    updateHint();
  } else if (operation === "mapping") {
    renderMappingFields();
  } else {
    const hint = document.createElement("div");
    hint.className = "hint";
    hint.textContent = "识别电子发票购买方，并在原目录生成 PNG";
    elements.operationFields.append(fieldRow("", hint));
  }
  applyBusyState();
}

function renderMappingFields() {
  const input = document.createElement("input");
  input.id = "mappingInput";
  input.className = "mono";
  input.type = "text";
  input.readOnly = true;
  input.value = state.mappingFile;
  const button = document.createElement("button");
  button.id = "mappingBrowse";
  button.type = "button";
  button.className = "inside-button";
  button.textContent = "选择…";
  button.addEventListener("click", chooseMapping);
  elements.operationFields.append(fieldRow("映射文件", [input, button], "with-action"));
  if (state.mappingColumns.length) {
    elements.operationFields.append(
      fieldRow("原名称列", columnSelect("sourceColumn", state.mappingColumns[0])),
      fieldRow("新名称列", columnSelect("destinationColumn", state.mappingColumns[1] || state.mappingColumns[0])),
    );
  }
}

function columnSelect(id, selected) {
  const select = document.createElement("select");
  select.id = id;
  for (const column of state.mappingColumns) {
    const option = document.createElement("option");
    option.value = column;
    option.textContent = column;
    option.selected = column === selected;
    select.append(option);
  }
  select.addEventListener("change", invalidatePreview);
  return select;
}

function updateHint() {
  const hint = document.getElementById("exampleHint");
  if (!hint) return;
  const operation = elements.operationSelect.value;
  const primary = document.getElementById("primaryInput")?.value || "";
  const secondary = document.getElementById("secondaryInput")?.value || "";
  const examples = {
    prefix: `report.docx  ⟶  ${primary || "final_"}report.docx`,
    suffix: `report.docx  ⟶  report${primary || "_后缀"}.docx`,
    remove: `report${primary || "_副本"}.docx  ⟶  report.docx`,
    replace: `report_${primary || "old"}.docx  ⟶  report_${secondary || "new"}.docx`,
  };
  hint.textContent = examples[operation] || "";
}

async function chooseRoot() {
  try {
    const result = await window.pywebview.api.choose_root(elements.rootInput.value);
    if (!result.cancelled) {
      elements.rootInput.value = result.path;
      updateDirectory(result.path);
      invalidatePreview();
    }
  } catch (error) { showError(error); }
}

async function chooseMapping() {
  try {
    const result = await window.pywebview.api.choose_mapping(elements.rootInput.value);
    if (!result.cancelled) {
      state.mappingFile = result.path;
      state.mappingColumns = result.columns;
      renderOperationFields();
      invalidatePreview();
    }
  } catch (error) { showError(error); }
}

function previewArgs() {
  return {
    root: elements.rootInput.value,
    operation: elements.operationSelect.value,
    primary: document.getElementById("primaryInput")?.value || "",
    secondary: document.getElementById("secondaryInput")?.value || "",
    mappingFile: state.mappingFile,
    sourceColumn: document.getElementById("sourceColumn")?.value || "",
    destinationColumn: document.getElementById("destinationColumn")?.value || "",
  };
}

async function preview() {
  state.prepared = false;
  state.trackingExecution = false;
  setProgress(0, false);
  setBusy(true);
  setStatus("正在生成预览…", "navy");
  elements.footerState.textContent = "处理中";
  try {
    const result = await window.pywebview.api.preview(previewArgs());
    state.prepared = true;
    renderRows(result.rows);
    elements.fileCount.textContent = `${result.total} 个文件`;
    elements.directoryName.textContent = `目录：${result.directory || "—"}`;
    elements.footerState.textContent = "预览就绪";
    setStatus(
      `预览已生成，共 ${result.total} 个文件，${result.readyCount} 个待处理，${result.blockedCount} 个已阻止。`,
      result.readyCount ? "green" : "amber",
    );
    setBusy(false);
    elements.executeButton.disabled = result.readyCount === 0;
    elements.executeLabel.textContent = result.readyCount ? `执行 (${result.readyCount})` : "执行";
  } catch (error) {
    setBusy(false);
    showError(error);
  }
}

async function executePrepared() {
  state.trackingExecution = true;
  setProgress(0, true);
  setBusy(true);
  setStatus("正在执行…", "navy");
  elements.footerState.textContent = "处理中";
  try {
    const result = await window.pywebview.api.execute();
    if (result.started) state.prepared = false;
    else {
      state.trackingExecution = false;
      setProgress(0, false);
      setBusy(false);
    }
  } catch (error) {
    state.trackingExecution = false;
    setProgress(0, false);
    setBusy(false);
    showError(error);
  }
}

async function undoLast() {
  state.trackingExecution = false;
  setProgress(0, true);
  setBusy(true);
  setStatus("等待撤销确认…", "amber");
  try {
    const result = await window.pywebview.api.undo();
    if (result.cancelled) {
      setProgress(0, false);
      setBusy(false);
      setStatus("已取消撤销，上次操作仍可撤销。", "amber");
      return;
    }
    if (result.root) {
      elements.rootInput.value = result.root;
      updateDirectory(result.root);
    }
    setStatus("正在撤销上次操作…", "navy");
    elements.footerState.textContent = "处理中";
  } catch (error) {
    setProgress(0, false);
    setBusy(false);
    showError(error);
  }
}

window.pathcraftHostEvent = function ({ event, payload }) {
  if (event === "window-state") {
    elements.appWindow.classList.toggle("maximized", payload.maximized);
    elements.maximizeWindow.setAttribute("aria-label", payload.maximized ? "还原" : "最大化");
    return;
  }
  if (event === "directory-dropped") {
    state.dragDepth = 0;
    elements.dropOverlay.hidden = true;
    elements.rootInput.value = payload.path;
    updateDirectory(payload.path);
    invalidatePreview();
    setStatus(payload.fromFile ? "已选择拖入文件所在的目录，请生成预览。" : "已选择拖入的目录，请生成预览。", "green");
    return;
  }
  if (event === "drop-error") {
    state.dragDepth = 0;
    elements.dropOverlay.hidden = true;
    setStatus(payload.message, "red");
    return;
  }
  if (event === "progress") {
    if (state.trackingExecution) markProcessedThrough(payload.index);
    const percent = payload.total ? (payload.index / payload.total) * 100 : 0;
    setProgress(percent, true);
    setStatus(`处理中 ${payload.index}/${payload.total}：${payload.detail}`, "navy");
    return;
  }
  if (event === "error") {
    state.trackingExecution = false;
    setProgress(0, false);
    setBusy(false);
    showError(payload.message);
    return;
  }
  if (event === "completed") {
    state.trackingExecution = false;
    setProgress(100, true);
    state.prepared = false;
    state.canUndo = payload.canUndo;
    elements.rootInput.value = payload.root;
    renderRows(payload.rows);
    elements.fileCount.textContent = `${payload.fileCount} 个文件`;
    elements.directoryName.textContent = `目录：${payload.directory || "—"}`;
    elements.footerState.textContent = payload.action;
    const details = payload.detailsCount ? `；详细信息 ${payload.detailsCount} 条已显示` : "";
    setStatus(
      `${payload.action}：成功 ${payload.succeeded}，跳过 ${payload.skipped}，失败 ${payload.failed}；当前目录共 ${payload.fileCount} 个文件${details}。`,
      payload.failed ? "red" : "green",
    );
    setBusy(false);
    window.setTimeout(() => {
      if (!state.busy && elements.progressTrack.getAttribute("aria-valuenow") === "100") {
        setProgress(0, false);
      }
    }, 450);
  }
};

function invalidatePreview() {
  state.prepared = false;
  elements.executeLabel.textContent = "执行";
  elements.executeButton.disabled = true;
  elements.footerState.textContent = "等待预览";
  setStatus("输入已更改，请重新生成预览。", "amber");
}

function setBusy(busy) {
  state.busy = busy;
  applyBusyState();
}

function applyBusyState() {
  elements.rootBrowse.disabled = state.busy;
  elements.operationSelect.disabled = state.busy;
  elements.previewButton.disabled = state.busy;
  for (const control of elements.operationFields.querySelectorAll("input, select, button")) {
    control.disabled = state.busy;
  }
  elements.executeButton.disabled = state.busy || !state.prepared;
  elements.undoButton.disabled = state.busy || !state.canUndo;
  elements.emptyPreviewButton.disabled = state.busy;
  elements.resultSearch.disabled = state.busy;
  elements.statusFilter.disabled = state.busy;
}

function renderRows(rows) {
  let readyIndex = 0;
  state.rows = rows.map(row => ({
    ...row,
    progressIndex: row.status === "ready" ? ++readyIndex : null,
  }));
  state.readyCount = readyIndex;
  state.processedThrough = 0;
  elements.resultSearch.value = "";
  elements.statusFilter.value = "all";
  renderFilteredRows(true);
}

function scheduleFilteredRender() {
  window.clearTimeout(state.filterTimer);
  state.filterTimer = window.setTimeout(() => renderFilteredRows(true), 120);
}

function displayStatus(row) {
  return row.progressIndex !== null && row.progressIndex <= state.processedThrough
    ? "done"
    : row.status;
}

function filteredRows() {
  const query = elements.resultSearch.value.trim().toLocaleLowerCase();
  const status = elements.statusFilter.value;
  return state.rows.filter(row => {
    if (status !== "all" && displayStatus(row) !== status) return false;
    if (!query) return true;
    return [row.source, row.destination, row.detail]
      .some(value => String(value || "").toLocaleLowerCase().includes(query));
  });
}

function renderFilteredRows(resetScroll = false) {
  const rows = filteredRows();
  state.visibleRows = rows;
  state.virtualStart = -1;
  state.virtualEnd = -1;
  elements.resultBody.replaceChildren();
  elements.resultsToolbar.hidden = state.rows.length === 0;
  elements.filterCount.textContent = rows.length === state.rows.length
    ? `${rows.length} 项`
    : `${rows.length} / ${state.rows.length} 项`;
  if (!state.rows.length) {
    elements.resultTable.hidden = true;
    elements.emptyState.hidden = false;
    elements.filterEmptyState.hidden = true;
    elements.resultTable.removeAttribute("aria-rowcount");
    return;
  }
  elements.emptyState.hidden = true;
  elements.resultTable.hidden = rows.length === 0;
  elements.filterEmptyState.hidden = rows.length !== 0;
  if (!rows.length) {
    elements.resultTable.removeAttribute("aria-rowcount");
    return;
  }
  elements.resultTable.setAttribute("aria-rowcount", String(rows.length + 1));
  if (resetScroll) elements.tableScroll.scrollTop = 0;
  renderVirtualRows(true);
}

const VIRTUAL_ROW_HEIGHT = 37;
const VIRTUAL_OVERSCAN = 8;

function scheduleVirtualRender() {
  if (state.virtualFrame) return;
  state.virtualFrame = window.requestAnimationFrame(() => {
    state.virtualFrame = 0;
    renderVirtualRows();
  });
}

function renderVirtualRows(force = false) {
  if (!state.visibleRows.length || elements.resultTable.hidden) return;
  const headerHeight = elements.resultTable.tHead?.offsetHeight || VIRTUAL_ROW_HEIGHT;
  const viewportHeight = Math.max(
    VIRTUAL_ROW_HEIGHT,
    elements.tableScroll.clientHeight - headerHeight,
  );
  const bodyScrollTop = Math.max(0, elements.tableScroll.scrollTop - headerHeight);
  const firstVisible = Math.floor(bodyScrollTop / VIRTUAL_ROW_HEIGHT);
  const start = Math.max(0, firstVisible - VIRTUAL_OVERSCAN);
  const visibleCount = Math.ceil(viewportHeight / VIRTUAL_ROW_HEIGHT);
  const end = Math.min(
    state.visibleRows.length,
    firstVisible + visibleCount + VIRTUAL_OVERSCAN,
  );
  if (!force && start === state.virtualStart && end === state.virtualEnd) return;
  state.virtualStart = start;
  state.virtualEnd = end;
  const fragment = document.createDocumentFragment();
  if (start) fragment.append(spacerRow(start * VIRTUAL_ROW_HEIGHT));
  for (let index = start; index < end; index += 1) {
    fragment.append(tableRow(state.visibleRows[index], index));
  }
  const remaining = state.visibleRows.length - end;
  if (remaining) fragment.append(spacerRow(remaining * VIRTUAL_ROW_HEIGHT));
  elements.resultBody.replaceChildren(fragment);
}

function spacerRow(height) {
  const row = document.createElement("tr");
  row.className = "virtual-spacer";
  row.setAttribute("aria-hidden", "true");
  const cell = document.createElement("td");
  cell.colSpan = 4;
  cell.style.height = `${height}px`;
  row.append(cell);
  return row;
}

function tableRow(row, visibleIndex) {
  const tr = document.createElement("tr");
  tr.setAttribute("aria-rowindex", String(visibleIndex + 2));
  if (row.progressIndex !== null) tr.dataset.progressIndex = String(row.progressIndex);
  const source = document.createElement("td");
  source.className = "path-cell";
  source.textContent = row.source;
  source.title = row.source;
  const destination = document.createElement("td");
  destination.className = "path-cell";
  destination.title = row.destination;
  appendDestinationDiff(destination, row.source, row.destination);
  const status = document.createElement("td");
  const badge = document.createElement("span");
  const statusName = displayStatus(row);
  badge.className = `badge ${statusName}`;
  const labels = { ready: "✓ 待处理", done: "✓ 已处理", blocked: "✕ 已阻止", issue: "⚠ 处理详情", current: "● 当前文件" };
  badge.textContent = labels[statusName] || statusName;
  status.append(badge);
  const detail = document.createElement("td");
  detail.className = "detail-cell";
  detail.textContent = row.detail;
  detail.title = row.detail;
  tr.append(source, destination, status, detail);
  return tr;
}

function appendDestinationDiff(cell, sourcePath, destination) {
  if (!destination || destination.includes("，")) {
    cell.textContent = destination;
    return;
  }
  const source = sourcePath.split(/[\\/]/).at(-1) || "";
  let prefixLength = 0;
  while (
    prefixLength < source.length
    && prefixLength < destination.length
    && source[prefixLength] === destination[prefixLength]
  ) prefixLength += 1;
  let suffixLength = 0;
  while (
    suffixLength < source.length - prefixLength
    && suffixLength < destination.length - prefixLength
    && source[source.length - 1 - suffixLength] === destination[destination.length - 1 - suffixLength]
  ) suffixLength += 1;
  const changedEnd = destination.length - suffixLength;
  if (prefixLength === changedEnd) {
    cell.textContent = destination;
    return;
  }
  cell.append(document.createTextNode(destination.slice(0, prefixLength)));
  const changed = document.createElement("span");
  changed.className = "text-diff-add";
  changed.textContent = destination.slice(prefixLength, changedEnd);
  cell.append(changed, document.createTextNode(destination.slice(changedEnd)));
}

function markProcessedThrough(index) {
  if (!Number.isInteger(index) || index < 1 || index > state.readyCount) {
    console.warn("PathCraft progress index does not match a ready preview row", {
      index,
      readyCount: state.readyCount,
    });
    return;
  }
  state.processedThrough = Math.max(state.processedThrough, index);
  if (["ready", "done"].includes(elements.statusFilter.value)) {
    renderFilteredRows(false);
    return;
  }
  for (const row of elements.resultBody.querySelectorAll("tr[data-progress-index]")) {
    if (Number(row.dataset.progressIndex) > index) continue;
    const badge = row.querySelector(".badge");
    badge.className = "badge done";
    badge.textContent = "✓ 已处理";
  }
}

function setProgress(percent, visible) {
  const normalized = Math.max(0, Math.min(100, Number(percent) || 0));
  elements.progressTrack.hidden = !visible;
  elements.progressTrack.setAttribute("aria-valuenow", String(Math.round(normalized)));
  elements.progressFill.style.width = `${normalized}%`;
}

function setStatus(message, tone) {
  elements.statusText.textContent = message;
  elements.statusLine.dataset.tone = tone;
}

function showError(error) {
  elements.footerState.textContent = "错误";
  setStatus(errorMessage(error), "red");
}

function errorMessage(error) {
  if (typeof error === "string") return error;
  return error?.message || String(error);
}

function updateDirectory(path) {
  const parts = path.replace(/[\\/]+$/, "").split(/[\\/]/);
  elements.directoryName.textContent = `目录：${parts.at(-1) || "—"}`;
}
