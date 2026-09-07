# NAS Recursive Boutique Regroup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move remaining priority-series directories buried inside `其它画册` into `精品/<系列>/`, preserving source bucket context such as `ALPHA`, `R15`, `内部`, and `D图册`.

**Architecture:** Use a dedicated recursive regroup script that scans only `其它画册`, selects the highest matching priority directory in each branch, writes a dry-run CSV, moves directories with unique-name conflict handling, and updates all known PIMS path columns by prefix.

**Tech Stack:** Python standard library, SQLite, Windows UNC filesystem paths, CSV audit reports.

---

### Task 1: Build Recursive Regroup Tool

**Files:**
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\scripts\nas_recursive_boutique_regroup.py`

- [x] **Step 1: Scan `其它画册` recursively**

Find directories whose basename matches the priority-series classifier.

- [x] **Step 2: Select highest matching ancestors**

If both a parent and child match the same priority logic, move the parent and suppress descendants.

- [x] **Step 3: Preserve source bucket**

Move `其它画册\ALPHA\NO.336 森萝财团...` to `精品\森萝财团\ALPHA\NO.336 森萝财团...`.

### Task 2: Execute Safely

**Files:**
- Modify: `\\192.168.31.10\personal_folder\网络写真集`
- Modify: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-recursive-boutique-regroup-*.csv`

- [x] **Step 1: Back up database**

Run:

```powershell
python -m pims_v1.cli backup-db --label before-nas-recursive-boutique-regroup
```

- [x] **Step 2: Dry-run**

Run:

```powershell
python scripts\nas_recursive_boutique_regroup.py --dry-run
```

- [x] **Step 3: Execute**

Run:

```powershell
python scripts\nas_recursive_boutique_regroup.py --execute
```

- [x] **Step 4: Verify**

Expected: recursive priority keyword hits in `其它画册` drop sharply, confirmed archive paths remain present, and final reports show no filesystem errors.
