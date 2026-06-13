# PIMS 项目状态与路线图

更新时间：2026-06-13

本文档用于新对话或新开发者快速接手 PIMS 照片整理项目。不要在本文档写入 API key、Webhook URL、NAS 账号密码等敏感信息。

## 项目目标

PIMS 是一个运行在 Windows 电脑上的个人照片/视频整理系统，以 NAS 作为最终清晰归档位置。

核心目标：

- 整理约 10T 的本地和 NAS 图册。
- 支持长时间运行、中断恢复、分批处理。
- 先检测和审核，再执行移动或隔离。
- 最终只保留 NAS 上结构清晰的归档文件。
- 删除/隔离前必须支持批量审核确认。

当前主要数据源：

- 本地：`D:\图册`
- 本地：`E:\图册整理`
- NAS：`\\192.168.31.10\personal_folder\网络写真集`

当前审核入口：

- 局域网：`http://192.168.31.98:8000/review-ui`

## 当前运行状态

最近一次检查结果：

- API 正在运行：`uvicorn pims_v1.main:app --host 0.0.0.0 --port 8000`
- 后台整理任务建议运行：`scripts\run_full_detection.ps1 -ExecuteConfirmedBatches -AiSuggestLimit 50 -R18ScanLimit 50 -AutoArchiveLimit 20`
- 数据库：`sqlite:///./data/pims.db`
- NAS 归档根目录：`\\192.168.31.10\personal_folder\网络写真集`
- DeepSeek API key：已配置
- DeepSeek 模型：`deepseek-v4-pro`
- DeepSeek 推理强度：`high`
- Enterprise WeChat 推送：当前关闭，避免重复推送骚扰

最近一次进度快照：

- 媒体文件总数：`550745`
- MD5 已完成：`136215 / 550745`，约 `24.73%`
- pHash 已完成：`10837 / 548311`，约 `1.98%`
- 待审核项目：`8223`
- 已执行操作：`1002`
- 批次：已执行 `3`，待计划 `2`

## 已实现功能

### 1. 文件索引

已支持：

- 本地目录和 NAS 目录索引。
- 记录文件路径、文件名、扩展名、大小、mtime、媒体类型、宽高、时长等基础信息。
- SQLite 持久化。
- 大批量任务可分批继续运行。

相关模块：

- `src/pims_v1/repos/asset_repo.py`
- `src/pims_v1/cli.py`

### 2. 精确重复检测

已支持：

- MD5 hash 计算。
- 精确重复分组。
- 自动规划重复副本隔离操作。
- 隔离前进入审核批次，不直接删除。

相关模块：

- `src/pims_v1/services/hash_index_service.py`
- `src/pims_v1/services/duplicate_index_service.py`
- `src/pims_v1/services/operation_plan_service.py`

### 3. 相似图片检测

已支持：

- 图片 pHash 计算。
- 相似图片分组。
- 非图片跳过。

相关模块：

- `src/pims_v1/services/phash_index_service.py`
- `src/pims_v1/services/similar_index_service.py`

### 4. 缩略图和媒体预览

已支持：

- 图片缩略图缓存。
- 审核页图片预览。
- 审核页视频内联预览和弹窗播放。

相关模块：

- `src/pims_v1/services/thumbnail_service.py`
- `src/pims_v1/main.py`
- `src/pims_v1/api/review_ui.py`

### 5. 审核页

审核页已拆成三个功能区：

- 总览进度：查看全量检测进度、任务队列和日志。
- AI 系列整理：审核 AI 分类/命名/目标路径/标签建议。
- 系列审核卡片展示规则建议，便于对比规则路径和 AI 建议。
- 重复隔离审核：对比“已存在位置”和“重复位置”，再确认批次。

已支持：

- 中文说明。
- 清新色彩 UI。
- 移动端适配基础优化。
- 批量选择、批量生成 AI 建议、批量确认移动。
- 系列建议筛选：全部、待 AI、待确认、R18、低置信度、目标冲突。
- 规则建议展示：`archive_category`、`archive_title`、解析 metadata。
- 操作 loading 态。
- WebSocket 自动刷新进度。
- 图片/视频预览。

相关模块：

- `src/pims_v1/api/review_ui.py`
- `src/pims_v1/api/review.py`
- `src/pims_v1/services/review_service.py`

### 6. AI 系列整理审核

已支持：

- DeepSeek 文本模型生成可审核建议。
- 当前默认模型：`deepseek-v4-pro`
- thinking/high reasoning 已开启。
- AI 建议包含标题、一级分类、目标路径、计划说明、风险提示、内容标签。
- `run-safe-workflow` 已支持 `--ai-suggest-limit` 批量生成 AI 建议。
- `scripts\run_full_detection.ps1` 默认 `-AiSuggestLimit 50`、`-R18ScanLimit 50`、`-AutoArchiveLimit 20`，后台长跑时会自动为新系列候选生成建议、抽样筛查 R18，并自动归档低风险规则/AI 一致项。
- 自动归档阶段会复用已有 `pending_review` AI 建议，避免同一候选在 `ai_suggest` 后重复调用模型；自动移动成功后同步将建议标记为 `confirmed`。
- AI 建议必须审核确认后才移动文件。
- 已确认系列默认不再显示在待审核列表。

重要规则：

- AI 不再决定物理归档层级。
- 物理路径优先由确定性规则生成。
- AI 只提供辅助字段、风险提示、标签和低风险命名建议。

### 7. 归档结构规则

已确认的核心规则：

- 人物型目录保持人物一级目录。
- 厂牌/机构/企划型目录保持厂牌一级目录。
- 不再无脑归入 `写真合集`。
- 不再无脑给标题追加“写真/套图/合集/系列”。
- 保留原目录中的规格信息，例如 `[46P208MB]`、`[43P4V234MB]`、`[86+1P]`。

示例：

```text
D:\图册\雪琪SAMA\雪琪SAMA JK白丝 [46P208MB]
=> NAS\雪琪SAMA\雪琪SAMA JK白丝 [46P208MB]
```

```text
D:\图册\紧急企划\【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】
=> NAS\紧急企划\【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】
```

```text
D:\图册\[IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]
=> NAS\IMISS爱蜜社\[IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]
```

### 8. R18 内容标签

已支持数据结构和审核流：

- `content_tags`
- `r18_label`
- `r18_confidence`
- `r18_reason`
- 本地启发式视觉抽样筛查。
- 手动 API：`POST /review/series/{candidate_id}/scan-r18`
- CLI：`pims scan-series-r18 <candidate_id>`
- 工作流参数：`--r18-scan-limit`
- `scripts\run_full_detection.ps1` 默认 `-R18ScanLimit 50`，后台长跑时会自动抽样筛查。

规则：

- R18 不改变一级归档结构。
- R18 不参与移动目标分类。
- 如果确认或 AI 建议 `r18_label=true`，只在最终目录名末尾追加 `[R18]`。
- 如果原目录已有 `R18`，不重复追加。
- 审核页显示 R18 置信度和原因。

示例：

```text
NAS\紧急企划\【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】 [R18]
```

当前限制：

- DeepSeek 当前文本 API 不可靠识别图片内容。
- 当前本地视觉筛查是粗筛启发式，不等同于生产级 NSFW 模型。
- 云端复核和视频抽帧尚未接入。

### 9. 通知

已支持 Enterprise WeChat Webhook 通知：

- 有新批量审核任务时可推送。
- 已做通知去重记录。

当前状态：

- 企微推送已关闭，原因是之前批次重复推送造成干扰。
- 后续应在确认通知节流策略后再开启。

### 10. 安全与恢复

已支持：

- SQLite 备份命令。
- 中断任务恢复。
- 批次确认和执行分离。
- 重复文件进入隔离区，不永久删除。
- AI 系列移动必须人工确认。

重要历史事件：

- 早期 AI 曾把 `雪琪SAMA` 系列错误建议到 `写真合集`。
- 已修正规则：保留人物/厂牌/企划一级目录。
- 已修复并恢复已确认的 `雪琪SAMA` 系列目录和数据库路径。
- 相关数据库备份：`data/pims.before-ai-recalc-20260613-111542.db`

## 已知问题和风险

### 1. 视觉内容识别仍需增强

R18 标签字段、审核展示、本地启发式抽样筛查和自动归档阻断已实现，但还不是完整的生产级 NSFW 识别链路。

建议方案：

- 本地 NSFW 模型替换当前启发式粗筛。
- 云端 SafeSearch/Moderation API 只复核疑似项。
- 视频抽帧纳入同一套抽样审核。
- 审核页人工确认最终标签。

### 2. 审核页代码偏重

`src/pims_v1/api/review_ui.py` 仍是单文件 HTML/CSS/JS 字符串。

短期可接受，但后续建议拆分：

- 静态 CSS
- 静态 JS
- API schema
- 页面组件分区

### 3. SQLite 可用但不是长期最优

当前 SQLite 适合单机单用户。

后续如果要更稳定运行 10T 长任务，建议：

- 引入 Alembic 迁移。
- 评估 PostgreSQL。
- 将任务队列从数据库表扩展为更明确的 worker 状态机。

### 4. 企微通知默认关闭

需要重新设计通知节流：

- 同一批次只推一次。
- 已处理批次不再提醒。
- 每小时最多 N 次。
- 通知内容要包含审核入口和任务类型。

### 5. NAS 操作必须继续谨慎

已经证明 NAS 回收站可恢复删除目录，但不能依赖它作为正常机制。

后续涉及真实移动/删除前必须：

- 备份数据库。
- 先 dry-run。
- 分批执行。
- 每批验证文件存在率。

## 下一阶段计划

### 阶段 1：把“规则归档”正式产品化

目标：

- 不再依赖 AI 决定路径。
- 将人物型、厂牌型、机构型、企划型目录规则固化。
- AI 只对少数无法判断项给建议。

任务：

- 新增目录名解析器。
- 解析人物名、厂牌名、编号、主题、规格信息。
- 输出 `archive_category`、`archive_title`、`metadata`、`confidence`。
- 在审核页展示“规则建议”和“AI 建议”的差异。当前已展示规则建议，后续可加强差异高亮。
- 对 `紧急企划`、`雪琪SAMA`、`IMISS爱蜜社` 写回归测试。

### 阶段 2：R18 视觉识别

推荐架构：

- 每个文件夹抽样，不全量每张都调用云端。
- 图片取封面、前中后若干张。
- 视频抽关键帧。
- 本地 NSFW 模型粗筛。
- 中间置信度再调用云端复核。
- 审核页人工确认是否追加 `[R18]`。

推荐模型路线：

- 本地粗筛：NudeNet 或类似 ONNX NSFW detector。
- 云端复核：Google Vision SafeSearch 或 AWS Rekognition moderation。
- 大模型只用于少量疑难样本解释，不做全量扫描。

### 阶段 3：审核页可维护性改造

目标：

- 降低 `review_ui.py` 复杂度。
- 页面逻辑按功能模块拆分。
- 增加更清晰的批量筛选和回滚入口。

任务：

- 拆分静态文件。
- 系列建议筛选已接入，后续重点转为拆分 `review_ui.py` 静态资源和组件。
- 增加隔离区管理页。
- 增加操作回滚页。

### 阶段 4：生产运行强化

目标：

- 让 10T 长任务更稳定、可观测、可恢复。

任务：

- 数据库迁移机制。
- 任务分阶段进度更精细。
- 日志持久化和错误归档。
- 大批量 NAS 操作限速和重试。
- 批次级 dry-run 报告。
- 失败任务自动恢复和告警。

### 阶段 5：通知恢复

目标：

- 恢复企微推送，但不重复骚扰。

任务：

- 重新启用 Webhook 前先加通知节流。
- 通知内容按任务类型分类。
- 同一批次只推一次。
- 已处理批次永不重复推。
- 支持每日汇总。

## 新对话接手提示词

新开对话时可直接提供下面内容：

```text
你正在接手 PIMS 项目，路径是 C:\Users\Administrator\Desktop\Codex\pims-v1。
先阅读 docs/PROJECT_STATUS_AND_ROADMAP.md 和 README.md。
当前项目是 Windows PC 运行、NAS 归档的照片/视频整理系统。
重点原则：
1. 不要让 AI 决定物理归档层级。
2. 人物、厂牌、机构、企划目录结构优先由规则生成。
3. 保留原文件夹名里的 P/V/大小/VOL/EX/人物/主题信息。
4. R18 只作为叶子目录标签，不改变移动分类。
5. 删除/隔离/移动前必须备份数据库、dry-run、人工审核。
6. 不要输出或提交 API key、Webhook 等敏感信息。
继续开发前先运行 git status 和相关测试。
```

## 常用命令

查看状态：

```powershell
git status -sb
pims status
Invoke-RestMethod http://127.0.0.1:8000/progress/summary
```

运行测试：

```powershell
python -m pytest -q
```

启动 API：

```powershell
uvicorn pims_v1.main:app --host 0.0.0.0 --port 8000
```

恢复任务：

```powershell
pims recover-tasks
```

运行安全工作流：

```powershell
pims run-safe-workflow --keep-root "\\192.168.31.10\personal_folder\网络写真集" --md5-limit 20000 --phash-limit 5000 --thumbnail-limit 2000 --min-series-assets 2 --ai-suggest-limit 50 --r18-scan-limit 50
```

备份数据库：

```powershell
pims backup-db --label before-risky-change
```
