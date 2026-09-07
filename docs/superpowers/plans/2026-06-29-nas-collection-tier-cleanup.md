# NAS Collection Tier Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the NAS archive root into `精品` for named priority series and `其它画册` for remaining albums, while keeping PIMS database paths consistent.

**Architecture:** Generate a dry-run CSV plan from the NAS root stored in SQLite, execute only no-conflict moves, then update all database path columns by old/new path prefixes. Priority series are moved under `精品/<系列>`; non-priority multi-set folders are moved under `其它画册/<系列>`; non-priority single-set wrappers are flattened into `其它画册/<套名>`.

**Tech Stack:** Python standard library, SQLite, Windows UNC filesystem paths, CSV audit reports.

---

### Task 1: Backup and Plan

**Files:**
- Read: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`
- Read/Write: `\\192.168.31.10\personal_folder\网络写真集`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-collection-tier-plan-<timestamp>.csv`

- [x] **Step 1: Back up the database**

Run:

```powershell
python -m pims_v1.cli backup-db --label before-nas-collection-tier-cleanup
```

Expected: `status=created`.

- [x] **Step 2: Generate a dry-run plan**

Run:

```powershell
python scripts/nas_collection_tier_cleanup.py --dry-run
```

Expected: a CSV plan with planned, skipped, and conflict rows.

### Task 2: Execute Moves

**Files:**
- Modify: `\\192.168.31.10\personal_folder\网络写真集`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-collection-tier-result-<timestamp>.csv`

- [x] **Step 1: Execute no-conflict moves**

Run:

```powershell
python scripts/nas_collection_tier_cleanup.py --execute
```

Expected: only rows with non-existing destinations are moved.

- [x] **Step 2: Remove empty single-set wrappers**

Expected: after flattening a single child directory, the old wrapper is removed only if it is empty.

### Task 3: Sync Database

**Files:**
- Modify: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-collection-tier-db-updates-<timestamp>.csv`

- [x] **Step 1: Update path prefixes**

Update path columns in `assets`, `series`, `series_suggestions`, `series_candidates`, `operations`, and archive tracking tables for every successful move.

- [x] **Step 2: Preserve failed and conflict paths**

Rows for skipped filesystem moves must not be changed.

### Task 4: Verify

**Files:**
- Read: `\\192.168.31.10\personal_folder\网络写真集`
- Read: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`

- [x] **Step 1: Verify target folders**

Expected: `精品` and `其它画册` exist; priority series are under `精品`.

- [x] **Step 2: Verify database consistency**

Expected: confirmed `series.archive_path` rows have no missing filesystem path.

- [x] **Step 3: Report skipped conflicts**

Summarize skipped rows so they can be reviewed later without guessing what happened.
