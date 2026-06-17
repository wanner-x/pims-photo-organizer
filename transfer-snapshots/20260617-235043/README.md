# PIMS transfer snapshot 20260617-235043

This snapshot is intended for continuing development on another PC.

## Included

- `database/pims.db`: SQLite database snapshot created with SQLite online backup.
- `logs/*.log`: API and full-detection logs copied from `data/logs`.
- `SHA256SUMS.txt`: SHA-256 checksum for the database snapshot.

## Not included

- `.env` and `.env.*`: contain local secrets and API keys.
- `data/.cache`: generated thumbnails; rebuildable.
- `data/.quarantine`: real quarantined media files; too large and not required for code work.
- `data/pims.db-wal` and `data/pims.db-shm`: runtime SQLite sidecar files; not needed with this backup.

## Restore on another PC

1. Install Git LFS before cloning or pulling this repository:

   ```powershell
   git lfs install
   git clone git@github.com:wanner-x/pims-photo-organizer.git
   cd pims-photo-organizer
   git lfs pull
   ```

2. Restore the database:

   ```powershell
   New-Item -ItemType Directory -Force -Path data | Out-Null
   Copy-Item transfer-snapshots\20260617-235043\database\pims.db data\pims.db -Force
   ```

3. Restore logs if needed:

   ```powershell
   New-Item -ItemType Directory -Force -Path data\logs | Out-Null
   Copy-Item transfer-snapshots\20260617-235043\logs\*.log data\logs\ -Force
   ```

4. Create a local `.env` from `.env.example`, then fill local-only paths and API keys.

## Snapshot progress

- Assets: `558927`
- MD5: `558927 / 558927` (`100.0%`)
- pHash: `17199 / 556410` (`3.09%`)
- Pending reviews: `243487`
- Planned operations: `360658`
- Planned batches: `5`

## Current runtime when exported

- API process was running on port `8000`.
- Full-detection runner was active.
- The workflow was in or after the pHash phase and may have been waiting on later AI/R18/archive steps.
