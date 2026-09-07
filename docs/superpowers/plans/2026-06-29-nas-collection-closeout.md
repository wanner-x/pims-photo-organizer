# NAS Collection Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the NAS photo collection closeout so boutique series, multi-set series, singleton albums, and junk residual files are consistently placed and verifiable.

**Architecture:** Use report-first cleanup: generate CSV inventories and move plans, review uncertain matches before execution, then execute only confirmed deterministic moves. Every move must update PIMS database paths and be followed by a filesystem and database verification pass.

**Tech Stack:** Python standard library, SQLite, Windows UNC filesystem paths, CSV audit reports, existing PIMS CLI backup tooling.

---

### Task 1: Freeze Current Baseline

**Files:**
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-closeout-baseline-YYYYMMDD-HHMMSS.csv`
- Read: `\\192.168.31.10\personal_folder\网络写真集`
- Read: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`

- [ ] **Step 1: Back up database**

Run:

```powershell
python -m pims_v1.cli backup-db --label before-nas-collection-closeout
```

Expected:

```text
status=created
path=data\backups\before-nas-collection-closeout-pims.db
```

- [ ] **Step 2: Export directory baseline**

Generate a CSV with these columns:

```text
Path,RelativePath,Depth,Parent,Name,ChildDirectoryCount,FileCount,TotalBytes
```

Rules:
- Include every directory under `\\192.168.31.10\personal_folder\网络写真集`.
- Do not move files in this task.
- Mark current top-level bucket as `精品`, `其它画册`, or `root`.

- [ ] **Step 3: Export PIMS series baseline**

Generate a CSV with these columns:

```text
SeriesId,Title,Status,ArchivePath,Exists,TopBucket
```

Expected:
- `confirmed` series with `Exists=False` must be `0`.
- Any missing confirmed path blocks execution until investigated.

---

### Task 2: Lock Canonical Series Rules

**Files:**
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-closeout-series-rules-YYYYMMDD-HHMMSS.csv`

- [ ] **Step 1: Define boutique canonical folders**

Use these exact boutique targets under `精品`:

```text
精品\森萝财团
精品\紧急企划
精品\少女秩序
精品\橙子喵
精品\村上西瓜
精品\素人渔夫
精品\流欲xx工坊
精品\萌量守恒
精品\稚乖画册
精品\金鱼kinngyo（花音栗子）
```

- [ ] **Step 2: Define priority alias matching**

Use exact and conservative substring aliases:

```text
森萝财团: 森萝财团, 森萝, X-077
紧急企划: 紧急企划
少女秩序: 少女秩序
橙子喵: 橙子喵
村上西瓜: 村上西瓜
素人渔夫: 素人渔夫
流欲xx工坊: 流欲xx工坊, 流欲, xx工坊
萌量守恒: 萌量守恒
稚乖画册: 稚乖
金鱼kinngyo（花音栗子）: 金鱼, kinngyo, 花音栗子
```

- [ ] **Step 3: Define non-boutique high-volume grouping**

Treat high-volume non-boutique creators as ordinary series folders under `其它画册`, unless user later promotes them to `精品`.

Initial explicit target:

```text
其它画册\爆机少女喵小吉
```

Aliases:

```text
爆机少女喵小吉: 爆机少女喵小吉, 喵小吉
```

---

### Task 3: Generate Deterministic Move Plan

**Files:**
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-closeout-move-plan-YYYYMMDD-HHMMSS.csv`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-closeout-uncertain-YYYYMMDD-HHMMSS.csv`

- [ ] **Step 1: Scan boutique aliases**

For each directory name and relative path:
- If it matches a boutique canonical rule exactly or by approved alias, plan a move under that boutique folder.
- If it is already under the correct boutique folder, mark `Action=keep`.
- If it is under another boutique folder, mark `Action=review_conflict`.

Move plan columns:

```text
SourcePath,TargetPath,Rule,Alias,Action,Reason
```

- [ ] **Step 2: Scan high-volume ordinary series**

For explicit ordinary series like `爆机少女喵小吉`:
- Move all matching albums into `其它画册\爆机少女喵小吉`.
- If any matching album is currently under `精品` because it is nested below a boutique creator, mark it `review_conflict` instead of moving.

- [ ] **Step 3: Discover additional multi-set candidates**

Group remaining directories by normalized creator/title prefix.

Normalization rules:
- Remove bracketed issue markers such as `[01]`, `Vol.01`, `第01期`, `NO.001`.
- Keep creator names before common separators: space, `-`, `_`, `+`, `写真`, `画册`.
- Do not merge names shorter than 2 Chinese characters unless already in rule table.

Candidate rule:
- Prefix group count `>= 2` becomes a proposed ordinary series folder under `其它画册`.
- Prefix group count `= 1` stays in `其它画册`.

- [ ] **Step 4: Split deterministic and uncertain**

Deterministic move criteria:
- Unique target.
- Source is not an ancestor of target.
- Target path does not already contain a different album with the same name.
- Rule source is explicit boutique alias, explicit ordinary alias, or discovered prefix group with count `>= 3`.

Uncertain criteria:
- Prefix group count is exactly `2`.
- Alias overlaps multiple canonical targets.
- Directory name contains generic words only, such as `写真`, `合集`, `套图`, `画册`, `图片`.
- Destination collision exists.

---

### Task 4: Review Before Execution

**Files:**
- Read: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-closeout-move-plan-YYYYMMDD-HHMMSS.csv`
- Read: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-closeout-uncertain-YYYYMMDD-HHMMSS.csv`

- [ ] **Step 1: Summarize deterministic moves**

Report:

```text
Boutique moves by target
Ordinary series moves by target
Already-correct keep count
Collision count
Conflict count
```

- [ ] **Step 2: Ask user only about uncertain groups**

Report no more than 30 uncertain groups per batch, sorted by group count descending.

For each group show:

```text
ProposedTarget,Count,ExampleSources,Reason
```

User choices:

```text
approve
skip
promote_to_精品
rename_target
```

---

### Task 5: Execute Confirmed Moves

**Files:**
- Modify: `\\192.168.31.10\personal_folder\网络写真集`
- Modify: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-closeout-move-result-YYYYMMDD-HHMMSS.csv`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-closeout-db-updates-YYYYMMDD-HHMMSS.csv`

- [ ] **Step 1: Execute only confirmed rows**

Execute rows where:

```text
Action=move
ReviewStatus=approved
```

or deterministic rows with:

```text
Action=move
ReviewStatus=not_required
```

- [ ] **Step 2: Avoid overwrites**

If target exists:
- If source and target are the same directory, mark `kept`.
- If target has different content, mark `collision` and do not move.
- If target is empty, move into target and mark `moved`.

- [ ] **Step 3: Update PIMS paths**

For every successful move:
- Update `series.archive_path` when it equals or is under the old source path.
- Update `assets.current_path` and `assets.original_path` when they equal or are under the old source path.
- Write every changed row to DB update CSV.

---

### Task 6: Clean Empty Directories and Junk Files

**Files:**
- Modify: `\\192.168.31.10\personal_folder\网络写真集`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-closeout-empty-dirs-YYYYMMDD-HHMMSS.csv`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-closeout-junk-files-YYYYMMDD-HHMMSS.csv`

- [ ] **Step 1: Report empty directories**

After moves, report empty directories only.

Do not delete non-empty directories.

- [ ] **Step 2: Delete only confirmed junk names**

Allowed exact junk names:

```text
永久地址 - 发布页.txt
机器猫次元 - 整理发布.txt
机器猫次元.url
```

Other ad-like `.txt` and `.url` files go to uncertain report for user confirmation.

---

### Task 7: Final Verification

**Files:**
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-closeout-final-summary-YYYYMMDD-HHMMSS.txt`

- [ ] **Step 1: Verify directory rules**

Expected:
- Boutique aliases outside their boutique folder: `0`.
- Explicit ordinary series aliases outside their ordinary folder: `0`, except reviewed conflicts.
- Confirmed series archive path missing: `0`.

- [ ] **Step 2: Verify singleton policy**

Expected:
- Direct children under `其它画册` that are single standalone albums remain allowed.
- Groups with `>= 2` albums are either in a series folder or listed in uncertain report.

- [ ] **Step 3: Verify junk file cleanup**

Expected:
- Exact junk file remaining count: `0`.
- Uncertain junk candidate report exists, even if count is `0`.

- [ ] **Step 4: Produce final summary**

Final summary must include:

```text
Moved directories count
Kept directories count
Collision count
Uncertain groups count
DB updated rows count
Confirmed series missing count
Exact junk remaining count
Report file paths
```
