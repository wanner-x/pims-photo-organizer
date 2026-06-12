from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["review-ui"])


REVIEW_UI_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PIMS Review - 照片整理审核台</title>
  <style>
    :root {
      --bg: #eef9f4;
      --bg-soft: #f7fcf9;
      --panel: rgba(255, 255, 255, .86);
      --ink: #16312e;
      --muted: #60726f;
      --line: #cde6de;
      --mint: #42b883;
      --teal: #168f9f;
      --sky: #7cc9e8;
      --warn: #f2a65a;
      --danger: #d95d59;
      --keep: #e7f8ee;
      --dup: #fff1eb;
      --shadow: 0 22px 70px rgba(37, 103, 94, .13);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      font: 15px/1.55 "Microsoft YaHei UI", "Noto Sans SC", "PingFang SC", sans-serif;
      background:
        radial-gradient(circle at 8% -10%, rgba(124, 201, 232, .45), transparent 34rem),
        radial-gradient(circle at 88% 6%, rgba(66, 184, 131, .35), transparent 30rem),
        linear-gradient(135deg, #f7fffb 0%, var(--bg) 52%, #edf8ff 100%);
      min-height: 100vh;
    }
    a { color: var(--teal); font-weight: 700; text-decoration: none; }
    header {
      padding: 30px clamp(16px, 4vw, 54px) 16px;
      display: grid;
      gap: 18px;
    }
    .hero {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 20px;
      align-items: end;
    }
    h1 {
      margin: 0;
      font-size: clamp(30px, 5vw, 58px);
      letter-spacing: -.05em;
      line-height: 1;
    }
    .subtitle {
      max-width: 900px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 16px;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    input, select, button {
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, .9);
      color: var(--ink);
      border-radius: 999px;
      padding: 9px 13px;
      font: inherit;
    }
    input { min-width: min(100%, 280px); }
    button {
      cursor: pointer;
      font-weight: 700;
      transition: transform .12s ease, box-shadow .12s ease;
    }
    button:hover { transform: translateY(-1px); box-shadow: 0 8px 20px rgba(22, 143, 159, .14); }
    button:disabled { cursor: not-allowed; opacity: .48; transform: none; box-shadow: none; }
    button.primary {
      background: linear-gradient(135deg, var(--mint), var(--teal));
      color: white;
      border: 0;
    }
    button.warn {
      background: var(--warn);
      color: #fff;
      border-color: var(--warn);
    }
    button.danger {
      background: var(--danger);
      color: #fff;
      border-color: var(--danger);
    }
    .progress-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(150px, 1fr));
      gap: 12px;
    }
    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 15px;
      box-shadow: var(--shadow);
    }
    .metric .label { color: var(--muted); font-size: 13px; }
    .metric .value { font-size: 25px; font-weight: 800; margin: 4px 0; }
    .bar {
      height: 8px;
      border-radius: 99px;
      background: #dcefe9;
      overflow: hidden;
    }
    .bar span {
      display: block;
      height: 100%;
      width: 0;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--mint), var(--sky));
    }
    main {
      display: grid;
      grid-template-columns: minmax(280px, 370px) 1fr;
      gap: 16px;
      padding: 0 clamp(16px, 4vw, 54px) 42px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      overflow: hidden;
      backdrop-filter: blur(12px);
    }
    .section-head {
      padding: 17px 18px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    h2 { margin: 0; font-size: 18px; }
    .batch-list, .op-list { padding: 13px; display: grid; gap: 12px; }
    .batch {
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, .68);
      border-radius: 20px;
      padding: 13px;
      cursor: pointer;
    }
    .batch.active {
      outline: 3px solid rgba(66, 184, 131, .24);
      background: #f8fffb;
    }
    .meta { color: var(--muted); font-size: 13px; word-break: break-all; }
    .pill {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      background: rgba(22, 143, 159, .1);
      color: var(--teal);
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 800;
      margin: 0 6px 6px 0;
    }
    .op {
      display: grid;
      gap: 12px;
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 14px;
      background: rgba(255, 255, 255, .72);
    }
    .op-top {
      display: grid;
      grid-template-columns: 170px 1fr;
      gap: 14px;
      align-items: start;
    }
    .preview {
      width: 170px;
      height: 140px;
      border-radius: 18px;
      object-fit: cover;
      background: linear-gradient(135deg, #dff3ee, #edf8ff);
      border: 1px solid var(--line);
      overflow: hidden;
    }
    video.preview { background: #102522; }
    .path {
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 13px;
      word-break: break-all;
      border-radius: 14px;
      padding: 10px;
      margin: 7px 0;
      background: rgba(22, 143, 159, .07);
    }
    .copy-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 10px;
    }
    .copy {
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 11px;
      background: #fff;
    }
    .copy.keep_copy { background: var(--keep); border-color: #bde7cb; }
    .copy.duplicate_target { background: var(--dup); border-color: #ffd2bf; }
    .copy-title {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      font-weight: 800;
    }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .notice {
      padding: 12px 16px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      background: rgba(124, 201, 232, .12);
    }
    .empty { padding: 24px; color: var(--muted); }
    @media (max-width: 960px) {
      .hero, main { grid-template-columns: 1fr; }
      .progress-grid { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
      .op-top { grid-template-columns: 120px 1fr; }
      .preview { width: 120px; height: 104px; }
    }
    @media (max-width: 560px) {
      .progress-grid { grid-template-columns: 1fr; }
      .op-top { grid-template-columns: 1fr; }
      .preview { width: 100%; height: 210px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="hero">
      <div>
        <h1>PIMS Review</h1>
        <div class="subtitle">照片整理审核台。先看清楚“已存在位置”和“重复位置”，误判可以排除；确认批次只做标记，不会移动文件。真正隔离仍需你单独执行命令。</div>
      </div>
      <div class="toolbar">
        <input id="token" type="password" placeholder="PIMS_API_TOKEN，可选">
        <button class="primary" id="refresh">刷新数据</button>
        <a href="/docs">接口文档</a>
      </div>
    </div>
    <div class="progress-grid" aria-label="整理进度">
      <div class="metric">
        <div class="label">媒体文件总数</div>
        <div class="value" id="asset-total">-</div>
        <div class="meta">已完成全量索引的文件数量</div>
      </div>
      <div class="metric">
        <div class="label">MD5 精确重复检测</div>
        <div class="value" id="md5-value">-</div>
        <div class="bar"><span id="md5-bar"></span></div>
      </div>
      <div class="metric">
        <div class="label">pHash 相似图片检测</div>
        <div class="value" id="phash-value">-</div>
        <div class="bar"><span id="phash-bar"></span></div>
      </div>
      <div class="metric">
        <div class="label">待审核项目</div>
        <div class="value" id="review-pending">-</div>
        <div class="meta" id="operation-summary">操作计划加载中</div>
      </div>
    </div>
  </header>
  <main>
    <section>
      <div class="section-head">
        <h2>待确认隔离批次</h2>
        <span id="batch-count" class="meta">加载中</span>
      </div>
      <div id="batches" class="batch-list"></div>
      <div class="notice">建议先处理 planned 批次。确认前逐项检查，确认后仍不会立刻移动文件。</div>
    </section>
    <section>
      <div class="section-head">
        <h2 id="ops-title">请选择一个批次</h2>
        <div class="toolbar">
          <select id="status-filter" aria-label="状态筛选">
            <option value="">全部状态</option>
            <option value="planned" selected>待确认</option>
            <option value="excluded">已排除</option>
            <option value="confirmed">已确认</option>
            <option value="executed">已隔离</option>
            <option value="failed">失败</option>
          </select>
          <button id="prev-page" disabled>上一页</button>
          <button id="next-page" disabled>下一页</button>
          <button class="warn" id="confirm-batch" disabled>确认当前批次</button>
        </div>
      </div>
      <div id="operations" class="op-list">
        <div class="empty">左侧选择一个批次后，这里会显示每个重复文件的处理建议。</div>
      </div>
      <div class="notice" id="status">等待操作。</div>
    </section>
  </main>
  <script>
    const state = { batches: [], batchId: null, offset: 0, limit: 100, total: 0 };
    const videoExts = new Set([".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"]);
    const imageExts = new Set([".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"]);
    const el = (id) => document.getElementById(id);
    const fmt = (value) => new Intl.NumberFormat("zh-CN").format(value ?? 0);
    const tokenHeader = () => {
      const token = el("token").value.trim();
      return token ? {"x-pims-api-token": token} : {};
    };
    const setStatus = (message) => { el("status").textContent = message; };
    const jsonFetch = async (url, options = {}) => {
      const response = await fetch(url, {
        ...options,
        headers: {...(options.headers || {}), ...(options.auth ? tokenHeader() : {})},
      });
      if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
      return response.json();
    };
    const renderProgress = (progress) => {
      const assets = progress.assets || {};
      el("asset-total").textContent = fmt(assets.total);
      el("md5-value").textContent = `${fmt(assets.md5_done)} / ${fmt(assets.total)} (${assets.md5_percent ?? 0}%)`;
      el("phash-value").textContent = `${fmt(assets.phash_done)} / ${fmt(assets.total)} (${assets.phash_percent ?? 0}%)`;
      el("md5-bar").style.width = `${assets.md5_percent ?? 0}%`;
      el("phash-bar").style.width = `${assets.phash_percent ?? 0}%`;
      el("review-pending").textContent = fmt(progress.reviews?.pending ?? 0);
      const planned = progress.operations?.planned ?? 0;
      const confirmed = progress.operations?.confirmed ?? 0;
      const excluded = progress.operations?.excluded ?? 0;
      el("operation-summary").textContent = `待确认操作 ${fmt(planned)}，已确认 ${fmt(confirmed)}，已排除 ${fmt(excluded)}`;
    };
    const renderBatches = () => {
      el("batch-count").textContent = `${fmt(state.batches.length)} 个批次`;
      if (!state.batches.length) {
        el("batches").innerHTML = `<div class="empty">暂无批次。继续运行安全检测后会在这里出现审核项。</div>`;
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
    };
    const makePreview = (asset) => {
      const ext = (asset.file_ext || "").toLowerCase();
      if (videoExts.has(ext)) {
        const video = document.createElement("video");
        video.className = "preview";
        video.src = asset.media_url;
        video.controls = true;
        video.preload = "metadata";
        return video;
      }
      const img = document.createElement("img");
      img.className = "preview";
      img.alt = asset.file_name || "媒体预览";
      img.src = imageExts.has(ext) ? asset.thumbnail_url : "";
      img.onerror = () => {
        if (imageExts.has(ext) && img.src !== asset.media_url) img.src = asset.media_url;
        else img.style.visibility = "hidden";
      };
      return img;
    };
    const copyCard = (copy) => {
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
    const renderOperations = (items) => {
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
        const preview = makePreview(asset);
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
        top.append(preview, body);
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
    const loadProgress = async () => {
      const data = await jsonFetch("/progress/summary");
      renderProgress(data);
    };
    const loadBatches = async () => {
      setStatus("正在加载批次...");
      const data = await jsonFetch("/operations/batches");
      state.batches = data.items;
      renderBatches();
      setStatus("批次已加载。");
    };
    const selectBatch = async (batchId) => {
      state.batchId = batchId;
      state.offset = 0;
      renderBatches();
      el("ops-title").textContent = `批次 #${batchId}`;
      el("confirm-batch").disabled = false;
      await loadOperations();
    };
    const loadOperations = async () => {
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
    const movePage = async (direction) => {
      const nextOffset = Math.max(0, state.offset + direction * state.limit);
      if (nextOffset === state.offset || nextOffset >= state.total) return;
      state.offset = nextOffset;
      await loadOperations();
    };
    const excludeOperation = async (operationId) => {
      if (!confirm(`确认排除操作 #${operationId}？排除后这个文件不会被隔离。`)) return;
      await jsonFetch(`/operations/${operationId}/exclude`, {method: "POST", auth: true});
      await loadOperations();
      await loadBatches();
      await loadProgress();
      setStatus(`已排除操作 #${operationId}。`);
    };
    const confirmBatch = async () => {
      if (!state.batchId) return;
      if (!confirm(`确认批次 #${state.batchId}？这只会标记确认，不会移动文件。`)) return;
      const result = await jsonFetch(`/operations/batches/${state.batchId}/confirm`, {method: "POST", auth: true});
      await loadBatches();
      await loadOperations();
      await loadProgress();
      setStatus(`批次 #${result.batch_id} 已确认 ${fmt(result.operations)} 项。执行隔离仍需命令行单独执行。`);
    };
    const refreshAll = async () => {
      await Promise.all([loadProgress(), loadBatches()]);
      if (state.batchId) await loadOperations();
    };
    el("refresh").addEventListener("click", () => refreshAll().catch((error) => setStatus(`刷新失败：${error.message}`)));
    el("status-filter").addEventListener("change", () => {
      state.offset = 0;
      loadOperations().catch((error) => setStatus(`加载失败：${error.message}`));
    });
    el("prev-page").addEventListener("click", () => movePage(-1));
    el("next-page").addEventListener("click", () => movePage(1));
    el("confirm-batch").addEventListener("click", confirmBatch);
    refreshAll().catch((error) => setStatus(`加载失败：${error.message}`));
  </script>
</body>
</html>
"""


@router.get("/review-ui", response_class=HTMLResponse)
def review_ui() -> str:
    return REVIEW_UI_HTML
