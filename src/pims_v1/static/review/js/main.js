import { el, setStatus } from "./dom.js";
import { state, viewNames } from "./state.js";
import { loadProgress, loadLog, initProgress } from "./progress.js";
import { loadSeries, initSeries } from "./series.js";
import {
  loadArchiveOverview,
  loadArchiveSampling,
  loadArchiveAnomalies,
  loadArchiveLedger,
  initArchive,
} from "./archive.js";
import { loadBatches, loadOperations, initDuplicates } from "./duplicates.js";
import { initPreview } from "./preview.js";
import { connectProgressSocket } from "./ws.js";

const refreshActiveView = async () => {
  if (state.activeView === "overview") {
    await Promise.all([loadProgress(), loadLog()]);
    return;
  }
  if (state.activeView === "series") {
    await Promise.all([loadProgress(), loadSeries()]);
    return;
  }
  if (state.activeView === "archive") {
    await Promise.all([loadProgress(), loadArchiveOverview()]);
    return;
  }
  if (state.activeView === "sampling") {
    await Promise.all([loadProgress(), loadArchiveSampling()]);
    return;
  }
  if (state.activeView === "anomalies") {
    await Promise.all([loadProgress(), loadArchiveAnomalies()]);
    return;
  }
  if (state.activeView === "ledger") {
    await Promise.all([loadProgress(), loadArchiveLedger()]);
    return;
  }
  await Promise.all([loadProgress(), loadBatches()]);
  if (state.batchId) await loadOperations();
};

const switchView = (view, updateHash = true) => {
  const nextView = viewNames.has(view) ? view : "overview";
  state.activeView = nextView;
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.viewPanel !== nextView;
  });
  document.querySelectorAll("[data-view-target]").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.viewTarget === nextView);
  });
  if (updateHash) history.replaceState(null, "", `#${nextView}`);
  refreshActiveView().catch((error) => setStatus(`刷新失败：${error.message}`));
};

const refreshAll = async () => {
  await Promise.all([
    loadProgress(),
    loadBatches(),
    loadSeries(),
    loadLog(),
    loadArchiveOverview(),
    loadArchiveSampling(),
    loadArchiveAnomalies(),
    loadArchiveLedger(),
  ]);
  if (state.batchId) await loadOperations();
};

document.querySelectorAll("[data-view-target]").forEach((tab) => {
  tab.addEventListener("click", () => switchView(tab.dataset.viewTarget));
});
window.addEventListener("hashchange", () => switchView(window.location.hash.slice(1), false));
el("refresh").addEventListener("click", () => refreshActiveView().catch((error) => setStatus(`刷新失败：${error.message}`)));
initProgress();
initSeries();
initArchive();
initDuplicates();
initPreview();
switchView(window.location.hash.slice(1) || "overview", false);
connectProgressSocket();
