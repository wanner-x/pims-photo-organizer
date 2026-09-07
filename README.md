# PIMS V1

PIMS V1 is a PC-hosted, NAS-centered photo organization system for large personal libraries.

For the current implementation status, handoff context, known risks, and roadmap, read [Project Status And Roadmap](docs/PROJECT_STATUS_AND_ROADMAP.md).

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
PIMS_KEEP_ROOT=\\192.168.31.10\personal_folder\网络写真集
PIMS_API_TOKEN=<long-random-token>
PIMS_DEEPSEEK_API_KEY=<optional>
PIMS_WECHAT_WEBHOOK_URL=<optional enterprise wechat bot webhook>
PIMS_REVIEW_URL=http://127.0.0.1:8000/review-ui
# Maximum decoded pixels allowed before a file is treated as a decompression bomb.
# Raised well above Pillow's default so large panoramas/scans still hash and thumbnail.
PIMS_MAX_IMAGE_PIXELS=300000000
# When > 0, run-safe-workflow auto-approves and removes this many byte-identical
# (exact MD5) duplicates per run. 0 disables auto-approval (manual review only).
PIMS_AUTO_QUARANTINE_LIMIT=0
# How redundant exact-MD5 duplicates are removed: "delete" removes them outright
# (no quarantine backup, so storage does not grow), "quarantine" keeps a reversible
# copy in quarantine_root. Either way a verified byte-identical keep copy must remain.
PIMS_DUPLICATE_ACTION=delete
# When rule and AI planners disagree but no R18/content risk is flagged, auto-apply
# the AI plan if AI confidence is at least this high (gives the AI more authority).
PIMS_AI_AUTO_APPLY_MIN_CONFIDENCE=0.85
# Concurrent workers for pHash image reads/hashing. pHash is NAS-I/O bound, so
# concurrency hides read latency and is the main throughput lever. DB writes stay
# single-threaded, so other steps and the API are unaffected. 1 = sequential.
PIMS_PHASH_CONCURRENCY=8
```

Save `PIMS_KEEP_ROOT` as UTF-8 and make sure the path matches exactly how the NAS library is indexed; a mis-encoded keep root silently disables NAS-preferred keep-copy selection.

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

Automatically generate AI review suggestions for new series candidates during the same workflow:

```powershell
pims run-safe-workflow --keep-root "\\192.168.31.10\personal_folder\网络写真集" --ai-suggest-limit 50 --auto-archive-limit 0
```

The long-running `scripts\run_full_detection.ps1` defaults `-AiSuggestLimit 50`, `-R18ScanLimit 50`, `-AutoArchiveLimit 20`, `-AutoQuarantineLimit 500`, `-SeriesLimit 0`, `-SimilarLimit 0`, and `-ExecuteConfirmedBatches $true`, so normal background runs focus on resumable hashing, duplicate grouping, R18 sampling, low-risk auto archive against existing candidates, automatic approval of exact-duplicate quarantine, and automatic execution of already-confirmed batches. Series rebuilding and similar-image review building are opt-in because full-library passes are expensive on large collections. Set `-AutoArchiveLimit 0` to disable automatic moves, `-AutoQuarantineLimit 0` to disable exact-duplicate auto-approval, and `-ExecuteConfirmedBatches:$false` to require a manual `execute-batch`.

### Automatic Exact-Duplicate Approval

Exact MD5 matches are byte-identical files, so PIMS can approve and remove the redundant copies without manual review. Each removal is only performed when a byte-identical keep copy still exists on disk, so the last accessible copy is never removed. With `PIMS_DUPLICATE_ACTION=delete` the redundant copy is deleted outright (no quarantine backup, so storage does not keep growing); with `quarantine` the move is reversible. Run it directly with:

```powershell
pims auto-quarantine-duplicates --keep-root "\\192.168.31.10\personal_folder\网络写真集" --limit 500 --action delete
```

Confirmed batches are executed in bounded, incrementally-committed chunks so very large batches no longer load every operation into memory at once. `execute-batch` accepts `--limit` (process at most N operations, resuming on the next call) and `--action delete|quarantine`:

```powershell
pims execute-batch 8 --action delete --limit 20000
```

Or enable it inside the workflow with `--auto-quarantine-limit` (or `PIMS_AUTO_QUARANTINE_LIMIT`):

```powershell
pims run-safe-workflow --keep-root "\\192.168.31.10\personal_folder\网络写真集" --auto-quarantine-limit 500
```

WeChat duplicate-approval notifications only cover the operations that auto-approval could not safely resolve, so manual prompts shrink as automation does more work.

### Retrying Failed Tasks

After fixing a systematic processing error (for example raising `PIMS_MAX_IMAGE_PIXELS`), requeue stuck tasks so they are retried:

```powershell
pims reset-failed-tasks --task-type hash_phash
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

The review page can list duplicate quarantine batches, show overall indexing/hash progress, display background task status and the latest full-detection log tail, display the duplicate path alongside the existing keep-copy path, preview cached image thumbnails or video files, exclude planned operations, and confirm a batch. It intentionally does not execute quarantine moves; run `pims execute-batch <batch_id>` separately only after reviewing and confirming.

The review page can also review AI-generated series organization suggestions. AI suggestions are only proposals until confirmed. After confirmation, PIMS creates a formal series and moves the series files into the NAS archive path under `<PIMS_KEEP_ROOT>/<category>/<title>/`.

When `PIMS_WECHAT_WEBHOOK_URL` is set, `run-safe-workflow` sends an Enterprise WeChat text notification whenever it creates a new duplicate quarantine batch with operations requiring approval.

`run-safe-workflow` prints periodic hash progress lines while it is processing large batches, so long-running PowerShell logs show movement before a full round finishes.

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

Implemented: indexing, MD5 duplicates, pHash similarity, series candidates, DeepSeek title/category suggestions with human review, confirmed series archive moves to NAS, thumbnails, review APIs, operation planning, batch confirmation, quarantine execution, automatic exact-duplicate approval with keep-copy safety guard, resumable hash tasks, failed-task requeueing, and SQLite backup.

Not implemented: multi-user authentication, role-based authorization, packaged installer/service, and database migrations for non-SQLite deployments.
