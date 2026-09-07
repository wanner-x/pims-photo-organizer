# PIMS V1 —— 以 NAS 为归档中心的个人照片/视频整理系统

PIMS（Photo Integrity & Management System）V1 是一个运行在 Windows PC 上、以 NAS 作为最终归档位置的**个人图库整理系统**，面向 10 TB 级别的本地 + NAS 混合照片库。它负责索引、精确/相似重复检测、系列（套图）识别与归档命名、R18 内容抽样筛查、人工审核与批次化执行，并通过企业微信推送需要人工介入的事项。

> 当前实现状态、接手上下文、已知风险与后续路线图，请阅读 [docs/PROJECT_STATUS_AND_ROADMAP.md](docs/PROJECT_STATUS_AND_ROADMAP.md)。

---

## 目录

- [设计原则](#设计原则)
- [功能一览](#功能一览)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [环境变量](#环境变量)
- [典型工作流](#典型工作流)
- [后台长跑脚本](#后台长跑脚本)
- [审核页](#审核页)
- [CLI 命令一览](#cli-命令一览)
- [归档命名规则](#归档命名规则)
- [R18 检测](#r18-检测)
- [通知（企业微信）](#通知企业微信)
- [安全与恢复](#安全与恢复)
- [测试](#测试)
- [辅助脚本](#辅助脚本)
- [当前范围与限制](#当前范围与限制)

---

## 设计原则

1. **先检测、再审核、后执行。** 任何移动 / 隔离 / 删除都必须先进入"操作批次"，经人工确认后才能执行。
2. **AI 不决定物理归档层级。** 目标路径优先由确定性规则（目录名解析器）生成，AI 只提供标题润色、标签、风险提示等辅助字段。
3. **保留原目录中的信息。** 人物 / 厂牌 / 企划 / 期号 / 日期 / 规格（如 `[46P208MB]`）等信息原样保留，不做无脑归类。
4. **R18 只是叶子标签。** 只在最终目录名末尾追加 ` [R18]`，不改变一级归档分类。
5. **可中断、可恢复、可分批。** 所有长任务都以任务表驱动，支持中断后 `recover-tasks` 继续。
6. **不提交敏感信息。** `.env`、`data/`、`reports/` 均在 `.gitignore` 中，API key、Webhook、NAS 账号一律不进仓库。

---

## 功能一览

| 模块 | 说明 |
| --- | --- |
| 文件索引 | 索引本地目录与 NAS（UNC 路径）目录，记录路径、大小、mtime、媒体类型、宽高、时长等；SQLite 持久化，大批量可分批继续 |
| 精确重复检测 | MD5 哈希 + 分组；自动规划"保留 NAS 副本、隔离/删除冗余副本"的操作，进入审核批次 |
| 相似图片检测 | pHash（感知哈希）+ 分组，并发读取 NAS 隐藏 I/O 延迟（`PIMS_PHASH_CONCURRENCY`） |
| 系列（套图）识别 | 按目录聚合生成系列候选；目录名解析器识别人物 / 厂牌 / 企划 / 未知四类并输出归档分类、标题、元数据与置信度 |
| AI 辅助命名 | 通过 DeepSeek 文本模型为低置信度候选生成标题、分类、标签、风险提示；仅作为建议，确认后才移动 |
| 自动归档 | 规则与 AI 一致、或 AI 置信度 ≥ 阈值且无内容风险时，可按限额自动归档到 NAS |
| R18 抽样筛查 | 对系列封面 / 前中后抽样帧做本地 NSFW 判定，支持 `heuristic`（启发式）与 `onnx`（NudeNet 本地模型）两种后端 |
| 缩略图与预览 | 图片缩略图缓存；审核页支持图片预览、视频内联播放与弹窗 |
| 审核页（review-ui） | 三大功能区：总览进度、AI 系列整理、重复隔离审核；WebSocket 自动刷新；批量选择 / 批量生成 AI 建议 / 批量确认 |
| 操作批次 | `plan → confirm → execute` 三段式；支持排除单条操作、分片执行（`--limit`）、`delete` / `quarantine` 两种动作 |
| 自动精确重复处理 | 字节级完全一致的冗余副本可在保留副本仍存在的前提下自动批准并删除/隔离 |
| 任务队列 | MD5 / pHash / 缩略图等任务入队、多轮处理、失败重排、中断恢复 |
| 通知 | 企业微信 Webhook：同批次只推一次、已处理批次不重推、每小时限额、可选每日日报 |
| 备份 | 一条命令备份 SQLite 数据库并打标签 |

---

## 技术栈

- **语言 / 运行时**：Python 3.11+
- **Web 框架**：FastAPI + Uvicorn，WebSocket 进度推送
- **数据层**：SQLAlchemy 2.x + SQLite（默认 `./data/pims.db`），Alembic 已列入依赖
- **配置**：pydantic-settings（`.env`，前缀 `PIMS_`）
- **调度**：APScheduler
- **图像**：Pillow、imagehash
- **HTTP 客户端**：httpx（DeepSeek、企业微信）
- **可选**：onnxruntime + numpy（`pip install -e .[nsfw]`，启用 NudeNet ONNX 后端）
- **测试**：pytest

---

## 项目结构

```text
pims-v1/
├─ src/pims_v1/
│  ├─ main.py                  # FastAPI 应用入口
│  ├─ cli.py                   # `pims` 命令行（30 个子命令）
│  ├─ config.py                # Settings（PIMS_* 环境变量）
│  ├─ db.py                    # SQLite 引擎（WAL、busy timeout）
│  ├─ api/                     # REST / WebSocket 路由
│  │  ├─ libraries.py          #   图库
│  │  ├─ operations.py         #   操作批次（排除 / 确认）
│  │  ├─ progress.py           #   进度快照与 WebSocket
│  │  ├─ review.py             #   审核 API（系列 / 重复 / R18 扫描）
│  │  ├─ review_ui.py          #   审核页（挂载 static/review）
│  │  └─ tasks.py              #   任务队列
│  ├─ models/                  # SQLAlchemy 模型：asset / duplicate / similar / series / operation / notification …
│  ├─ repos/                   # 仓储层
│  ├─ services/                # 业务服务
│  │  ├─ index_service.py      #   索引
│  │  ├─ hash_index_service.py / phash_index_service.py     # MD5 / pHash
│  │  ├─ duplicate_index_service.py / similar_index_service.py
│  │  ├─ series_index_service.py / dirname_parser.py / archive_rule_planner.py
│  │  ├─ ai_naming_service.py / deepseek_client.py
│  │  ├─ archive_decision_service.py / archive_service.py / series_confirm_service.py
│  │  ├─ nsfw_detector.py / visual_moderation_service.py / series_moderation_service.py
│  │  ├─ operation_plan_service.py / delete_service.py
│  │  ├─ task_service.py / task_worker_service.py / progress_service.py
│  │  ├─ notification_service.py / backup_service.py / thumbnail_service.py
│  │  └─ safe_workflow_service.py   # 把上述步骤串成一轮"安全工作流"
│  ├─ static/review/           # 审核页的 CSS / JS（按功能拆分）
│  └─ workers/recovery_worker.py
├─ scripts/                    # 长跑脚本与一次性整理脚本（见下文）
├─ tests/                      # pytest（约 290 个用例）
├─ docs/
│  ├─ PROJECT_STATUS_AND_ROADMAP.md   # 状态、风险、路线图（必读）
│  ├─ superpowers/specs|plans/        # 设计文档与各阶段实施计划
│  └─ archive/                        # 历史愿景稿
├─ data/                       # 运行时数据（已忽略）：SQLite、缓存、隔离区、日志、模型
└─ reports/                    # 本地审计产物（已忽略）
```

---

## 快速开始

### 1. 创建虚拟环境并安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]          # 开发 + 测试
# 可选：本地 NudeNet ONNX NSFW 后端
pip install -e .[nsfw]
```

### 2. 配置环境变量

```powershell
copy .env.example .env
```

按需修改 `.env`（见下节）。`PIMS_KEEP_ROOT` 必须以 UTF-8 保存，且与索引时使用的 NAS 路径**完全一致**，否则"优先保留 NAS 副本"的逻辑会静默失效。

### 3. 挂载 NAS 并启动 API

```powershell
# 先确认 NAS 共享已可访问（例如 \\NAS\photos\归档）
uvicorn pims_v1.main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/review-ui` 进入审核页。除非有带鉴权的反向代理，**不要**把 API 暴露到公网；设置 `PIMS_API_TOKEN` 后，所有会产生变更的接口都要求请求头 `x-pims-api-token`。

### 4. 运行测试

```powershell
python -m pytest -q
```

---

## 环境变量

所有变量以 `PIMS_` 为前缀，从 `.env` 读取（UTF-8 / UTF-8 with BOM 均可）。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PIMS_DATABASE_URL` | `sqlite:///./data/pims.db` | SQLAlchemy 数据库地址 |
| `PIMS_CACHE_ROOT` | `./data/.cache` | 缩略图等缓存目录 |
| `PIMS_QUARANTINE_ROOT` | `./data/.quarantine` | 隔离区（`quarantine` 动作的目标目录） |
| `PIMS_LOGS_ROOT` | `./data/logs` | 日志目录 |
| `PIMS_KEEP_ROOT` | 空 | NAS 归档根目录（UNC 路径），重复检测优先保留此目录下的副本，系列归档目标也在此目录下 |
| `PIMS_API_TOKEN` | 空 | 设置后，变更类 API 需携带 `x-pims-api-token` |
| `PIMS_MAX_IMAGE_PIXELS` | `300000000` | Pillow 解压炸弹上限，放大以便超大全景/扫描件也能哈希与缩略 |
| `PIMS_DUPLICATE_ACTION` | `quarantine` | 冗余精确重复副本的处理方式：`quarantine`（可逆）或 `delete`（直接删除，不占用额外空间） |
| `PIMS_AUTO_QUARANTINE_LIMIT` | `0` | 每轮工作流自动批准并处理的精确重复数量；`0` 表示只走人工审核 |
| `PIMS_AI_AUTO_APPLY_MIN_CONFIDENCE` | `0.85` | 规则与 AI 不一致且无内容风险时，AI 置信度达到该值即自动采用 AI 方案 |
| `PIMS_PHASH_CONCURRENCY` | `1` | pHash 读取 + 哈希的并发数；NAS I/O 受限时可设 4~8 |
| `PIMS_AI_SUGGEST_LIMIT` | `0` | 每轮工作流生成 AI 建议的数量上限 |
| `PIMS_DEEPSEEK_API_KEY` | 空 | DeepSeek API Key（可选，不配则跳过 AI 步骤） |
| `PIMS_DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek 接口地址 |
| `PIMS_DEEPSEEK_MODEL` | `deepseek-v4-flash` | 模型名 |
| `PIMS_DEEPSEEK_REASONING_EFFORT` | `low` | 推理强度 |
| `PIMS_DEEPSEEK_THINKING_ENABLED` | `false` | 是否开启 thinking |
| `PIMS_DEEPSEEK_MAX_TOKENS` | `600` | 单次生成 token 上限 |
| `PIMS_R18_PROVIDER` | `auto` | R18 判定提供方 |
| `PIMS_R18_SAMPLE_LIMIT` | `7` | 每个系列抽样帧数 |
| `PIMS_R18_HIGH_THRESHOLD` | `0.82` | 直接判定为 R18 的置信度阈值 |
| `PIMS_R18_REVIEW_THRESHOLD` | `0.55` | 进入人工复核的置信度阈值 |
| `PIMS_R18_SCAN_LIMIT` | `0` | 每轮工作流 R18 扫描数量上限 |
| `PIMS_NSFW_BACKEND` | `heuristic` | `heuristic`（启发式，无额外依赖）或 `onnx`（NudeNet 本地模型） |
| `PIMS_NSFW_ONNX_MODEL_PATH` | `./data/models/nudenet_classifier_model.onnx` | ONNX 模型路径，用 `scripts/download_nsfw_model.py` 下载 |
| `PIMS_WECHAT_WEBHOOK_URL` | 空 | 企业微信机器人 Webhook（可选） |
| `PIMS_WECHAT_HOURLY_LIMIT` | `3` | 每小时最多推送条数，`0` 不限；超限标记 `throttled`，下轮自动重试 |
| `PIMS_WECHAT_DIGEST` | `false` | `true` 时批次通知只入队，工作流结束后聚合为一条日报 |
| `PIMS_REVIEW_URL` | `http://127.0.0.1:8000/review-ui` | 通知中附带的审核页链接 |

---

## 典型工作流

以下以 `\\NAS\photos\归档` 代表 NAS 归档根目录，请替换为你自己的路径。

### 第一步：索引图库

```powershell
pims index-library "D:\图册" --name "PC Photos" --kind local
pims index-library "\\NAS\photos\归档" --name "NAS Photos" --kind nas
```

### 第二步：运行安全工作流（只生成审核数据，不移动文件）

```powershell
pims run-safe-workflow --keep-root "\\NAS\photos\归档" `
  --md5-limit 20000 --phash-limit 5000 --thumbnail-limit 2000 `
  --min-series-assets 2 --ai-suggest-limit 50 --r18-scan-limit 50
```

一轮工作流会依次：处理 MD5 / pHash 任务 → 重复 / 相似分组 → 系列候选 → 规则归档建议 → （可选）AI 建议 → （可选）R18 抽样 → 生成操作批次 → （可选）自动归档 / 自动精确重复处理 → 发送通知。运行中会周期性打印哈希进度。

### 第三步：审核

- 浏览器打开 `http://127.0.0.1:8000/review-ui`，在"重复隔离审核"中对比"已存在位置"与"重复位置"，排除误判后确认批次；
- 在"AI 系列整理"中审核规则建议与 AI 建议，确认后 PIMS 会创建正式系列并把文件移动到 `<PIMS_KEEP_ROOT>/<分类>/<标题>/`。

命令行等价操作：

```powershell
pims list-batches
pims exclude-operation <operation_id>
pims confirm-batch <batch_id>
```

### 第四步：备份后执行

```powershell
pims backup-db --label before-execute
pims execute-batch <batch_id> --action delete --limit 20000   # 分片执行，可多次调用续跑
```

`--action quarantine` 会把文件移动到 `PIMS_QUARANTINE_ROOT`（可逆）；`--action delete` 直接删除冗余副本。两种方式都要求一份字节级一致的保留副本仍在磁盘上。

### 精确重复自动处理（可选）

```powershell
pims auto-quarantine-duplicates --keep-root "\\NAS\photos\归档" --limit 500 --action delete
# 或在工作流中：
pims run-safe-workflow --keep-root "\\NAS\photos\归档" --auto-quarantine-limit 500
```

### 查看状态

```powershell
pims status
pims list-tasks
Invoke-RestMethod http://127.0.0.1:8000/progress/summary
```

---

## 后台长跑脚本

`scripts\run_full_detection.ps1` 用于在 PC 上无人值守地循环运行安全工作流，默认参数：

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| `-AiSuggestLimit` | `50` | 每轮 AI 建议数 |
| `-R18ScanLimit` | `50` | 每轮 R18 抽样数 |
| `-AutoArchiveLimit` | `20` | 每轮低风险自动归档数，`0` 关闭 |
| `-AutoQuarantineLimit` | `500` | 每轮精确重复自动批准数，`0` 关闭 |
| `-SeriesLimit` | `0` | 系列重建数量（全量扫描代价高，默认不做） |
| `-SimilarLimit` | `0` | 相似图分组数量（同上） |
| `-ExecuteConfirmedBatches` | `$true` | 自动执行已确认批次；`:$false` 则需手动 `execute-batch` |

```powershell
scripts\run_full_detection.ps1 -ExecuteConfirmedBatches -AiSuggestLimit 50 -R18ScanLimit 50 -AutoArchiveLimit 20 -SeriesLimit 0 -SimilarLimit 0
```

---

## 审核页

`GET /review-ui` 提供一个纯前端页面（静态资源位于 `src/pims_v1/static/review/`），分为三个功能区：

- **总览进度**：全量检测进度、任务队列、最近日志尾部，WebSocket（`/ws/progress`）自动刷新；
- **AI 系列整理**：候选筛选（全部 / 待 AI / 待确认 / R18 / 低置信度 / 目标冲突），并排展示规则建议与 AI 建议，支持批量生成建议、批量确认移动；
- **重复隔离审核**：列出隔离批次、对比重复路径与保留路径、预览缩略图 / 视频、排除单条操作、确认批次。

审核页**不会**直接执行移动或删除，执行必须走 `pims execute-batch` 或开启 `-ExecuteConfirmedBatches` 的长跑脚本。

---

## CLI 命令一览

安装后可用 `pims <子命令> --help` 查看参数。

| 类别 | 命令 |
| --- | --- |
| 索引 | `scan-sample`、`index-library` |
| 哈希 | `hash-md5`、`hash-phash`、`enqueue-md5-tasks`、`process-md5-tasks`、`enqueue-phash-tasks`、`process-phash-tasks` |
| 分组 | `build-duplicates`、`build-similar`、`build-series` |
| 系列 / AI | `list-series`、`suggest-series-title`、`confirm-series`、`auto-archive-series`、`scan-series-r18` |
| 操作批次 | `plan-duplicate-quarantine`、`list-batches`、`confirm-batch`、`exclude-operation`、`execute-batch`、`auto-quarantine-duplicates` |
| 任务 | `list-tasks`、`recover-tasks`、`reset-failed-tasks` |
| 缩略图 | `build-thumbnails` |
| 工作流 | `run-safe-workflow` |
| 运维 | `status`、`backup-db`、`notify-wechat` |

---

## 归档命名规则

目录名解析器（`services/dirname_parser.py`）把系列目录归入 **person（人物）/ studio（厂牌）/ project（企划）/ unknown** 四类，按五级模式优先级解析出人物、厂牌、编号、日期、主题、规格（P / V / MB 数值化）与 R18 标记，并给出置信度。`archive_rule_planner` 在置信度 ≥ 0.5 时采用解析结果，否则交给 AI 建议。

核心规则：

- 人物型目录保持人物一级目录；厂牌 / 机构 / 企划型目录保持厂牌一级目录；
- 不再无脑归入"写真合集"，也不给标题追加"写真 / 套图 / 合集 / 系列"；
- 保留原目录中的规格信息，如 `[46P208MB]`、`[43P4V234MB]`、`[86+1P]`。

示例：

```text
D:\图册\雪琪SAMA\雪琪SAMA JK白丝 [46P208MB]
=> NAS\雪琪SAMA\雪琪SAMA JK白丝 [46P208MB]

D:\图册\[IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]
=> NAS\IMISS爱蜜社\[IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]
```

---

## R18 检测

- 数据结构：`content_tags`、`r18_label`、`r18_confidence`、`r18_reason`；
- 抽样策略：封面 + 前 / 中 / 后帧，默认每系列 7 张，不全量扫描；
- 后端：`heuristic`（默认，无额外依赖）或 `onnx`（NudeNet 分类器，需 `pip install -e .[nsfw]` 并下载模型）；
- 入口：工作流 `--r18-scan-limit`、CLI `pims scan-series-r18 <candidate_id>`、API `POST /review/series/{candidate_id}/scan-r18`；
- 结果：`r18_label=true` 时只在最终目录名末尾追加 ` [R18]`（原名已含 R18 则不重复），一级分类不变；审核页显示置信度与原因。

```powershell
python scripts\download_nsfw_model.py        # 下载模型到 data\models\
python scripts\compare_nsfw_backends.py      # heuristic 与 onnx 只读对照
# .env 中设置 PIMS_NSFW_BACKEND=onnx 启用
```

20 样本对照显示启发式后端在深色薄纱场景存在漏检，ONNX 后端显著更敏感；启用后建议先人工复核一段时间再调整阈值。

---

## 通知（企业微信）

配置 `PIMS_WECHAT_WEBHOOK_URL` 后，工作流在生成需要人工批准的隔离批次时推送文本消息。节流规则：

1. 同一批次只推一次（`notification_records` 唯一索引去重）；
2. 已处理批次（状态非 `planned`）不再推送；
3. 每小时最多 `PIMS_WECHAT_HOURLY_LIMIT` 条，超限标记 `throttled`，下轮工作流自动重试；
4. `PIMS_WECHAT_DIGEST=true` 时事件只入队，工作流结束后聚合为一条日报（每天最多一条）。

`pims notify-wechat` 发送的生命周期消息与上述预算共享。自动批准能处理的精确重复不会产生通知，人工提示会随着自动化程度提高而减少。

---

## 安全与恢复

- **变更前备份**：`pims backup-db --label <标签>`；
- **中断恢复**：

  ```powershell
  pims recover-tasks
  pims run-safe-workflow --keep-root "\\NAS\photos\归档"
  ```

- **系统性失败重排**：修复原因（例如调高 `PIMS_MAX_IMAGE_PIXELS`）后执行 `pims reset-failed-tasks --task-type hash_phash`；
- **NAS 操作四步走**：备份数据库 → dry-run → 分批执行 → 每批验证文件存在率。NAS 回收站虽可恢复，但不能作为常规机制依赖。

---

## 测试

```powershell
python -m pytest -q
```

约 290 个用例，覆盖服务层、CLI、API 路由、目录名解析回归（含 `紧急企划`、`雪琪SAMA`、`IMISS爱蜜社` 等样本）、通知节流、NSFW 后端、审核页静态资源等。`tests/test_app.py`、`tests/test_db.py`、`tests/test_review_routes.py` 中少数用例依赖 `./data/pims.db` 存在，首次克隆后可先启动一次 API 或运行任一写库命令生成。

---

## 辅助脚本

| 脚本 | 用途 |
| --- | --- |
| `scripts/run_full_detection.ps1` | 后台循环运行安全工作流（见上文） |
| `scripts/download_nsfw_model.py` | 下载 NudeNet ONNX 模型 |
| `scripts/compare_nsfw_backends.py` | 对同一批样本对比 heuristic / onnx 判定结果（只读） |
| `scripts/delegated_approval_worker.py` | 委托审批循环 worker |
| `scripts/nas_ad_file_cleanup.py` | 清理 NAS 目录中的广告 / 水印等垃圾文件（一次性） |
| `scripts/nas_collection_tier_cleanup.py` | 合集分层整理（一次性） |
| `scripts/nas_collection_closeout.py` | 合集收尾整理（一次性，含测试） |
| `scripts/nas_recursive_boutique_regroup.py` | 递归精品重分组（一次性） |
| `scripts/nas_final_cleanup.py` | 最终清理（一次性） |

一次性脚本均针对特定阶段的 NAS 目录状态编写，运行前请阅读脚本头部说明并先以 dry-run 方式验证。

---

## 当前范围与限制

**已实现**：索引、MD5 精确重复、pHash 相似、系列候选与规则命名、DeepSeek 辅助建议、人工审核、确认后归档到 NAS、缩略图、审核 API 与页面、操作批次规划 / 确认 / 执行、精确重复自动处理（带保留副本守卫）、可恢复哈希任务、失败任务重排、企业微信节流通知、SQLite 备份。

**未实现 / 已知限制**：

- 多用户鉴权与角色权限；
- 打包安装器 / Windows 服务；
- 非 SQLite 数据库的迁移方案（Alembic 仅列入依赖）；
- 云端 SafeSearch / Moderation 复核与视频抽帧（依赖 ffmpeg）；
- 目录名解析器对厂牌子系列名、《书名号》粘连、裸厂牌名、韩日文人名括注等模式仍可能误判（详见解析器测试文件头部注释）。

更多细节、阶段计划与接手提示词见 [docs/PROJECT_STATUS_AND_ROADMAP.md](docs/PROJECT_STATUS_AND_ROADMAP.md)。
