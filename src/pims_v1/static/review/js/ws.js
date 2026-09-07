import { setStatus } from "./dom.js";
import { state } from "./state.js";
import { renderProgress, renderLog } from "./progress.js";
import { loadBatches } from "./duplicates.js";

export const applySnapshot = (payload) => {
  if (!payload) return;
  if (payload.type === "error") {
    setStatus(payload.message || "自动刷新暂时失败，正在继续重试。");
    return;
  }
  if (payload.progress) renderProgress(payload.progress);
  if (payload.log) renderLog(payload.log);
  if (!state.batchId) loadBatches().catch(() => {});
};

export const connectProgressSocket = () => {
  if (!("WebSocket" in window)) return;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws/progress`);
  socket.addEventListener("message", (event) => {
    try {
      applySnapshot(JSON.parse(event.data));
    } catch (error) {
      setStatus(`自动刷新数据解析失败：${error.message}`);
    }
  });
  socket.addEventListener("open", () => setStatus("已连接自动刷新。"));
  socket.addEventListener("close", () => {
    setStatus("自动刷新断开，5 秒后重连。");
    setTimeout(connectProgressSocket, 5000);
  });
  socket.addEventListener("error", () => socket.close());
};
