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
  undoConfirmationArmed: false,
  undoConfirmationTimer: 0,
};

document.addEventListener("DOMContentLoaded", () => {
  for (const id of [
    "appWindow", "titlebar", "minimizeWindow", "maximizeWindow", "closeWindow",
    "version", "rootInput", "rootBrowse", "operationSelect", "operationMenu", "operationFields",
    "previewButton", "executeButton", "executeLabel", "undoButton", "undoLabel", "statusLine",
    "statusText", "progressTrack", "progressFill", "tableScroll", "resultTable", "resultBody",
    "resultsToolbar", "resultSearch", "statusFilter", "filterCount",
    "emptyState", "filterEmptyState", "previewStaleNotice",
    "dropOverlay", "footerState",
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
    renderOperationMenu(initial.operations);
    renderOperationFields();
    updateDirectory(initial.root);
    setWorkflowState("setup");
    setStatus("请选择目录和操作，然后生成预览。", "amber", "等待预览");
    applyBusyState();
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
  elements.rootBrowse.addEventListener("keydown", event => {
    if (["Enter", " "].includes(event.key) && !state.busy) {
      event.preventDefault();
      chooseRoot();
    }
  });
  elements.operationSelect.addEventListener("change", () => {
    renderOperationFields();
    invalidatePreview();
  });
  elements.previewButton.addEventListener("click", preview);
  elements.executeButton.addEventListener("click", executePrepared);
  elements.undoButton.addEventListener("click", undoLast);
  elements.resultSearch.addEventListener("input", scheduleFilteredRender);
  elements.statusFilter.addEventListener("change", () => renderFilteredRows(true));
  elements.tableScroll.addEventListener("scroll", scheduleVirtualRender);
  window.addEventListener("resize", scheduleVirtualRender);
  setupDragAndDrop();
}

function setWorkflowState(value) {
  elements.appWindow.dataset.workflow = value;
}

function renderOperationMenu(operations) {
  const fragment = document.createDocumentFragment();
  for (const operation of operations) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "operation-button";
    button.dataset.operation = operation.value;
    button.append(operationIcon(operation.value));

    const label = document.createElement("span");
    label.textContent = operation.label;
    button.append(label);

    const arrow = document.createElement("span");
    arrow.className = "operation-arrow";
    arrow.textContent = "›";
    button.append(arrow);

    button.addEventListener("click", () => {
      if (state.busy || elements.operationSelect.value === operation.value) return;
      elements.operationSelect.value = operation.value;
      elements.operationSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
    fragment.append(button);
  }
  elements.operationMenu.replaceChildren(fragment);
  updateOperationMenuSelection();
}

function operationIcon(value) {
  const wrapper = document.createElement("span");
  wrapper.className = "operation-icon";
  const paths = {
    prefix: '<path d="M7 7h10M7 12h7M7 17h10"/><path d="M4 7h.01M4 12h.01M4 17h.01"/>',
    suffix: '<path d="M6 7h10M9 12h7M6 17h10"/><path d="M19 7h.01M19 12h.01M19 17h.01"/>',
    remove: '<path d="M5 7h14M9 7V5h6v2m-8 0 1 13h8l1-13M10 11v5m4-5v5"/>',
    replace: '<path d="M4 7h11m0 0-3-3m3 3-3 3M20 17H9m0 0 3-3m-3 3 3 3"/>',
    mapping: '<path d="M4 5h6v6H4zM14 13h6v6h-6zM10 8h3a4 4 0 0 1 4 4v1M14 16h-3a4 4 0 0 1-4-4v-1"/>',
    pdf: '<path d="M7 3h7l4 4v14H7zM14 3v5h5"/><path d="M9.5 16v-4h1.4a1.2 1.2 0 0 1 0 2.4H9.5m4-2.4v4h1a2 2 0 0 0 0-4h-1Zm5 4v-4h2.5"/>',
  };
  wrapper.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[value] || '<path d="M5 5h14v14H5z"/>'}</svg>`;
  return wrapper;
}

function updateOperationMenuSelection() {
  if (!elements.operationMenu) return;
  for (const button of elements.operationMenu.querySelectorAll(".operation-button")) {
    const active = button.dataset.operation === elements.operationSelect.value;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "true" : "false");
  }
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
  updateOperationMenuSelection();
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
    elements.operationFields.append(fieldRow("输出说明", hint));
  }
  applyBusyState();
}

function renderMappingFields() {
  const input = document.createElement("input");
  input.id = "mappingInput";
  input.className = "mono";
  input.type = "text";
  input.readOnly = true;
  input.placeholder = "请选择 Excel 或 CSV 文件";
  input.value = state.mappingFile;
  const button = document.createElement("button");
  button.id = "mappingBrowse";
  button.type = "button";
  button.className = "inside-button";
  button.textContent = "选择";
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
  if (state.busy) return;
  resetUndoConfirmation();
  try {
    const result = await window.pywebview.api.choose_root(elements.rootInput.value);
    if (!result.cancelled) {
      elements.rootInput.value = result.path;
      updateDirectory(result.path);
      invalidatePreview();
      await refreshCurrentFiles(result.path);
    }
  } catch (error) { showError(error); }
}

async function refreshCurrentFiles(path) {
  state.prepared = false;
  state.trackingExecution = false;
  setProgress(0, false);
  setBusy(true);
  setWorkflowState("setup");
  setStatus("正在读取当前目录…", "navy", "加载文件");
  try {
    const result = await window.pywebview.api.list_files(path);
    renderRows(result.rows);
    elements.fileCount.textContent = `${result.fileCount} 个文件`;
    elements.directoryName.textContent = `目录：${result.directory || "—"}`;
    setStatus(
      result.fileCount ? `已显示当前目录中的 ${result.fileCount} 个文件。` : "当前目录中没有可显示的文件。",
      result.fileCount ? "green" : "amber",
      "目录已加载",
    );
  } finally {
    setBusy(false);
  }
}

async function chooseMapping() {
  if (state.busy) return;
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
  if (state.busy) return;
  resetUndoConfirmation();
  state.prepared = false;
  state.trackingExecution = false;
  setProgress(0, false);
  setBusy(true);
  setWorkflowState("setup");
  setStatus("正在扫描目录并生成预览…", "navy", "生成预览");
  try {
    const result = await window.pywebview.api.preview(previewArgs());
    state.prepared = true;
    renderRows(result.rows);
    elements.fileCount.textContent = `${result.total} 个文件`;
    elements.directoryName.textContent = `目录：${result.directory || "—"}`;
    setWorkflowState("preview");
    setStatus(
      `共 ${result.total} 个文件，${result.readyCount} 个待处理，${result.blockedCount} 个已阻止。`,
      result.readyCount ? "green" : "amber",
      "预览就绪",
    );
    setBusy(false);
    elements.executeButton.disabled = result.readyCount === 0;
    elements.executeLabel.textContent = result.readyCount ? `执行处理 (${result.readyCount})` : "执行处理";
  } catch (error) {
    setBusy(false);
    showError(error);
  }
}

async function executePrepared() {
  if (state.busy || !state.prepared) return;
  resetUndoConfirmation();
  state.trackingExecution = true;
  setProgress(0, true);
  setBusy(true);
  setWorkflowState("running");
  setStatus("正在处理文件，请不要关闭窗口。", "navy", "正在执行");
  try {
    const result = await window.pywebview.api.execute();
    if (result.started) {
      state.prepared = false;
    } else {
      state.trackingExecution = false;
      setProgress(0, false);
      setBusy(false);
      setWorkflowState("preview");
      setStatus(result.message || "未执行任何操作。", "amber", "预览就绪");
    }
  } catch (error) {
    state.trackingExecution = false;
    setProgress(0, false);
    setBusy(false);
    showError(error);
  }
}

async function undoLast() {
  if (state.busy || !state.canUndo) return;
  if (!state.undoConfirmationArmed) {
    state.undoConfirmationArmed = true;
    elements.undoButton.classList.add("confirm-undo");
    elements.undoButton.setAttribute("aria-pressed", "true");
    elements.undoLabel.textContent = "确认撤销？";
    setStatus("请再次点击红色按钮确认撤销。", "red", "等待确认");
    state.undoConfirmationTimer = window.setTimeout(resetUndoConfirmation, 5000);
    return;
  }
  resetUndoConfirmation();
  state.trackingExecution = false;
  setProgress(0, true);
  setBusy(true);
  setStatus("正在恢复上次操作前的文件状态…", "navy", "正在撤销");
  try {
    const result = await window.pywebview.api.undo(true);
    if (result.root) {
      elements.rootInput.value = result.root;
      updateDirectory(result.root);
    }
    setWorkflowState("running");
    setStatus("正在恢复上次操作前的文件状态…", "navy", "正在撤销");
  } catch (error) {
    setProgress(0, false);
    setBusy(false);
    showError(error);
  }
}

function resetUndoConfirmation() {
  window.clearTimeout(state.undoConfirmationTimer);
  state.undoConfirmationTimer = 0;
  state.undoConfirmationArmed = false;
  elements.undoButton.classList.remove("confirm-undo");
  elements.undoButton.setAttribute("aria-pressed", "false");
  elements.undoLabel.textContent = "撤销";
}

window.pathcraftHostEvent = function ({ event, payload = {} } = {}) {
  if (typeof event !== "string" || !payload || typeof payload !== "object") return;
  if (event === "window-state") {
    const maximized = Boolean(payload.maximized);
    elements.appWindow.classList.toggle("maximized", maximized);
    elements.maximizeWindow.setAttribute("aria-label", maximized ? "还原" : "最大化");
    return;
  }
  if (event === "directory-dropped") {
    if (typeof payload.path !== "string" || !payload.path) return;
    state.dragDepth = 0;
    elements.dropOverlay.hidden = true;
    elements.rootInput.value = payload.path;
    updateDirectory(payload.path);
    invalidatePreview();
    refreshCurrentFiles(payload.path).catch(showError);
    return;
  }
  if (event === "drop-error") {
    state.dragDepth = 0;
    elements.dropOverlay.hidden = true;
    setStatus(String(payload.message || "无法处理拖入的项目。"), "red", "拖入失败");
    return;
  }
  if (event === "progress") {
    const index = Number(payload.index);
    const total = Number(payload.total);
    if (!Number.isFinite(index) || !Number.isFinite(total) || index < 0 || total <= 0) return;
    if (state.trackingExecution) markProcessedThrough(index);
    const percent = Math.min(100, Math.max(0, (index / total) * 100));
    setProgress(percent, true);
    setStatus(`处理中 ${index}/${total}：${String(payload.detail || "")}`, "navy", "正在执行");
    return;
  }
  if (event === "error") {
    state.trackingExecution = false;
    setProgress(0, false);
    setBusy(false);
    showError(payload.message || "处理过程中发生未知错误。");
    return;
  }
  if (event === "completed") {
    if (!Array.isArray(payload.rows) || typeof payload.root !== "string") {
      state.trackingExecution = false;
      setProgress(0, false);
      setBusy(false);
      showError("后端返回的完成信息不完整。");
      return;
    }
    state.trackingExecution = false;
    setProgress(100, true);
    state.prepared = false;
    state.canUndo = payload.canUndo;
    elements.rootInput.value = payload.root;
    renderRows(payload.rows);
    elements.fileCount.textContent = `${payload.fileCount} 个文件`;
    elements.directoryName.textContent = `目录：${payload.directory || "—"}`;
    setWorkflowState("complete");
    const details = payload.detailsCount ? `；详细信息 ${payload.detailsCount} 条已显示` : "";
    setStatus(
      `成功 ${payload.succeeded}，跳过 ${payload.skipped}，失败 ${payload.failed}；当前目录共 ${payload.fileCount} 个文件${details}。`,
      payload.failed ? "red" : "green",
      payload.action,
    );
    setBusy(false);
    window.setTimeout(() => {
      if (!state.busy && elements.progressTrack.getAttribute("aria-valuenow") === "100") {
        setProgress(0, false);
      }
    }, 550);
  }
};

function invalidatePreview() {
  const hadPreparedPreview = state.prepared;
  state.prepared = false;
  setWorkflowState("setup");
  elements.executeLabel.textContent = "执行处理";
  elements.executeButton.disabled = true;
  elements.previewStaleNotice.hidden = !hadPreparedPreview || state.rows.length === 0;
  setStatus("输入已更改，请重新生成预览。", "amber", "等待预览");
}

function setBusy(busy) {
  state.busy = busy;
  applyBusyState();
}

function applyBusyState() {
  elements.rootBrowse.setAttribute("aria-disabled", String(state.busy));
  elements.rootBrowse.classList.toggle("disabled", state.busy);
  elements.operationSelect.disabled = state.busy;
  for (const button of elements.operationMenu.querySelectorAll(".operation-button")) {
    button.disabled = state.busy;
  }
  elements.previewButton.disabled = state.busy;
  for (const control of elements.operationFields.querySelectorAll("input, select, button")) {
    control.disabled = state.busy;
  }
  elements.executeButton.disabled = state.busy || !state.prepared;
  elements.undoButton.disabled = state.busy || !state.canUndo;
  elements.resultSearch.disabled = state.busy;
  elements.statusFilter.disabled = state.busy;
}

function renderRows(rows) {
  elements.previewStaleNotice.hidden = true;
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
  const viewportHeight = Math.max(VIRTUAL_ROW_HEIGHT, elements.tableScroll.clientHeight - headerHeight);
  const bodyScrollTop = Math.max(0, elements.tableScroll.scrollTop - headerHeight);
  const firstVisible = Math.floor(bodyScrollTop / VIRTUAL_ROW_HEIGHT);
  const start = Math.max(0, firstVisible - VIRTUAL_OVERSCAN);
  const visibleCount = Math.ceil(viewportHeight / VIRTUAL_ROW_HEIGHT);
  const end = Math.min(state.visibleRows.length, firstVisible + visibleCount + VIRTUAL_OVERSCAN);
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
  while (prefixLength < source.length && prefixLength < destination.length && source[prefixLength] === destination[prefixLength]) prefixLength += 1;
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
    console.warn("PathCraft progress index does not match a ready preview row", { index, readyCount: state.readyCount });
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

function setStatus(message, tone, title = null) {
  elements.statusText.textContent = message;
  elements.statusLine.dataset.tone = tone;
  if (title !== null) elements.footerState.textContent = title;
}

function showError(error) {
  setWorkflowState("setup");
  setStatus(errorMessage(error), "red", "发生错误");
}

function errorMessage(error) {
  if (typeof error === "string") return error;
  return error?.message || String(error);
}

function updateDirectory(path) {
  const parts = String(path || "").replace(/[\\/]+$/, "").split(/[\\/]/);
  elements.directoryName.textContent = `目录：${parts.at(-1) || "—"}`;
  elements.directoryName.title = path || "";
}
