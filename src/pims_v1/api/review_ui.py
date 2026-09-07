from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["review-ui"])

# 页面样式与交互逻辑位于 pims_v1/static/review/ 下，由 /static 静态路由提供：
# - /static/review/review.css      页面样式（含移动端适配）
# - /static/review/js/main.js      前端入口（原生 ES modules，零构建）
REVIEW_UI_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PIMS Review - 照片整理审核台</title>
  <link rel="stylesheet" href="/static/review/review.css">
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
  <script type="module" src="/static/review/js/main.js"></script>
</body>
</html>
"""


@router.get("/review-ui", response_class=HTMLResponse)
def review_ui() -> str:
    return REVIEW_UI_HTML
