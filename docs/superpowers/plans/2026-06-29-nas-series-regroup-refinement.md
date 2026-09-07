# NAS Series Regroup Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the NAS `精品` and `其它画册` structure by adding `金鱼kinngyo（花音栗子）` to `精品` and grouping scattered same-series albums under their existing series folders.

**Architecture:** Extend the existing one-shot cleanup script with priority aliases and second-level `其它画册` regrouping. The script writes a dry-run CSV, executes no-overwrite moves, merges only non-conflicting child folders into existing destinations, and updates SQLite path prefixes for moved content.

**Tech Stack:** Python standard library, SQLite, Windows UNC filesystem paths, CSV audit reports.

---

### Task 1: Inspect Current Structure

**Files:**
- Read: `\\192.168.31.10\personal_folder\网络写真集\精品`
- Read: `\\192.168.31.10\personal_folder\网络写真集\其它画册`
- Read: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`

- [x] **Step 1: Check `精品` contents**

Expected: existing priority folders are listed and `金鱼kinngyo（花音栗子）` is missing.

- [x] **Step 2: Check scattered same-series folders**

Expected: `爆机少女喵小吉` has scattered root-level albums under `其它画册`.

### Task 2: Update Cleanup Rules

**Files:**
- Modify: `C:\Users\Administrator\Desktop\Codex\pims-v1\scripts\nas_collection_tier_cleanup.py`

- [x] **Step 1: Add priority aliases**

Add `金鱼kinngyo（花音栗子）` to priority series and match common variants such as `金鱼kinngyo (花音栗子)`, `金鱼kinngyo`, and `花音栗子`.

- [x] **Step 2: Add second-level regrouping**

Inside `其它画册`, move directories whose names match an existing series prefix under that series folder.

- [x] **Step 3: Add non-overwrite merge**

When the target album folder already exists, move only source child folders whose target child path does not exist.

### Task 3: Execute and Verify

**Files:**
- Modify: `\\192.168.31.10\personal_folder\网络写真集`
- Modify: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-collection-tier-*.csv`

- [x] **Step 1: Back up database**

Run:

```powershell
python -m pims_v1.cli backup-db --label before-nas-series-regroup-refinement
```

- [x] **Step 2: Execute dry-run**

Run:

```powershell
python scripts\nas_collection_tier_cleanup.py --dry-run
```

- [x] **Step 3: Execute moves**

Run:

```powershell
python scripts\nas_collection_tier_cleanup.py --execute
```

- [x] **Step 4: Verify**

Expected: `金鱼kinngyo（花音栗子）` exists under `精品`; scattered `爆机少女喵小吉` directories are no longer at `其它画册` root; confirmed series paths exist.
