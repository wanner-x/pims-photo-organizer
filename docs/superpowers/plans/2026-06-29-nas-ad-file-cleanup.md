# NAS Ad File Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete explicitly identified junk ad files from the NAS archive and report similar uncertain files for manual confirmation.

**Architecture:** Add a dedicated cleanup script that scans the NAS root from SQLite, classifies exact known junk filenames separately from uncertain ad-like text/link files, writes CSV reports, deletes only exact known junk on `--execute`, and marks matching PIMS `assets` rows as `deleted`.

**Tech Stack:** Python standard library, SQLite, Windows UNC filesystem paths, CSV audit reports.

---

### Task 1: Build Cleanup Tool

**Files:**
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\scripts\nas_ad_file_cleanup.py`

- [x] **Step 1: Scan exact junk**

Match these exact names and conflict-renamed variants with numeric suffixes:

```text
永久地址 - 发布页.txt
机器猫次元 - 整理发布.txt
机器猫次元.url
```

- [x] **Step 2: Scan uncertain candidates**

Report small `.txt` and `.url` files with ad-like words such as `发布页`, `地址`, `防迷路`, `图小乐`, `官网`, and `永久`.

### Task 2: Execute Safely

**Files:**
- Modify: `\\192.168.31.10\personal_folder\网络写真集`
- Modify: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\pims.db`
- Create: `C:\Users\Administrator\Desktop\Codex\pims-v1\data\reports\nas-ad-file-cleanup-*.csv`

- [x] **Step 1: Back up database**

Run:

```powershell
python -m pims_v1.cli backup-db --label before-nas-ad-file-cleanup
```

- [x] **Step 2: Dry-run**

Run:

```powershell
python scripts\nas_ad_file_cleanup.py --dry-run
```

- [x] **Step 3: Execute exact deletion**

Run:

```powershell
python scripts\nas_ad_file_cleanup.py --execute
```

- [x] **Step 4: Verify**

Expected: exact junk count becomes zero, uncertain candidates remain reported, confirmed series archive paths still exist.
