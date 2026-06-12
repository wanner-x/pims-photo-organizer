# PIMS V1

PIMS V1 is a PC-hosted, NAS-centered photo organization system for large personal libraries.

## Local Run

1. Create a Python 3.11 virtual environment.
2. Install the package with `pip install -e .[dev]`.
3. Mount or map NAS libraries before starting the app.
4. Start the API with `uvicorn pims_v1.main:app --reload`.
5. Run tests with `python -m pytest -v`.

## Production-Safe Runbook

This project is designed for a single-user, PC-hosted workflow with the NAS as the final archive. Do not expose the API to the public network.

### Required Environment

Copy `.env.example` to `.env` and set:

```powershell
PIMS_DATABASE_URL=sqlite:///./data/pims.db
PIMS_CACHE_ROOT=./data/.cache
PIMS_QUARANTINE_ROOT=./data/.quarantine
PIMS_API_TOKEN=<long-random-token>
PIMS_DEEPSEEK_API_KEY=<optional>
PIMS_WECHAT_WEBHOOK_URL=<optional enterprise wechat bot webhook>
```

Run the API bound to localhost unless you have a reverse proxy with authentication:

```powershell
uvicorn pims_v1.main:app --host 127.0.0.1 --port 8000
```

Mutating operation APIs require `x-pims-api-token` when `PIMS_API_TOKEN` is set.

### Backup Before Mutating Steps

Back up the SQLite database before confirming or executing operation batches:

```powershell
pims backup-db --label before-execute
```

### Safe Index And Review Workflow

Index libraries first:

```powershell
pims index-library "D:\图册" --name "PC Photos" --kind local
pims index-library "\\192.168.31.10\personal_folder\网络写真集" --name "NAS Photos" --kind nas
```

Build review data without moving or deleting files:

```powershell
pims run-safe-workflow --keep-root "\\192.168.31.10\personal_folder\网络写真集" --md5-limit 1000 --phash-limit 1000 --thumbnail-limit 1000
```

Review planned batches:

```powershell
pims list-batches
pims list-tasks
pims status
```

Open the local review page:

```powershell
uvicorn pims_v1.main:app --host 127.0.0.1 --port 8000
```

Then browse to `http://127.0.0.1:8000/review-ui`.

The review page can list duplicate quarantine batches, show overall indexing/hash progress, display the duplicate path alongside the existing keep-copy path, preview cached image thumbnails or video files, exclude planned operations, and confirm a batch. It intentionally does not execute quarantine moves; run `pims execute-batch <batch_id>` separately only after reviewing and confirming.

When `PIMS_WECHAT_WEBHOOK_URL` is set, `run-safe-workflow` sends an Enterprise WeChat text notification whenever it creates a new duplicate quarantine batch with operations requiring approval.

Exclude a planned operation when needed through the API:

```powershell
curl -X POST http://127.0.0.1:8000/operations/123/exclude -H "x-pims-api-token: <token>"
```

Confirm and execute only after reviewing the batch:

```powershell
pims confirm-batch <batch_id>
pims execute-batch <batch_id>
```

`execute-batch` moves files to `PIMS_QUARANTINE_ROOT`; it does not permanently delete files.

### Recovery

If a run is interrupted:

```powershell
pims recover-tasks
pims run-safe-workflow --keep-root "\\192.168.31.10\personal_folder\网络写真集"
```

### Current Scope

Implemented: indexing, MD5 duplicates, pHash similarity, series candidates, DeepSeek title suggestions, thumbnails, review APIs, operation planning, batch confirmation, quarantine execution, resumable hash tasks, and SQLite backup.

Not implemented: multi-user authentication, role-based authorization, packaged installer/service, and database migrations for non-SQLite deployments.
