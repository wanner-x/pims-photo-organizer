from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["review-ui"])


REVIEW_UI_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PIMS Review</title>
  <style>
    :root {
      --bg: #f3efe5;
      --panel: #fffaf0;
      --ink: #1f261f;
      --muted: #6e756a;
      --line: #d8cfbe;
      --accent: #1d5f53;
      --accent-2: #c8612f;
      --danger: #9c2f25;
      --shadow: 0 20px 60px rgba(49, 43, 31, .14);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      font: 15px/1.5 Georgia, "Noto Serif SC", "Microsoft YaHei", serif;
      background:
        radial-gradient(circle at 20% 0%, rgba(200, 97, 47, .18), transparent 32rem),
        radial-gradient(circle at 85% 20%, rgba(29, 95, 83, .16), transparent 28rem),
        linear-gradient(135deg, #f7f0df, var(--bg));
      min-height: 100vh;
    }
    header {
      padding: 36px clamp(18px, 5vw, 64px) 20px;
      display: grid;
      gap: 16px;
      grid-template-columns: 1fr;
    }
    h1 {
      margin: 0;
      font-size: clamp(34px, 6vw, 76px);
      letter-spacing: -.06em;
      line-height: .95;
    }
    .subtitle {
      max-width: 760px;
      color: var(--muted);
      font-size: 17px;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin-top: 8px;
    }
    input, select, button {
      border: 1px solid var(--line);
      background: rgba(255, 250, 240, .9);
      color: var(--ink);
      border-radius: 999px;
      padding: 10px 14px;
      font: inherit;
    }
    input { min-width: min(100%, 320px); }
    button {
      cursor: pointer;
      font-weight: 700;
      transition: transform .12s ease, background .12s ease;
    }
    button:hover { transform: translateY(-1px); }
    button.primary {
      background: var(--accent);
      color: #fffaf0;
      border-color: var(--accent);
    }
    button.warn {
      background: var(--accent-2);
      color: #fffaf0;
      border-color: var(--accent-2);
    }
    button.danger {
      background: var(--danger);
      color: #fffaf0;
      border-color: var(--danger);
    }
    main {
      display: grid;
      grid-template-columns: minmax(260px, 360px) 1fr;
      gap: 18px;
      padding: 0 clamp(18px, 5vw, 64px) 48px;
    }
    section {
      background: rgba(255, 250, 240, .82);
      border: 1px solid rgba(216, 207, 190, .9);
      border-radius: 28px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .section-head {
      padding: 18px 20px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    h2 {
      margin: 0;
      font-size: 18px;
      letter-spacing: -.02em;
    }
    .batch-list, .op-list { padding: 14px; display: grid; gap: 12px; }
    .batch {
      border: 1px solid var(--line);
      background: rgba(255,255,255,.42);
      border-radius: 20px;
      padding: 14px;
      cursor: pointer;
    }
    .batch.active { outline: 3px solid rgba(29, 95, 83, .22); }
    .meta { color: var(--muted); font-size: 13px; word-break: break-all; }
    .pill {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      background: rgba(29, 95, 83, .1);
      color: var(--accent);
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
      margin-right: 6px;
    }
    .op {
      display: grid;
      grid-template-columns: 132px 1fr;
      gap: 14px;
      align-items: start;
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 14px;
      background: rgba(255,255,255,.5);
    }
    .thumb {
      width: 132px;
      height: 132px;
      border-radius: 18px;
      object-fit: cover;
      background: linear-gradient(135deg, #d8cfbe, #f7f0df);
      border: 1px solid var(--line);
    }
    .path {
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 13px;
      word-break: break-all;
      background: rgba(31, 38, 31, .06);
      border-radius: 14px;
      padding: 10px;
      margin: 8px 0;
    }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .notice {
      padding: 12px 16px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      background: rgba(200, 97, 47, .08);
    }
    @media (max-width: 860px) {
      main { grid-template-columns: 1fr; }
      .op { grid-template-columns: 96px 1fr; }
      .thumb { width: 96px; height: 96px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>PIMS Review</h1>
      <div class="subtitle">待确认隔离批次审核页。这里可以查看将被隔离的重复文件、逐项排除误判、确认批次；页面不提供执行隔离，执行仍需单独调用命令。</div>
    </div>
    <div class="toolbar">
      <input id="token" type="password" placeholder="PIMS_API_TOKEN，可选">
      <button class="primary" id="refresh">刷新批次</button>
      <a href="/docs">API Docs</a>
    </div>
  </header>
  <main>
    <section>
      <div class="section-head">
        <h2>待确认隔离批次</h2>
        <span id="batch-count" class="meta">加载中</span>
      </div>
      <div id="batches" class="batch-list"></div>
      <div class="notice">只审核 planned/confirmed/executed 状态；真正移动文件前请先备份数据库。</div>
    </section>
    <section>
      <div class="section-head">
        <h2 id="ops-title">选择一个批次</h2>
        <div class="toolbar">
          <select id="status-filter">
            <option value="">全部状态</option>
            <option value="planned" selected>planned</option>
            <option value="excluded">excluded</option>
            <option value="confirmed">confirmed</option>
            <option value="executed">executed</option>
            <option value="failed">failed</option>
          </select>
          <button id="prev-page" disabled>上一页</button>
          <button id="next-page" disabled>下一页</button>
          <button class="warn" id="confirm-batch" disabled>确认当前批次</button>
        </div>
      </div>
      <div id="operations" class="op-list"></div>
      <div class="notice" id="status">等待操作。</div>
    </section>
  </main>
  <script>
    const state = { batches: [], batchId: null, offset: 0, limit: 200, total: 0 };
    const el = (id) => document.getElementById(id);
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
    const renderBatches = () => {
      el("batch-count").textContent = `${state.batches.length} 个批次`;
      el("batches").replaceChildren(...state.batches.map((batch) => {
        const node = document.createElement("div");
        node.className = `batch ${batch.id === state.batchId ? "active" : ""}`;
        node.innerHTML = `
          <div><span class="pill">#${batch.id}</span><span class="pill">${batch.status}</span><span class="pill">${batch.operation_count} 项</span></div>
          <strong>${batch.batch_type}</strong>
          <div class="meta"></div>
        `;
        node.querySelector(".meta").textContent = batch.description || "";
        node.addEventListener("click", () => selectBatch(batch.id));
        return node;
      }));
    };
    const renderOperations = (items) => {
      if (!items.length) {
        el("operations").innerHTML = `<div class="meta">这个筛选条件下没有操作。</div>`;
        return;
      }
      el("operations").replaceChildren(...items.map((operation) => {
        const asset = operation.asset || {};
        const node = document.createElement("article");
        node.className = "op";
        const img = document.createElement("img");
        img.className = "thumb";
        img.alt = asset.file_name || `operation ${operation.id}`;
        img.src = asset.thumbnail_url || "";
        img.onerror = () => { img.style.visibility = "hidden"; };
        const body = document.createElement("div");
        body.innerHTML = `
          <div><span class="pill">op #${operation.id}</span><span class="pill">${operation.status}</span><span class="pill">${operation.operation_type}</span></div>
          <strong></strong>
          <div class="path"></div>
          <div class="meta"></div>
          <div class="actions"></div>
        `;
        body.querySelector("strong").textContent = asset.file_name || "未知文件";
        body.querySelector(".path").textContent = operation.from_path;
        body.querySelector(".meta").textContent = `size=${asset.file_size ?? "?"} md5=${asset.hash_md5 || "-"} phash=${asset.hash_phash || "-"}`;
        const actions = body.querySelector(".actions");
        if (operation.status === "planned") {
          const exclude = document.createElement("button");
          exclude.className = "danger";
          exclude.textContent = "排除，不隔离";
          exclude.addEventListener("click", () => excludeOperation(operation.id));
          actions.append(exclude);
        }
        node.append(img, body);
        return node;
      }));
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
      const params = new URLSearchParams({
        limit: String(state.limit),
        offset: String(state.offset),
      });
      if (filter) params.set("status", filter);
      setStatus("正在加载操作...");
      const data = await jsonFetch(`/operations/batches/${state.batchId}/operations?${params}`);
      state.total = data.total;
      renderOperations(data.items);
      el("prev-page").disabled = state.offset <= 0;
      el("next-page").disabled = state.offset + state.limit >= state.total;
      const start = state.total === 0 ? 0 : state.offset + 1;
      const end = Math.min(state.offset + data.items.length, state.total);
      setStatus(`已加载 ${start}-${end} / ${state.total} 项。`);
    };
    const movePage = async (direction) => {
      const nextOffset = Math.max(0, state.offset + direction * state.limit);
      if (nextOffset === state.offset || nextOffset >= state.total) return;
      state.offset = nextOffset;
      await loadOperations();
    };
    const excludeOperation = async (operationId) => {
      if (!confirm(`确认排除操作 #${operationId}？排除后不会隔离这个文件。`)) return;
      await jsonFetch(`/operations/${operationId}/exclude`, {method: "POST", auth: true});
      await loadOperations();
      await loadBatches();
      setStatus(`已排除操作 #${operationId}。`);
    };
    const confirmBatch = async () => {
      if (!state.batchId) return;
      if (!confirm(`确认批次 #${state.batchId}？这只会标记确认，不会移动文件。`)) return;
      const result = await jsonFetch(`/operations/batches/${state.batchId}/confirm`, {method: "POST", auth: true});
      await loadBatches();
      await loadOperations();
      setStatus(`批次 #${result.batch_id} 已确认 ${result.operations} 项。执行隔离仍需命令行单独执行。`);
    };
    el("refresh").addEventListener("click", loadBatches);
    el("status-filter").addEventListener("change", () => {
      state.offset = 0;
      loadOperations();
    });
    el("prev-page").addEventListener("click", () => movePage(-1));
    el("next-page").addEventListener("click", () => movePage(1));
    el("confirm-batch").addEventListener("click", confirmBatch);
    loadBatches().catch((error) => setStatus(`加载失败：${error.message}`));
  </script>
</body>
</html>
"""


@router.get("/review-ui", response_class=HTMLResponse)
def review_ui() -> str:
    return REVIEW_UI_HTML
