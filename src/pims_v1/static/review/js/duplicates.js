import { jsonFetch } from "./api.js";
import { el, fmt, setStatus, withButtonLoading } from "./dom.js";
import { state } from "./state.js";
import { loadProgress } from "./progress.js";
import { makePreview } from "./preview.js";

export const selectedBatch = () => state.batches.find((batch) => batch.id === state.batchId);

export const batchConfirmBlocker = (batch) => {
  if (!batch) return "请先选择一个包含操作的 planned 批次。";
  if (batch.status !== "planned") return `批次 #${batch.id} 当前状态是 ${batch.status}，不能确认。`;
  if ((batch.operation_count || 0) <= 0) return `批次 #${batch.id} 没有可确认操作。`;
  return "";
};

export const updateBatchActionState = () => {
  const batch = selectedBatch();
  const canConfirm = Boolean(batch && batch.status === "planned" && (batch.operation_count || 0) > 0);
  const button = el("confirm-batch");
  button.disabled = !canConfirm;
  button.title = batchConfirmBlocker(batch).replace(/。$/, "");
};

export const explainSelectedBatchConfirmState = () => {
  const reason = batchConfirmBlocker(selectedBatch());
  if (reason) setStatus(reason);
};

export const renderBatches = () => {
  el("batch-count").textContent = `${fmt(state.batches.length)} 个批次`;
  if (!state.batches.length) {
    el("batches").innerHTML = `<div class="empty">暂无批次。继续运行安全检测后会在这里出现审核项。</div>`;
    updateBatchActionState();
    return;
  }
  el("batches").replaceChildren(...state.batches.map((batch) => {
    const node = document.createElement("div");
    node.className = `batch ${batch.id === state.batchId ? "active" : ""}`;
    node.innerHTML = `
      <div><span class="pill">批次 #${batch.id}</span><span class="pill">${batch.status}</span><span class="pill">${fmt(batch.operation_count)} 项</span></div>
      <strong>${batch.batch_type === "duplicate_quarantine" ? "重复文件隔离计划" : batch.batch_type}</strong>
      <div class="meta"></div>
    `;
    node.querySelector(".meta").textContent = batch.description || "";
    node.addEventListener("click", () => selectBatch(batch.id));
    return node;
  }));
  updateBatchActionState();
};

export const copyCard = (copy) => {
  const node = document.createElement("div");
  node.className = `copy ${copy.role || ""}`;
  node.innerHTML = `
    <div class="copy-title">
      <span>${copy.role_label || "同内容副本"}</span>
      <span class="pill">${copy.library_kind || "unknown"}</span>
    </div>
    <div class="path"></div>
    <div class="meta">文件：${copy.file_name || "-"} · 大小：${fmt(copy.file_size)} · MD5：${copy.hash_md5 || "-"}</div>
  `;
  node.querySelector(".path").textContent = copy.current_path || "";
  return node;
};

export const renderOperations = (items) => {
  if (!items.length) {
    el("operations").innerHTML = `<div class="empty">当前筛选条件下没有操作。</div>`;
    return;
  }
  el("operations").replaceChildren(...items.map((operation) => {
    const asset = operation.asset || {};
    const node = document.createElement("article");
    node.className = "op";
    const top = document.createElement("div");
    top.className = "op-top";
    const previewShell = document.createElement("div");
    previewShell.className = "preview-shell";
    const preview = makePreview(asset);
    const hint = document.createElement("div");
    hint.className = "preview-hint";
    hint.textContent = "点开预览";
    previewShell.append(preview, hint);
    const body = document.createElement("div");
    body.innerHTML = `
      <div><span class="pill">操作 #${operation.id}</span><span class="pill">${operation.status}</span><span class="pill">${operation.operation_type}</span></div>
      <h3 style="margin:4px 0 8px;">${asset.file_name || "未知文件"}</h3>
      <div class="meta">下面列出同 MD5 的所有副本。橙色是准备隔离的重复位置，绿色是建议保留的已存在位置。</div>
      <div class="actions"></div>
    `;
    const actions = body.querySelector(".actions");
    if (operation.status === "planned") {
      const exclude = document.createElement("button");
      exclude.className = "danger";
      exclude.textContent = "排除这个文件，不隔离";
      exclude.addEventListener("click", () => excludeOperation(operation.id));
      actions.append(exclude);
    }
    top.append(previewShell, body);
    const copies = document.createElement("div");
    copies.className = "copy-list";
    const duplicateAssets = operation.duplicate_assets || [];
    if (duplicateAssets.length) copies.replaceChildren(...duplicateAssets.map(copyCard));
    else copies.innerHTML = `<div class="copy duplicate_target"><strong>重复位置，将隔离</strong><div class="path"></div></div>`;
    const fallbackPath = copies.querySelector(".path");
    if (!duplicateAssets.length && fallbackPath) fallbackPath.textContent = operation.from_path;
    node.append(top, copies);
    return node;
  }));
};

export const loadBatches = async () => {
  setStatus("正在加载批次...");
  const data = await jsonFetch("/operations/batches");
  state.batches = data.items;
  renderBatches();
  setStatus("批次已加载。");
};

export const selectBatch = async (batchId) => {
  state.batchId = batchId;
  state.offset = 0;
  renderBatches();
  el("ops-title").textContent = `批次 #${batchId}`;
  await loadOperations();
  explainSelectedBatchConfirmState();
};

export const loadOperations = async () => {
  if (!state.batchId) return;
  const filter = el("status-filter").value;
  const params = new URLSearchParams({limit: String(state.limit), offset: String(state.offset)});
  if (filter) params.set("status", filter);
  setStatus("正在加载操作明细...");
  const data = await jsonFetch(`/operations/batches/${state.batchId}/operations?${params}`);
  state.total = data.total;
  renderOperations(data.items);
  el("prev-page").disabled = state.offset <= 0;
  el("next-page").disabled = state.offset + state.limit >= state.total;
  const start = state.total === 0 ? 0 : state.offset + 1;
  const end = Math.min(state.offset + data.items.length, state.total);
  setStatus(`已显示 ${fmt(start)}-${fmt(end)} / ${fmt(state.total)} 项。`);
};

export const movePage = async (direction) => {
  const nextOffset = Math.max(0, state.offset + direction * state.limit);
  if (nextOffset === state.offset || nextOffset >= state.total) return;
  state.offset = nextOffset;
  await loadOperations();
};

export const excludeOperation = async (operationId) => {
  if (!confirm(`确认排除操作 #${operationId}？排除后这个文件不会被隔离。`)) return;
  await jsonFetch(`/operations/${operationId}/exclude`, {method: "POST", auth: true});
  await loadOperations();
  await loadBatches();
  await loadProgress();
  setStatus(`已排除操作 #${operationId}。`);
};

export const confirmBatch = async () => {
  const batch = selectedBatch();
  const blocker = batchConfirmBlocker(batch);
  if (blocker) {
    setStatus(blocker);
    updateBatchActionState();
    return;
  }
  if (!confirm(`确认批次 #${batch.id}？这只会标记确认，不会移动文件。`)) return;
  const result = await jsonFetch(`/operations/batches/${batch.id}/confirm`, {method: "POST", auth: true});
  await loadBatches();
  await loadOperations();
  await loadProgress();
  setStatus(`批次 #${result.batch_id} 已确认 ${fmt(result.operations)} 项。执行隔离仍需命令行单独执行。`);
};

export const initDuplicates = () => {
  el("status-filter").addEventListener("change", () => {
    state.offset = 0;
    loadOperations().catch((error) => setStatus(`加载失败：${error.message}`));
  });
  el("prev-page").addEventListener("click", () => movePage(-1));
  el("next-page").addEventListener("click", () => movePage(1));
  el("confirm-batch").addEventListener("click", (event) => {
    withButtonLoading(event.currentTarget, "确认中...", confirmBatch)
      .then(updateBatchActionState)
      .catch((error) => {
        updateBatchActionState();
        setStatus(`确认批次失败：${error.message}`);
      });
  });
};
