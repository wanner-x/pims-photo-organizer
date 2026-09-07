import { jsonFetch } from "./api.js";
import { el, fmt, setStatus, withButtonLoading } from "./dom.js";
import { state } from "./state.js";
import { loadProgress } from "./progress.js";
import { loadSeries } from "./series.js";

export const renderArchiveOverview = (overview) => {
  state.archiveOverview = overview;
  const planning = overview?.planning || {};
  const executions = overview?.executions || {};
  el("archive-planning-summary").innerHTML = `
    <div><strong>自动通过：</strong>${fmt(planning.auto_apply || 0)}</div>
    <div><strong>自动通过待抽检：</strong>${fmt(planning.auto_apply_sampled || 0)}</div>
    <div><strong>人工审核：</strong>${fmt(planning.manual_review || 0)}</div>
  `;
  el("archive-execution-summary").innerHTML = `
    <div><strong>执行成功：</strong>${fmt(executions.done || 0)}</div>
    <div><strong>已回滚：</strong>${fmt(executions.rolled_back || 0)}</div>
    <div><strong>执行失败：</strong>${fmt(executions.failed || 0)}</div>
  `;
  el("archive-risk-summary").innerHTML = `
    <div><strong>风险事件总数：</strong>${fmt(overview?.risk_events || 0)}</div>
  `;
};

export const renderArchiveAnomalies = (items) => {
  state.archiveAnomalies = items || [];
  if (!state.archiveAnomalies.length) {
    el("anomaly-list").innerHTML = `<div class="empty">当前没有异常项。</div>`;
    return;
  }
  el("anomaly-list").replaceChildren(...state.archiveAnomalies.map((item) => {
    const node = document.createElement("article");
    node.className = "series-card";
    node.innerHTML = `
      <span class="pill">${item.event_type}</span>
      <strong>${item.candidate?.title || "未命名候选"}</strong>
      <div class="meta"></div>
      <div class="series-plan">
        <div><strong>决策：</strong>${item.decision_type || "-"}</div>
        <div><strong>原因：</strong>${item.decision_reason || "-"}</div>
        <div><strong>细节：</strong>${JSON.stringify(item.details || {}, null, 0)}</div>
      </div>
    `;
    node.querySelector(".meta").textContent = item.candidate?.source_root || "";
    return node;
  }));
};

export const renderArchiveSampling = (items) => {
  state.archiveSampling = items || [];
  if (!state.archiveSampling.length) {
    el("sampling-list").innerHTML = `<div class="empty">当前没有待抽检项目。</div>`;
    return;
  }
  el("sampling-list").replaceChildren(...state.archiveSampling.map((item) => {
    const node = document.createElement("article");
    node.className = "series-card";
    node.innerHTML = `
      <span class="pill">${item.decision_type}</span>
      <strong>${item.candidate?.title || "未命名候选"}</strong>
      <div class="meta"></div>
      <div class="series-plan">
        <div><strong>规则分：</strong>${item.rule_score ?? "-"}</div>
        <div><strong>AI 分：</strong>${item.ai_score ?? "-"}</div>
        <div><strong>风险分：</strong>${item.risk_score ?? "-"}</div>
        <div><strong>原因：</strong>${item.decision_reason || "-"}</div>
      </div>
    `;
    node.querySelector(".meta").textContent = item.candidate?.source_root || "";
    return node;
  }));
};

export const renderArchiveLedger = (items) => {
  state.archiveLedger = items || [];
  if (!state.archiveLedger.length) {
    el("ledger-list").innerHTML = `<div class="empty">当前没有执行记录。</div>`;
    return;
  }
  el("ledger-list").replaceChildren(...state.archiveLedger.map((item) => {
    const node = document.createElement("article");
    node.className = "series-card";
    node.innerHTML = `
      <span class="pill">执行 #${item.id}</span>
      <span class="pill">${item.status}</span>
      <strong>${item.candidate_title || "未命名候选"}</strong>
      <div class="meta"></div>
      <div class="series-plan">
        <div><strong>决策：</strong>${item.decision_type || "-"}</div>
        <div><strong>来源：</strong>${item.source_path || "-"}</div>
        <div><strong>目标：</strong>${item.target_path || "-"}</div>
        <div><strong>原因：</strong>${item.decision_reason || "-"}</div>
      </div>
      <div class="actions">
        <button class="warn" data-action="rollback" ${item.status === "done" ? "" : "disabled"}>回滚这次移动</button>
      </div>
    `;
    node.querySelector(".meta").textContent = item.source_root || "";
    node.querySelector('[data-action="rollback"]').addEventListener("click", (event) => {
      withButtonLoading(event.currentTarget, "回滚中...", () => rollbackExecution(item.id)).catch((error) => {
        setStatus(`回滚失败：${error.message}`);
      });
    });
    return node;
  }));
};

export const loadArchiveOverview = async () => {
  const data = await jsonFetch("/review/archive/overview");
  renderArchiveOverview(data);
};

export const loadArchiveSampling = async () => {
  const data = await jsonFetch("/review/archive/sampling?limit=30");
  renderArchiveSampling(data.items);
};

export const loadArchiveAnomalies = async () => {
  const data = await jsonFetch("/review/archive/anomalies?limit=30");
  renderArchiveAnomalies(data.items);
};

export const loadArchiveLedger = async () => {
  const data = await jsonFetch("/review/archive/executions?limit=30");
  renderArchiveLedger(data.items);
};

export const rollbackExecution = async (executionId) => {
  setStatus(`正在回滚执行记录 #${executionId}...`);
  await jsonFetch(`/review/archive/executions/${executionId}/rollback`, {method: "POST", auth: true});
  await Promise.all([loadSeries(), loadProgress(), loadArchiveOverview(), loadArchiveAnomalies(), loadArchiveLedger()]);
  setStatus(`执行记录 #${executionId} 已回滚。`);
};

export const initArchive = () => {
  el("refresh-archive-overview").addEventListener("click", () => loadArchiveOverview().catch((error) => setStatus(`自动归档概览加载失败：${error.message}`)));
  el("refresh-sampling").addEventListener("click", () => loadArchiveSampling().catch((error) => setStatus(`抽检队列加载失败：${error.message}`)));
  el("refresh-anomalies").addEventListener("click", () => loadArchiveAnomalies().catch((error) => setStatus(`异常队列加载失败：${error.message}`)));
  el("refresh-ledger").addEventListener("click", () => loadArchiveLedger().catch((error) => setStatus(`执行账本加载失败：${error.message}`)));
};
