# NAS Directory Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the NAS photo archive root easier to browse by moving obvious one-off top-level set folders under their existing producer/person parent folders.

**Architecture:** Use a conservative, report-first filesystem operation. Back up SQLite first, generate a deterministic move plan from the current NAS root and database root path, execute only no-conflict directory moves, then update `series.archive_path` rows whose paths were moved.

**Tech Stack:** PowerShell, Python standard library, SQLite, Windows UNC paths.

---

### Task 1: Backup and Plan

**Files:**
- Read: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-root-cleanup-plan-<timestamp>.csv`

- [x] **Step 1: Back up the database**

Run:

```powershell
python -m pims_v1.cli backup-db --label before-nas-directory-cleanup
```

Expected: `status=created`.

- [x] **Step 2: Generate a conservative move plan**

Only include top-level directories matching an existing top-level parent by prefix, such as `爆机少女喵小吉 - ...` under `爆机少女喵小吉`, `[BLUECAKE] ...` under `[BLUECAKE]`, `ATFMAKER Vol ...` under `ATFMAKER`, and `Pure Media Vol...` under `Pure Media`.

- [x] **Step 3: Reject conflicts**

Skip any move when the destination already exists.

### Task 2: Execute Moves

**Files:**
- Modify: NAS archive directories under `\\192.168.31.10\personal_folder\网络写真集`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-root-cleanup-result-<timestamp>.csv`

- [x] **Step 1: Move only planned no-conflict directories**

Use `os.replace` or `shutil.move` for directory moves.

- [x] **Step 2: Record every move**

Each result row must include source, destination, action, and error.

### Task 3: Sync Database

**Files:**
- Modify: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-root-cleanup-db-updates-<timestamp>.csv`

- [x] **Step 1: Update moved `series.archive_path` prefixes**

For each successful directory move, update `series.archive_path` if it equals the old directory or starts with the old directory plus a separator.

- [x] **Step 2: Leave failed rows untouched**

Do not fabricate paths for missing failed series.

### Task 4: Verify

**Files:**
- Read: NAS archive root
- Read: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`

- [x] **Step 1: Verify root directory count and root files**

Expected: root file count remains `0`, top-level directory count decreases.

- [x] **Step 2: Verify database archive paths**

Expected: no new missing confirmed paths; moved paths exist.

- [x] **Step 3: Summarize remaining manual cleanup**

Report source/status buckets such as `_源目录补迁移`, `图册整理`, and `【原档】` without moving them automatically.
