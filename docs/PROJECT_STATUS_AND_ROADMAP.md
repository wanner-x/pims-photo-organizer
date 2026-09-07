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
- 后台整理任务建议运行：`scripts\run_full_detection.ps1 -ExecuteConfirmedBatches -AiSuggestLimit 50 -R18ScanLimit 50 -AutoArchiveLimit 20 -SeriesLimit 0 -SimilarLimit 0`
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
- `scripts\run_full_detection.ps1` 默认 `-AiSuggestLimit 50`、`-R18ScanLimit 50`、`-AutoArchiveLimit 20`、`-SeriesLimit 0`、`-SimilarLimit 0`，后台长跑时优先完成可恢复哈希、重复分组、R18 抽样和已有候选的低风险自动归档；系列重建和相似图聚类默认后置，避免每轮全量扫描阻塞长跑。
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
- [2026-07-17 更新] 本地粗筛已支持 NudeNet ONNX 后端：`PIMS_NSFW_BACKEND=onnx` 显式启用（默认仍 heuristic，行为不变）。模型 `data/models/nudenet_classifier_model.onnx`（79.7MB），下载脚本 `scripts/download_nsfw_model.py`，对照脚本 `scripts/compare_nsfw_backends.py`。20 样本对照显示 heuristic 在深色薄纱场景漏检、onnx 显著更敏感，启用后建议先人工复核一段时间再调阈值。
- 云端复核和视频抽帧尚未接入。

### 9. 通知

已支持 Enterprise WeChat Webhook 通知：

- 有新批量审核任务时可推送。
- 已做通知去重记录。

当前状态：

- 企微推送保持关闭（.env 未配置 webhook）。
- [2026-07-17 更新] 节流已实现，重新开启只差配置 webhook：同批次只推一次、已处理批次（status != planned）不再推、每小时最多 `PIMS_WECHAT_HOURLY_LIMIT` 次（默认 3，超限标记 throttled 下轮自动重试）、`PIMS_WECHAT_DIGEST=1` 时聚合为每日一条日报（`run_safe_workflow` 末尾触发）。新表 `notification_digest_entries`。

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

R18 标签字段、审核展示、本地抽样筛查和自动归档阻断已实现，但还不是完整的生产级 NSFW 识别链路。

进展与剩余：

- [已完成] 本地 NSFW 模型粗筛（NudeNet ONNX 后端，`services/nsfw_detector.py` 统一接口，默认 heuristic 可切换）。
- [未做] 云端 SafeSearch/Moderation API 只复核疑似项。
- [未做] 视频抽帧纳入同一套抽样审核（依赖 ffmpeg）。
- 审核页人工确认最终标签（流程已支持）。

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

[2026-07-17 已解决] 通知节流四条规则全部实现（见"9. 通知"），`notification_records.status` 生命周期扩展为 `sending→sent|failed|throttled|digest_pending→digested`。重新开启仅需配置 `PIMS_WECHAT_WEBHOOK_URL`。

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

- [已完成 2026-07-17] 目录名解析器 `services/dirname_parser.py`：person/studio/project/unknown 四类，五级模式优先级，解析人物/厂牌/编号/日期/主题/规格（P/V/MB 数值化）/R18，输出 `category_type`、`archive_category`、`archive_title`、`metadata`、`confidence`。
- [已完成] 接入 `archive_rule_planner`：父目录非通用且置信度 >= 0.5 时采用解析结果，低于阈值维持原逻辑（留给 AI）。对外字段结构不变。
- [已完成] 46 个新增测试（含 `紧急企划`、`雪琪SAMA`、`IMISS爱蜜社` 回归），全量 270 个测试通过。真实库抽样 200 条：studio 106 / person 71 / unknown 13 / project 10，平均置信度 0.756，94% 过阈值。
- [遗留] 已知不能处理的模式见解析器测试文件头部注释：厂牌子系列名（丝享家/普惠集）误判人物、《书名号》粘连、无关键词后缀的裸厂牌名、韩日文人名括注、裸规格尾缀混入主题。
- [后续] 审核页加强"规则建议 vs AI 建议"差异高亮。

### 阶段 2：R18 视觉识别

推荐架构：

- 每个文件夹抽样，不全量每张都调用云端。（已实现，沿用封面/前中后抽样）
- [已完成 2026-07-17] 本地 NSFW 模型粗筛：NudeNet ONNX 分类器接入 `services/nsfw_detector.py` 统一接口，`PIMS_NSFW_BACKEND=onnx` 启用，手动 API / CLI / 工作流三条链路全部生效；onnxruntime 1.27（Python 3.14 有轮子），依赖组 `pip install -e .[nsfw]`。
- [未做] 视频抽关键帧（依赖 ffmpeg）。
- [未做] 中间置信度再调用云端复核。
- 审核页人工确认是否追加 `[R18]`（流程已支持）。

云端复核候选（未接入）：Google Vision SafeSearch 或 AWS Rekognition moderation；大模型只用于少量疑难样本解释，不做全量扫描。

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

[2026-07-17 全部完成] 节流四规则已实现并有 26 个新增测试背书：

- 同一批次只推一次（notification_records 唯一索引去重）。
- 已处理批次（status != planned）永不重复推。
- 每小时最多 `PIMS_WECHAT_HOURLY_LIMIT` 次（默认 3，0 关闭；超限标记 throttled，下轮工作流自动重试不丢失）。
- 每日汇总：`PIMS_WECHAT_DIGEST=1` 时事件只入队，`run_safe_workflow` 末尾聚合为一条日报（每天最多一条）；CLI `notify-wechat` 生命周期消息共享同一小时预算。

恢复推送步骤：确认 `.env` 配置 `PIMS_WECHAT_WEBHOOK_URL`（可同时设 `PIMS_WECHAT_DIGEST=1` 起步），无需代码改动。

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

NSFW 模型（可选，onnx 后端）：

```powershell
python scripts\download_nsfw_model.py          # 下载 NudeNet ONNX 模型到 data\models\
python scripts\compare_nsfw_backends.py        # heuristic vs onnx 只读对照抽样
# .env 设 PIMS_NSFW_BACKEND=onnx 启用（默认 heuristic）
```
