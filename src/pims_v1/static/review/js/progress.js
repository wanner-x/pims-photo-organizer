import { jsonFetch } from "./api.js";
import { el, fmt, setStatus } from "./dom.js";

export const renderProgress = (progress) => {
  const assets = progress.assets || {};
  el("asset-total").textContent = fmt(assets.total);
  el("md5-value").textContent = `${fmt(assets.md5_done)} / ${fmt(assets.total)} (${assets.md5_percent ?? 0}%)`;
  el("phash-value").textContent = `${fmt(assets.phash_done)} / ${fmt(assets.phash_total ?? 0)} (${assets.phash_percent ?? 0}%)`;
  el("md5-bar").style.width = `${assets.md5_percent ?? 0}%`;
  el("phash-bar").style.width = `${assets.phash_percent ?? 0}%`;
  el("review-pending").textContent = fmt(progress.reviews?.pending ?? 0);
  const planned = progress.operations?.planned ?? 0;
  const confirmed = progress.operations?.confirmed ?? 0;
  const excluded = progress.operations?.excluded ?? 0;
  el("operation-summary").textContent = `待确认操作 ${fmt(planned)}，已确认 ${fmt(confirmed)}，已排除 ${fmt(excluded)}`;
  const tasks = progress.tasks || [];
  const taskText = tasks.length
    ? tasks.map((task) => `${task.task_type}/${task.status}: ${fmt(task.count)}`).join("；")
    : "暂无任务";
  el("task-summary").textContent = taskText;
};

export const renderLog = (payload) => {
  if (!payload.found) {
    el("log-tail").textContent = "还没有检测日志。";
    return;
  }
  el("log-tail").textContent = [`日志：${payload.name}`, ...(payload.lines || [])].join("\n");
};

export const loadProgress = async () => {
  const data = await jsonFetch("/progress/summary");
  renderProgress(data);
};

export const loadLog = async () => {
  const data = await jsonFetch("/progress/logs/latest?lines=80");
  renderLog(data);
};

export const initProgress = () => {
  el("refresh-log").addEventListener("click", () => loadLog().catch((error) => setStatus(`日志加载失败：${error.message}`)));
};
