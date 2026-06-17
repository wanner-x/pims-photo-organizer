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
      overflow-x: hidden;
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
    button[aria-busy="true"]::after {
      content: "";
      display: inline-block;
      width: .8em;
      height: .8em;
      margin-left: .5em;
      border: 2px solid currentColor;
      border-right-color: transparent;
      border-radius: 999px;
      vertical-align: -0.1em;
      animation: spin .7s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
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
    .runtime-panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 15px;
      box-shadow: var(--shadow);
      display: grid;
      gap: 10px;
    }
    .view-nav {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      padding: 6px 0 2px;
    }
    .view-tab {
      border-radius: 18px;
      padding: 11px 14px;
      text-align: left;
      background: rgba(255, 255, 255, .74);
      border: 1px solid var(--line);
      min-width: min(100%, 210px);
      box-shadow: 0 10px 28px rgba(37, 103, 94, .08);
    }
    .view-tab.active {
      background: linear-gradient(135deg, rgba(66, 184, 131, .18), rgba(124, 201, 232, .18));
      outline: 3px solid rgba(22, 143, 159, .14);
    }
    .view-tab span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
      margin-top: 2px;
    }
    .view-panel[hidden] { display: none !important; }
    .runtime-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
    }
    pre.log-tail {
      margin: 0;
      max-height: 180px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-all;
      border-radius: 16px;
      padding: 12px;
      color: #dff9ee;
      background: #15312d;
      font: 12px/1.55 Consolas, "Cascadia Mono", monospace;
    }
    .series-review-panel {
      margin: 0 clamp(16px, 4vw, 54px) 16px;
    }
    .series-list {
      padding: 14px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 12px;
    }
    .series-bulk-bar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: rgba(247, 252, 249, .78);
    }
    .series-bulk-bar .meta { margin-right: auto; }
    .series-card {
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 14px;
      background: rgba(255, 255, 255, .76);
      display: grid;
      gap: 10px;
      min-width: 0;
      overflow: hidden;
    }
    .series-card.selected {
      outline: 3px solid rgba(66, 184, 131, .22);
      background: #fbfffd;
    }
    .series-card[aria-busy="true"] {
      outline: 3px solid rgba(22, 143, 159, .18);
    }
    .series-card strong {
      overflow-wrap: anywhere;
    }
    .series-card-head {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 8px;
      align-items: start;
    }
    .series-card-head input {
      width: auto;
      min-width: 0;
      margin-top: 4px;
    }
    .series-card input {
      min-width: 0;
      width: 100%;
      border-radius: 14px;
    }
    .series-fields {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .series-plan {
      display: grid;
      gap: 5px;
      padding: 10px 12px;
      border: 1px dashed var(--line);
      border-radius: 16px;
      background: rgba(247, 252, 249, .76);
      color: var(--muted);
      overflow-wrap: anywhere;
      font-size: 13px;
    }
    .series-plan strong { color: var(--ink); }
    .series-assets {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
    }
    .series-assets img {
      width: 100%;
      aspect-ratio: 1;
      object-fit: cover;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #e6f4ef;
    }
    .series-busy {
      min-height: 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .series-busy.error { color: var(--danger); font-weight: 700; }
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
      grid-template-columns: minmax(180px, 32%) 1fr;
      gap: 14px;
      align-items: start;
    }
    .preview {
      width: 100%;
      aspect-ratio: 4 / 3;
      min-height: 150px;
      max-height: 320px;
      border-radius: 18px;
      object-fit: contain;
      background: linear-gradient(135deg, #dff3ee, #edf8ff);
      border: 1px solid var(--line);
      overflow: hidden;
      cursor: zoom-in;
    }
    video.preview { background: #102522; }
    .preview-shell {
      position: relative;
      display: grid;
      align-items: center;
      min-width: 0;
    }
    .preview-hint {
      position: absolute;
      right: 10px;
      bottom: 10px;
      padding: 4px 8px;
      border-radius: 999px;
      color: white;
      background: rgba(22, 49, 46, .68);
      font-size: 12px;
      pointer-events: none;
    }
    .preview-modal {
      position: fixed;
      inset: 0;
      z-index: 50;
      display: none;
      align-items: center;
      justify-content: center;
      padding: clamp(12px, 4vw, 40px);
      background: rgba(9, 28, 25, .82);
      backdrop-filter: blur(10px);
    }
    .preview-modal.open { display: flex; }
    .preview-modal img,
    .preview-modal video {
      max-width: min(96vw, 1600px);
      max-height: 88vh;
      border-radius: 18px;
      background: #071b18;
      box-shadow: 0 30px 90px rgba(0, 0, 0, .38);
      object-fit: contain;
    }
    .preview-modal button {
      position: fixed;
      right: 22px;
      top: 18px;
      color: white;
      background: rgba(255, 255, 255, .18);
      border-color: rgba(255, 255, 255, .28);
    }
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
      .op-top { grid-template-columns: minmax(160px, 38%) 1fr; }
    }
    @media (max-width: 560px) {
      .progress-grid { grid-template-columns: 1fr; }
      .op-top { grid-template-columns: 1fr; }
      .preview { width: 100%; min-height: 220px; }
    }
    @media (max-width: 720px) {
      header { padding: 18px 12px 12px; }
      main {
        grid-template-columns: 1fr;
        padding: 0 12px 26px;
      }
      .series-review-panel { margin: 0 12px 14px; }
      .section-head {
        position: sticky;
        top: 0;
        z-index: 5;
        align-items: flex-start;
        flex-direction: column;
        background: rgba(247, 252, 249, .96);
        backdrop-filter: blur(10px);
      }
      .toolbar,
      .actions {
        width: 100%;
      }
      .toolbar button,
      .toolbar select,
      .toolbar input,
      .actions button {
        width: 100%;
      }
      .view-nav { display: grid; grid-template-columns: 1fr; }
      .view-tab { width: 100%; }
      .series-list { grid-template-columns: 1fr; padding: 10px; }
      .series-fields { grid-template-columns: 1fr; }
      .series-assets { grid-template-columns: repeat(3, 1fr); }
      .series-assets img:nth-child(n+7) { display: none; }
      .series-bulk-bar {
        position: sticky;
        top: 74px;
        z-index: 45;
        margin: 10px;
        border: 1px solid var(--line);
        border-radius: 22px;
        background: rgba(247, 252, 249, .96);
        box-shadow: 0 18px 50px rgba(22, 49, 46, .22);
      }
      .series-bulk-bar .meta { width: 100%; }
      .series-bulk-bar button { flex: 1 1 130px; }
      .batch-list, .op-list { padding: 10px; }
      body { padding-bottom: 28px; }
    }
  </style>
</head>
<body>
  <!-- scan-r18 moderation-provider -->
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
    <nav class="view-nav" aria-label="审核功能导航">
      <button class="view-tab active" data-view-target="overview" type="button">总览进度<span>看全量检测、后台任务和日志</span></button>
      <button class="view-tab" data-view-target="series" type="button">AI 系列整理<span>审核 AI 命名、分类和 NAS 移动目标</span></button>
      <button class="view-tab" data-view-target="archive" type="button">自动归档概览<span>看自动执行、抽检和失败统计</span></button>
      <button class="view-tab" data-view-target="sampling" type="button">抽检队列<span>查看自动通过但需要抽样复核的项目</span></button>
      <button class="view-tab" data-view-target="anomalies" type="button">异常队列<span>只看需要人工介入的高风险项目</span></button>
      <button class="view-tab" data-view-target="ledger" type="button">执行账本<span>查看自动移动记录并支持回滚</span></button>
      <button class="view-tab" data-view-target="duplicates" type="button">重复隔离审核<span>对比已存在位置和重复位置，再确认隔离</span></button>
    </nav>
    <div id="view-overview" class="view-panel" data-view-panel="overview">
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
      <div class="runtime-panel">
        <div class="runtime-head">
          <div>
            <strong>后台任务状态</strong>
            <div class="meta" id="task-summary">任务队列加载中</div>
          </div>
          <button id="refresh-log">刷新日志</button>
        </div>
        <pre id="log-tail" class="log-tail">日志加载中...</pre>
      </div>
    </div>
  </header>
  <section id="view-series" class="series-review-panel view-panel" data-view-panel="series" hidden>
    <div class="section-head">
      <div>
        <h2>AI 系列整理审核</h2>
        <div class="meta">AI 只生成分类和命名建议。你确认后，系统会把该系列文件移动到 NAS 归档目录。</div>
      </div>
      <button id="refresh-series">刷新系列建议</button>
    </div>
    <div class="series-bulk-bar">
      <span id="series-selected-count" class="meta">已选择 0 个系列</span>
      <select id="series-filter" aria-label="系列筛选">
        <option value="all">全部</option>
        <option value="needs_ai">待 AI</option>
        <option value="pending_confirm">待确认</option>
        <option value="r18">R18</option>
        <option value="low_confidence">低置信度</option>
        <option value="target_conflict">目标冲突</option>
      </select>
      <button id="select-visible-series">全选当前页</button>
      <button id="clear-series-selection">清空选择</button>
      <button class="warn" id="batch-suggest-series">批量生成 AI 建议</button>
      <button class="primary" id="batch-confirm-series">批量确认并移动</button>
      <span id="series-bulk-status" class="series-busy" aria-live="polite"></span>
    </div>
    <div id="series-list" class="series-list">
      <div class="empty">系列候选加载中...</div>
    </div>
  </section>
  <section id="view-archive" class="series-review-panel view-panel" data-view-panel="archive" hidden>
    <div class="section-head">
      <div>
        <h2>自动归档概览</h2>
        <div class="meta">自动归档、抽检和失败统计。这里看系统最近自动做了什么。</div>
      </div>
      <button id="refresh-archive-overview">刷新概览</button>
    </div>
    <div class="series-list">
      <div class="series-card">
        <strong>规划状态</strong>
        <div class="series-plan" id="archive-planning-summary">加载中...</div>
      </div>
      <div class="series-card">
        <strong>执行状态</strong>
        <div class="series-plan" id="archive-execution-summary">加载中...</div>
      </div>
      <div class="series-card">
        <strong>风险事件</strong>
        <div class="series-plan" id="archive-risk-summary">加载中...</div>
      </div>
    </div>
  </section>
  <section id="view-sampling" class="series-review-panel view-panel" data-view-panel="sampling" hidden>
    <div class="section-head">
      <div>
        <h2>抽检队列</h2>
        <div class="meta">自动通过但需要抽检的项目，主要用于质量控制和漂移监控。</div>
      </div>
      <button id="refresh-sampling">刷新抽检</button>
    </div>
    <div id="sampling-list" class="series-list">
      <div class="empty">抽检队列加载中...</div>
    </div>
  </section>
  <section id="view-anomalies" class="series-review-panel view-panel" data-view-panel="anomalies" hidden>
    <div class="section-head">
      <div>
        <h2>异常队列</h2>
        <div class="meta">只显示需要人工处理的高风险项目，例如 R18、冲突或规则与 AI 分歧。</div>
      </div>
      <button id="refresh-anomalies">刷新异常</button>
    </div>
    <div id="anomaly-list" class="series-list">
      <div class="empty">异常队列加载中...</div>
    </div>
  </section>
  <section id="view-ledger" class="series-review-panel view-panel" data-view-panel="ledger" hidden>
    <div class="section-head">
      <div>
        <h2>执行账本</h2>
        <div class="meta">查看自动移动记录、决策依据和回滚入口。</div>
      </div>
      <button id="refresh-ledger">刷新账本</button>
    </div>
    <div id="ledger-list" class="series-list">
      <div class="empty">执行账本加载中...</div>
    </div>
  </section>
  <main id="view-duplicates" class="view-panel" data-view-panel="duplicates" hidden>
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
  <div id="preview-modal" class="preview-modal" aria-hidden="true">
    <button id="close-preview" type="button">关闭预览</button>
    <div id="preview-modal-content"></div>
  </div>
  <script>
    const viewNames = new Set(["overview", "series", "archive", "sampling", "anomalies", "ledger", "duplicates"]);
    const state = {
      activeView: "overview",
      batches: [],
      batchId: null,
      offset: 0,
      limit: 30,
      total: 0,
      series: [],
      archiveOverview: null,
      archiveSampling: [],
      archiveAnomalies: [],
      archiveLedger: [],
      selectedSeriesIds: new Set(),
    };
    const videoExts = new Set([".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"]);
    const imageExts = new Set([".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"]);
    const el = (id) => document.getElementById(id);
    const fmt = (value) => new Intl.NumberFormat("zh-CN").format(value ?? 0);
    const tokenHeader = () => {
      const token = el("token").value.trim();
      return token ? {"x-pims-api-token": token} : {};
    };
    const setStatus = (message) => { el("status").textContent = message; };
    const setBulkStatus = (message, isError = false) => {
      const node = el("series-bulk-status");
      node.textContent = message || "";
      node.classList.toggle("error", isError);
    };
    const setSeriesCardBusy = (candidateId, message = "", isError = false) => {
      const node = document.querySelector(`.series-card[data-candidate-id="${candidateId}"]`);
      if (!node) return;
      node.setAttribute("aria-busy", message && !isError ? "true" : "false");
      const busy = node.querySelector('[data-role="busy"]');
      if (!busy) return;
      busy.textContent = message;
      busy.classList.toggle("error", isError);
    };
    const withButtonLoading = async (button, loadingText, work) => {
      if (!button || button.disabled) return;
      const originalText = button.textContent;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.textContent = loadingText;
      try {
        return await work();
      } finally {
        button.textContent = originalText;
        button.removeAttribute("aria-busy");
        button.disabled = false;
      }
    };
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
    const renderLog = (payload) => {
      if (!payload.found) {
        el("log-tail").textContent = "还没有检测日志。";
        return;
      }
      el("log-tail").textContent = [`日志：${payload.name}`, ...(payload.lines || [])].join("\n");
    };
    const applySnapshot = (payload) => {
      if (!payload) return;
      if (payload.type === "error") {
        setStatus(payload.message || "自动刷新暂时失败，正在继续重试。");
        return;
      }
      if (payload.progress) renderProgress(payload.progress);
      if (payload.log) renderLog(payload.log);
      if (!state.batchId) loadBatches().catch(() => {});
    };
    const selectedBatch = () => state.batches.find((batch) => batch.id === state.batchId);
    const batchConfirmBlocker = (batch) => {
      if (!batch) return "请先选择一个包含操作的 planned 批次。";
      if (batch.status !== "planned") return `批次 #${batch.id} 当前状态是 ${batch.status}，不能确认。`;
      if ((batch.operation_count || 0) <= 0) return `批次 #${batch.id} 没有可确认操作。`;
      return "";
    };
    const updateBatchActionState = () => {
      const batch = selectedBatch();
      const canConfirm = Boolean(batch && batch.status === "planned" && (batch.operation_count || 0) > 0);
      const button = el("confirm-batch");
      button.disabled = !canConfirm;
      button.title = batchConfirmBlocker(batch).replace(/。$/, "");
    };
    const explainSelectedBatchConfirmState = () => {
      const reason = batchConfirmBlocker(selectedBatch());
      if (reason) setStatus(reason);
    };
    const renderBatches = () => {
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
    const renderSeries = () => {
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
    const renderArchiveOverview = (overview) => {
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
    const renderArchiveAnomalies = (items) => {
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
    const renderArchiveSampling = (items) => {
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
    const renderArchiveLedger = (items) => {
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
    const updateSeriesSelectionCount = () => {
      const count = state.selectedSeriesIds.size;
      el("series-selected-count").textContent = `已选择 ${fmt(count)} 个系列`;
    };
    const makePreview = (asset) => {
      const ext = (asset.file_ext || "").toLowerCase();
      if (videoExts.has(ext)) {
        const video = document.createElement("video");
        video.className = "preview";
        video.src = asset.media_url;
        video.muted = true;
        video.playsInline = true;
        video.preload = "metadata";
        video.addEventListener("click", (event) => {
          event.preventDefault();
          video.pause();
          openPreview(asset);
        });
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
      img.addEventListener("click", () => openPreview(asset));
      return img;
    };
    const pauseInlinePreviews = () => {
      document.querySelectorAll("video.preview").forEach((video) => {
        video.pause();
      });
    };
    const openPreview = (asset) => {
      pauseInlinePreviews();
      const modal = el("preview-modal");
      const content = el("preview-modal-content");
      content.replaceChildren();
      const ext = (asset.file_ext || "").toLowerCase();
      if (videoExts.has(ext)) {
        const video = document.createElement("video");
        video.src = asset.media_url;
        video.controls = true;
        video.autoplay = true;
        content.append(video);
      } else {
        const img = document.createElement("img");
        img.alt = asset.file_name || "预览";
        img.src = asset.media_url || asset.thumbnail_url;
        content.append(img);
      }
      modal.classList.add("open");
      modal.setAttribute("aria-hidden", "false");
    };
    const closePreview = () => {
      const modal = el("preview-modal");
      el("preview-modal-content").replaceChildren();
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
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
    const loadProgress = async () => {
      const data = await jsonFetch("/progress/summary");
      renderProgress(data);
    };
    const loadLog = async () => {
      const data = await jsonFetch("/progress/logs/latest?lines=80");
      renderLog(data);
    };
    const loadBatches = async () => {
      setStatus("正在加载批次...");
      const data = await jsonFetch("/operations/batches");
      state.batches = data.items;
      renderBatches();
      setStatus("批次已加载。");
    };
    const loadSeries = async () => {
      const params = new URLSearchParams({limit: "20"});
      const filterValue = el("series-filter")?.value || "all";
      if (filterValue !== "all") params.set("filter", filterValue);
      const data = await jsonFetch(`/review/series?${params}`);
      state.series = data.items;
      renderSeries();
    };
    const loadArchiveOverview = async () => {
      const data = await jsonFetch("/review/archive/overview");
      renderArchiveOverview(data);
    };
    const loadArchiveSampling = async () => {
      const data = await jsonFetch("/review/archive/sampling?limit=30");
      renderArchiveSampling(data.items);
    };
    const loadArchiveAnomalies = async () => {
      const data = await jsonFetch("/review/archive/anomalies?limit=30");
      renderArchiveAnomalies(data.items);
    };
    const loadArchiveLedger = async () => {
      const data = await jsonFetch("/review/archive/executions?limit=30");
      renderArchiveLedger(data.items);
    };
    const suggestSeries = async (candidateId) => {
      setStatus(`正在为候选 #${candidateId} 生成 AI 分类/命名...`);
      setSeriesCardBusy(candidateId, "正在调用 AI 生成分类/命名，请稍候...");
      await jsonFetch(`/review/series/${candidateId}/suggest-ai`, {method: "POST", auth: true});
      await loadSeries();
      setStatus(`候选 #${candidateId} 的 AI 建议已生成，请审核后确认。`);
      setBulkStatus("");
    };
    const scanSeriesR18 = async (candidateId) => {
      setStatus(`正在为候选 #${candidateId} 执行 scan-r18 ...`);
      setSeriesCardBusy(candidateId, "正在扫描视觉 R18 风险...");
      await jsonFetch(`/review/series/${candidateId}/scan-r18`, {method: "POST", auth: true});
      await Promise.all([loadSeries(), loadArchiveOverview(), loadArchiveAnomalies()]);
      setStatus(`候选 #${candidateId} 的 scan-r18 已完成。`);
      setBulkStatus("");
    };
    const autoArchiveSeries = async (candidateId) => {
      setStatus(`正在为候选 #${candidateId} 执行双引擎自动归档...`);
      await jsonFetch(`/review/series/${candidateId}/auto-archive`, {method: "POST", auth: true});
      await Promise.all([loadSeries(), loadProgress(), loadArchiveOverview(), loadArchiveAnomalies(), loadArchiveLedger()]);
      setStatus(`候选 #${candidateId} 的双引擎自动归档已完成。`);
      setBulkStatus("");
    };
    const rollbackExecution = async (executionId) => {
      setStatus(`正在回滚执行记录 #${executionId}...`);
      await jsonFetch(`/review/archive/executions/${executionId}/rollback`, {method: "POST", auth: true});
      await Promise.all([loadSeries(), loadProgress(), loadArchiveOverview(), loadArchiveAnomalies(), loadArchiveLedger()]);
      setStatus(`执行记录 #${executionId} 已回滚。`);
    };
    const selectedSeries = () => state.series.filter((candidate) => state.selectedSeriesIds.has(candidate.id));
    const selectVisibleSeries = () => {
      state.series.forEach((candidate) => state.selectedSeriesIds.add(candidate.id));
      renderSeries();
    };
    const clearSeriesSelection = () => {
      state.selectedSeriesIds.clear();
      renderSeries();
    };
    const batchSuggestSeries = async () => {
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
    const confirmSeries = async (candidate, node) => {
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
    const batchConfirmSeries = async () => {
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
    const selectBatch = async (batchId) => {
      state.batchId = batchId;
      state.offset = 0;
      renderBatches();
      el("ops-title").textContent = `批次 #${batchId}`;
      await loadOperations();
      explainSelectedBatchConfirmState();
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
    el("refresh-series").addEventListener("click", () => loadSeries().catch((error) => setStatus(`系列加载失败：${error.message}`)));
    el("refresh-archive-overview").addEventListener("click", () => loadArchiveOverview().catch((error) => setStatus(`自动归档概览加载失败：${error.message}`)));
    el("refresh-sampling").addEventListener("click", () => loadArchiveSampling().catch((error) => setStatus(`抽检队列加载失败：${error.message}`)));
    el("refresh-anomalies").addEventListener("click", () => loadArchiveAnomalies().catch((error) => setStatus(`异常队列加载失败：${error.message}`)));
    el("refresh-ledger").addEventListener("click", () => loadArchiveLedger().catch((error) => setStatus(`执行账本加载失败：${error.message}`)));
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
    el("refresh-log").addEventListener("click", () => loadLog().catch((error) => setStatus(`日志加载失败：${error.message}`)));
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
    el("close-preview").addEventListener("click", closePreview);
    el("preview-modal").addEventListener("click", (event) => {
      if (event.target === el("preview-modal")) closePreview();
    });
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closePreview();
    });
    const connectProgressSocket = () => {
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
    switchView(window.location.hash.slice(1) || "overview", false);
    connectProgressSocket();
  </script>
</body>
</html>
"""


@router.get("/review-ui", response_class=HTMLResponse)
def review_ui() -> str:
    return REVIEW_UI_HTML
