import { jsonFetch } from "./api.js";
import { el, fmt, setStatus, withButtonLoading } from "./dom.js";
import { state } from "./state.js";
import { loadProgress } from "./progress.js";
import { loadArchiveOverview, loadArchiveAnomalies, loadArchiveLedger } from "./archive.js";

export const setBulkStatus = (message, isError = false) => {
  const node = el("series-bulk-status");
  node.textContent = message || "";
  node.classList.toggle("error", isError);
};

export const setSeriesCardBusy = (candidateId, message = "", isError = false) => {
  const node = document.querySelector(`.series-card[data-candidate-id="${candidateId}"]`);
  if (!node) return;
  node.setAttribute("aria-busy", message && !isError ? "true" : "false");
  const busy = node.querySelector('[data-role="busy"]');
  if (!busy) return;
  busy.textContent = message;
  busy.classList.toggle("error", isError);
};

export const updateSeriesSelectionCount = () => {
  const count = state.selectedSeriesIds.size;
  el("series-selected-count").textContent = `已选择 ${fmt(count)} 个系列`;
};

export const renderSeries = () => {
  updateSeriesSelectionCount();
  if (!state.series.length) {
    el("series-list").innerHTML = `<div class="empty">暂无系列候选。后台检测会按文件夹自动生成候选。</div>`;
    return;
  }
  el("series-list").replaceChildren(...state.series.map((candidate) => {
    const suggestion = candidate.suggestion || {};
    const node = document.createElement("article");
    node.className = `series-card ${state.selectedSeriesIds.has(candidate.id) ? "selected" : ""}`;
    node.dataset.candidateId = String(candidate.id);
    if (suggestion.id) node.dataset.suggestionId = String(suggestion.id);
    node.innerHTML = `
      <div class="series-card-head">
        <input data-action="select" type="checkbox" aria-label="选择候选 #${candidate.id}">
        <div>
          <span class="pill">候选 #${candidate.id}</span>
          <span class="pill">${candidate.status}</span>
          <span class="pill">${fmt(candidate.asset_count)} 个文件</span>
        </div>
      </div>
      <strong>${suggestion.title || candidate.title || "待 AI 命名"}</strong>
      <div class="meta"></div>
      <div class="series-assets"></div>
      <div class="series-fields">
        <input data-field="title" placeholder="系列标题" value="">
        <input data-field="category" placeholder="分类，例如 写真合集" value="">
      </div>
      <div class="series-plan">
        <div><strong>规则建议：</strong><span data-role="rule-plan">-</span></div>
        <div><strong>目标路径：</strong><span data-role="archive-path">等待 AI 建议</span></div>
        <div><strong>标签：</strong><span data-role="content-tags">-</span></div>
        <div><strong>计划：</strong><span data-role="plan-summary">-</span></div>
        <div><strong>风险：</strong><span data-role="risk-flags">-</span></div>
      </div>
      <div class="actions">
        <button data-action="suggest">AI 生成分类/命名</button>
        <button class="primary" data-action="auto-archive">双引擎自动归档</button>
        <button class="primary" data-action="confirm" ${suggestion.id ? "" : "disabled"}>确认并移动到 NAS</button>
      </div>
      <div class="series-busy" data-role="busy" aria-live="polite"></div>
    `;
    node.setAttribute("aria-busy", "false");
    const checkbox = node.querySelector('[data-action="select"]');
    checkbox.checked = state.selectedSeriesIds.has(candidate.id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selectedSeriesIds.add(candidate.id);
      else state.selectedSeriesIds.delete(candidate.id);
      node.classList.toggle("selected", checkbox.checked);
      updateSeriesSelectionCount();
    });
    node.querySelector(".meta").textContent = candidate.source_root || "";
    node.querySelector('[data-field="title"]').value = suggestion.title || candidate.title || "";
    node.querySelector('[data-field="category"]').value = suggestion.category || "";
    const rulePlan = candidate.rule_plan || {};
    node.querySelector('[data-role="rule-plan"]').textContent = [rulePlan.archive_category, rulePlan.archive_title].filter(Boolean).join(" / ") || "-";
    node.querySelector('[data-role="archive-path"]').textContent = suggestion.archive_path || "等待 AI 建议";
    const tags = suggestion.tags || [];
    const r18Text = suggestion.r18_label ? `R18 ${Math.round((suggestion.r18_confidence || 0) * 100)}%` : "";
    node.querySelector('[data-role="content-tags"]').textContent = [r18Text, ...tags.filter((tag) => tag !== "R18")].filter(Boolean).join("；") || "未标记";
    node.querySelector('[data-role="plan-summary"]').textContent = suggestion.plan_summary || "-";
    node.querySelector('[data-role="risk-flags"]').textContent = [suggestion.r18_reason, ...(suggestion.risk_flags || [])].filter(Boolean).join("；") || "未标记风险";
    const assetBox = node.querySelector(".series-assets");
    const previews = (candidate.assets || []).slice(0, 8).map((asset) => {
      const img = document.createElement("img");
      img.alt = asset.file_name || "样例";
      img.src = asset.thumbnail_url;
      img.onerror = () => { img.style.visibility = "hidden"; };
      return img;
    });
    assetBox.replaceChildren(...previews);
    node.querySelector('[data-action="suggest"]').addEventListener("click", (event) => {
      withButtonLoading(event.currentTarget, "AI 生成中...", () => suggestSeries(candidate.id)).catch((error) => {
        setSeriesCardBusy(candidate.id, `AI 建议失败：${error.message}`, true);
        setStatus(`AI 建议失败：${error.message}`);
      });
    });
    node.querySelector('[data-action="auto-archive"]').addEventListener("click", (event) => {
      withButtonLoading(event.currentTarget, "自动归档中...", () => autoArchiveSeries(candidate.id)).catch((error) => {
        setSeriesCardBusy(candidate.id, `自动归档失败：${error.message}`, true);
        setStatus(`自动归档失败：${error.message}`);
      });
    });
    node.querySelector('[data-action="confirm"]').addEventListener("click", (event) => {
      withButtonLoading(event.currentTarget, "移动中...", () => confirmSeries(candidate, node)).catch((error) => {
        setSeriesCardBusy(candidate.id, `确认移动失败：${error.message}`, true);
        setStatus(`确认移动失败：${error.message}`);
      });
    });
    return node;
  }));
  updateSeriesSelectionCount();
};

export const loadSeries = async () => {
  const params = new URLSearchParams({limit: "20"});
  const filterValue = el("series-filter")?.value || "all";
  if (filterValue !== "all") params.set("filter", filterValue);
  const data = await jsonFetch(`/review/series?${params}`);
  state.series = data.items;
  renderSeries();
};

export const suggestSeries = async (candidateId) => {
  setStatus(`正在为候选 #${candidateId} 生成 AI 分类/命名...`);
  setSeriesCardBusy(candidateId, "正在调用 AI 生成分类/命名，请稍候...");
  await jsonFetch(`/review/series/${candidateId}/suggest-ai`, {method: "POST", auth: true});
  await loadSeries();
  setStatus(`候选 #${candidateId} 的 AI 建议已生成，请审核后确认。`);
  setBulkStatus("");
};

export const scanSeriesR18 = async (candidateId) => {
  setStatus(`正在为候选 #${candidateId} 执行 scan-r18 ...`);
  setSeriesCardBusy(candidateId, "正在扫描视觉 R18 风险...");
  await jsonFetch(`/review/series/${candidateId}/scan-r18`, {method: "POST", auth: true});
  await Promise.all([loadSeries(), loadArchiveOverview(), loadArchiveAnomalies()]);
  setStatus(`候选 #${candidateId} 的 scan-r18 已完成。`);
  setBulkStatus("");
};

export const autoArchiveSeries = async (candidateId) => {
  setStatus(`正在为候选 #${candidateId} 执行双引擎自动归档...`);
  await jsonFetch(`/review/series/${candidateId}/auto-archive`, {method: "POST", auth: true});
  await Promise.all([loadSeries(), loadProgress(), loadArchiveOverview(), loadArchiveAnomalies(), loadArchiveLedger()]);
  setStatus(`候选 #${candidateId} 的双引擎自动归档已完成。`);
  setBulkStatus("");
};

export const selectedSeries = () => state.series.filter((candidate) => state.selectedSeriesIds.has(candidate.id));

export const selectVisibleSeries = () => {
  state.series.forEach((candidate) => state.selectedSeriesIds.add(candidate.id));
  renderSeries();
};

export const clearSeriesSelection = () => {
  state.selectedSeriesIds.clear();
  renderSeries();
};

export const batchSuggestSeries = async () => {
  const targets = selectedSeries();
  if (!targets.length) {
    setStatus("请先选择要生成 AI 建议的系列。");
    setBulkStatus("请先勾选要生成 AI 建议的系列。", true);
    return;
  }
  if (!confirm(`批量为 ${fmt(targets.length)} 个系列生成 AI 分类/命名建议？`)) return;
  setBulkStatus(`正在批量生成 AI 建议：0 / ${fmt(targets.length)}`);
  let success = 0;
  let failed = 0;
  let firstError = "";
  for (const candidate of targets) {
    try {
      setSeriesCardBusy(candidate.id, "正在生成 AI 建议...");
      await jsonFetch(`/review/series/${candidate.id}/suggest-ai`, {method: "POST", auth: true});
      success += 1;
      setStatus(`批量 AI 建议进度：成功 ${fmt(success)}，失败 ${fmt(failed)}。`);
      setBulkStatus(`批量 AI 建议进度：成功 ${fmt(success)}，失败 ${fmt(failed)}，共 ${fmt(targets.length)}。`);
      setSeriesCardBusy(candidate.id, "AI 建议已生成。");
    } catch (error) {
      failed += 1;
      if (!firstError) firstError = error.message;
      setSeriesCardBusy(candidate.id, `AI 建议失败：${error.message}`, true);
      setBulkStatus(`批量 AI 建议进度：成功 ${fmt(success)}，失败 ${fmt(failed)}，共 ${fmt(targets.length)}。`, failed > 0);
    }
  }
  await loadSeries();
  const errorHint = firstError ? ` 首个错误：${firstError}` : "";
  setStatus(`批量 AI 建议完成：成功 ${fmt(success)}，失败 ${fmt(failed)}。${errorHint}`);
  setBulkStatus(`批量 AI 建议完成：成功 ${fmt(success)}，失败 ${fmt(failed)}。${errorHint}`, failed > 0);
};

export const confirmSeries = async (candidate, node) => {
  const suggestion = candidate.suggestion || {};
  if (!suggestion.id) return;
  const title = node.querySelector('[data-field="title"]').value.trim();
  const category = node.querySelector('[data-field="category"]').value.trim();
  if (!title || !category) {
    setStatus("确认前请填写系列标题和分类。");
    setSeriesCardBusy(candidate.id, "确认前请填写系列标题和分类。", true);
    return;
  }
  if (!confirm(`确认候选 #${candidate.id}？系统会移动 ${fmt(candidate.asset_count)} 个文件到 NAS：${category}/${title}`)) return;
  setSeriesCardBusy(candidate.id, "正在移动文件到 NAS...");
  const result = await jsonFetch(`/review/series-suggestions/${suggestion.id}/confirm`, {
    method: "POST",
    auth: true,
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({title, category}),
  });
  await Promise.all([loadSeries(), loadProgress()]);
  setStatus(`系列已确认并移动到 NAS：成功 ${fmt(result.moved)}，失败 ${fmt(result.failed)}。目标：${result.archive_path || "-"}`);
  setBulkStatus("");
};

export const batchConfirmSeries = async () => {
  const targets = selectedSeries().filter((candidate) => candidate.suggestion?.id);
  if (!targets.length) {
    setStatus("请选择已有 AI 建议的系列再批量确认。");
    setBulkStatus("请选择已有 AI 建议的系列再批量确认。", true);
    return;
  }
  const totalAssets = targets.reduce((sum, candidate) => sum + (candidate.asset_count || 0), 0);
  if (!confirm(`批量确认 ${fmt(targets.length)} 个系列，并移动约 ${fmt(totalAssets)} 个文件到 NAS？`)) return;
  setBulkStatus(`正在批量确认并移动：0 / ${fmt(targets.length)}`);
  let success = 0;
  let failed = 0;
  let firstError = "";
  for (const candidate of targets) {
    const node = document.querySelector(`.series-card[data-candidate-id="${candidate.id}"]`);
    const title = node?.querySelector('[data-field="title"]')?.value.trim() || candidate.suggestion.title;
    const category = node?.querySelector('[data-field="category"]')?.value.trim() || candidate.suggestion.category;
    try {
      setSeriesCardBusy(candidate.id, "正在确认并移动到 NAS...");
      const result = await jsonFetch(`/review/series-suggestions/${candidate.suggestion.id}/confirm`, {
        method: "POST",
        auth: true,
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({title, category}),
      });
      state.selectedSeriesIds.delete(candidate.id);
      success += 1;
      setStatus(`批量确认进度：成功 ${fmt(success)}，失败 ${fmt(failed)}。`);
      setBulkStatus(`批量确认进度：成功 ${fmt(success)}，失败 ${fmt(failed)}，共 ${fmt(targets.length)}。最新目标：${result.archive_path || "-"}`);
      setSeriesCardBusy(candidate.id, "已确认并移动。");
    } catch (error) {
      failed += 1;
      if (!firstError) firstError = error.message;
      setSeriesCardBusy(candidate.id, `确认移动失败：${error.message}`, true);
      setBulkStatus(`批量确认进度：成功 ${fmt(success)}，失败 ${fmt(failed)}，共 ${fmt(targets.length)}。`, true);
    }
  }
  await Promise.all([loadSeries(), loadProgress()]);
  const errorHint = firstError ? ` 首个错误：${firstError}` : "";
  setStatus(`批量确认并移动完成：成功 ${fmt(success)}，失败 ${fmt(failed)}。${errorHint}`);
  setBulkStatus(`批量确认并移动完成：成功 ${fmt(success)}，失败 ${fmt(failed)}。${errorHint}`, failed > 0);
};

export const initSeries = () => {
  el("refresh-series").addEventListener("click", () => loadSeries().catch((error) => setStatus(`系列加载失败：${error.message}`)));
  el("series-filter").addEventListener("change", () => {
    state.selectedSeriesIds.clear();
    loadSeries().catch((error) => setStatus(`系列筛选失败：${error.message}`));
  });
  el("select-visible-series").addEventListener("click", selectVisibleSeries);
  el("clear-series-selection").addEventListener("click", clearSeriesSelection);
  el("batch-suggest-series").addEventListener("click", (event) => {
    withButtonLoading(event.currentTarget, "批量生成中...", batchSuggestSeries).catch((error) => {
      setBulkStatus(`批量 AI 建议失败：${error.message}`, true);
      setStatus(`批量 AI 建议失败：${error.message}`);
    });
  });
  el("batch-confirm-series").addEventListener("click", (event) => {
    withButtonLoading(event.currentTarget, "批量移动中...", batchConfirmSeries).catch((error) => {
      setBulkStatus(`批量确认失败：${error.message}`, true);
      setStatus(`批量确认失败：${error.message}`);
    });
  });
};
