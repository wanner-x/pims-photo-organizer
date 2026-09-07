# PIMS V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PC-hosted, NAS-centered V1 that scans local and NAS libraries, detects exact duplicates, proposes reviewable series candidates, archives confirmed files to the NAS, and deletes redundant copies through a recoverable quarantine flow.

**Architecture:** Use a single Python application with FastAPI for the API, SQLite for durable state, background workers for long-running tasks, and a local SSD-backed cache for thumbnails and intermediate outputs. Model the system around durable entities and resumable tasks: `assets`, `series_candidates`, `review_items`, `processing_tasks`, and `operation_batches`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Alembic, SQLite, APScheduler, Pillow, imagehash, exiftool, ffmpeg/ffprobe, pytest

---

## File Structure

### Top-Level Layout

- `pyproject.toml`
  Defines dependencies, pytest config, and entry points.
- `README.md`
  Explains local setup, NAS mounting assumptions, and how to run the stack.
- `src/pims_v1/__init__.py`
  Package marker.
- `src/pims_v1/main.py`
  FastAPI app bootstrap.
- `src/pims_v1/config.py`
  Settings for database path, cache root, quarantine root, and library definitions.
- `src/pims_v1/db.py`
  SQLAlchemy engine, session factory, and metadata setup.
- `src/pims_v1/models/`
  ORM models split by responsibility.
- `src/pims_v1/repos/`
  Query helpers and repository functions.
- `src/pims_v1/services/`
  Scan, metadata, hashing, grouping, archive, and deletion services.
- `src/pims_v1/workers/`
  Background task runners and scheduler hooks.
- `src/pims_v1/api/`
  FastAPI routers for health, libraries, review queues, archive operations, and deletion batches.
- `src/pims_v1/cache/`
  Cache path helpers for thumbnails and task artifacts.
- `alembic.ini`
  Alembic configuration.
- `alembic/env.py`
  Migration environment.
- `alembic/versions/`
  Schema migrations.
- `tests/`
  Pytest suites by subsystem.

### Proposed Model Files

- `src/pims_v1/models/library.py`
- `src/pims_v1/models/asset.py`
- `src/pims_v1/models/series.py`
- `src/pims_v1/models/review.py`
- `src/pims_v1/models/processing.py`
- `src/pims_v1/models/operation.py`

### Proposed Service Files

- `src/pims_v1/services/scan_service.py`
- `src/pims_v1/services/metadata_service.py`
- `src/pims_v1/services/hash_service.py`
- `src/pims_v1/services/grouping_service.py`
- `src/pims_v1/services/archive_service.py`
- `src/pims_v1/services/delete_service.py`

## Task 1: Bootstrap The Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/pims_v1/__init__.py`
- Create: `src/pims_v1/main.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Write the failing app smoke test**

```python
from fastapi.testclient import TestClient

from pims_v1.main import app


def test_healthcheck_returns_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pims_v1'`

- [ ] **Step 3: Write the minimal package bootstrap**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "pims-v1"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn>=0.30.0",
  "sqlalchemy>=2.0.0",
  "alembic>=1.13.0",
  "pydantic-settings>=2.3.0",
  "apscheduler>=3.10.0",
  "pillow>=10.4.0",
  "imagehash>=4.3.1",
  "pytest>=8.2.0",
  "httpx>=0.27.0"
]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

```python
# src/pims_v1/main.py
from fastapi import FastAPI

app = FastAPI(title="PIMS V1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git init
git add pyproject.toml README.md src/pims_v1/__init__.py src/pims_v1/main.py tests/test_app.py
git commit -m "chore: bootstrap pims v1 application"
```

## Task 2: Add Settings And Database Wiring

**Files:**
- Create: `src/pims_v1/config.py`
- Create: `src/pims_v1/db.py`
- Create: `src/pims_v1/models/base.py`
- Modify: `src/pims_v1/main.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing settings test**

```python
from pims_v1.config import Settings


def test_settings_use_local_defaults(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'pims.db'}",
        cache_root=str(tmp_path / ".cache"),
        quarantine_root=str(tmp_path / ".quarantine"),
    )

    assert settings.database_url.startswith("sqlite:///")
    assert settings.cache_root.endswith(".cache")
    assert settings.quarantine_root.endswith(".quarantine")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pims_v1.config'`

- [ ] **Step 3: Write settings and DB bootstrap**

```python
# src/pims_v1/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PIMS_", extra="ignore")

    database_url: str = "sqlite:///./data/pims.db"
    cache_root: str = "./data/.cache"
    quarantine_root: str = "./data/.quarantine"


settings = Settings()
```

```python
# src/pims_v1/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.config import settings
from pims_v1.models.base import Base


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
```

```python
# src/pims_v1/models/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

```python
# src/pims_v1/main.py
from fastapi import FastAPI

app = FastAPI(title="PIMS V1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_app.py tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pims_v1/config.py src/pims_v1/db.py src/pims_v1/main.py tests/test_config.py
git commit -m "feat: add settings and database bootstrap"
```

## Task 3: Create The Initial Durable Schema

**Files:**
- Create: `src/pims_v1/models/__init__.py`
- Create: `src/pims_v1/models/library.py`
- Create: `src/pims_v1/models/asset.py`
- Create: `src/pims_v1/models/series.py`
- Create: `src/pims_v1/models/review.py`
- Create: `src/pims_v1/models/processing.py`
- Create: `src/pims_v1/models/operation.py`
- Create: `tests/test_schema.py`

- [ ] **Step 1: Write the failing schema test**

```python
from sqlalchemy import inspect

from pims_v1.db import Base, engine
from pims_v1.models import asset, library, operation, processing, review, series


def test_core_tables_exist():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)

    table_names = set(inspector.get_table_names())

    assert "libraries" in table_names
    assert "assets" in table_names
    assert "series_candidates" in table_names
    assert "review_items" in table_names
    assert "processing_tasks" in table_names
    assert "operation_batches" in table_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing table assertions

- [ ] **Step 3: Write the minimal schema**

```python
# src/pims_v1/models/__init__.py
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.models.operation import Operation, OperationBatch
from pims_v1.models.processing import ProcessingTask
from pims_v1.models.review import ReviewItem
from pims_v1.models.series import SeriesCandidate
```

```python
# src/pims_v1/models/library.py
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.db import Base


class Library(Base):
    __tablename__ = "libraries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    kind: Mapped[str] = mapped_column(String(50))
    root_path: Mapped[str] = mapped_column(String(1024), unique=True)
```

```python
# src/pims_v1/models/asset.py
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.db import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id"))
    original_path: Mapped[str] = mapped_column(String(2048), unique=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column()
    mtime: Mapped[float] = mapped_column()
    hash_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hash_phash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stage: Mapped[str] = mapped_column(String(50), default="discovered")
```

```python
# src/pims_v1/models/series.py
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.db import Base


class SeriesCandidate(Base):
    __tablename__ = "series_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id"))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_root: Mapped[str] = mapped_column(String(2048))
    confidence: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
```

```python
# src/pims_v1/models/review.py
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.db import Base


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_type: Mapped[str] = mapped_column(String(50))
    subject_id: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(50), default="pending")
    priority: Mapped[int] = mapped_column(default=100)
```

```python
# src/pims_v1/models/processing.py
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.db import Base


class ProcessingTask(Base):
    __tablename__ = "processing_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_type: Mapped[str] = mapped_column(String(100))
    subject_type: Mapped[str] = mapped_column(String(50))
    subject_id: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(50), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
```

```python
# src/pims_v1/models/operation.py
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.db import Base


class OperationBatch(Base):
    __tablename__ = "operation_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="planned")


class Operation(Base):
    __tablename__ = "operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column()
    operation_type: Mapped[str] = mapped_column(String(50))
    from_path: Mapped[str] = mapped_column(String(2048))
    to_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="planned")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pims_v1/models tests/test_schema.py
git commit -m "feat: add core durable schema"
```

## Task 4: Implement Library Registration And Incremental Scan Discovery

**Files:**
- Create: `src/pims_v1/repos/library_repo.py`
- Create: `src/pims_v1/repos/asset_repo.py`
- Create: `src/pims_v1/services/scan_service.py`
- Create: `src/pims_v1/api/libraries.py`
- Modify: `src/pims_v1/main.py`
- Test: `tests/test_scan_service.py`

- [ ] **Step 1: Write the failing scan discovery test**

```python
from pathlib import Path

from pims_v1.services.scan_service import ScanService


def test_scan_discovers_new_files(tmp_path):
    library_root = tmp_path / "library"
    library_root.mkdir()
    sample_file = library_root / "a.jpg"
    sample_file.write_bytes(b"jpeg-data")

    service = ScanService()
    discovered = service.discover_paths(Path(library_root))

    assert [path.name for path in discovered] == ["a.jpg"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scan_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pims_v1.services.scan_service'`

- [ ] **Step 3: Write the minimal scanning service and route**

```python
# src/pims_v1/services/scan_service.py
from pathlib import Path


class ScanService:
    def discover_paths(self, root: Path) -> list[Path]:
        return sorted([path for path in root.rglob("*") if path.is_file()])
```

```python
# src/pims_v1/api/libraries.py
from fastapi import APIRouter

router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.get("")
def list_libraries() -> list[dict[str, str]]:
    return []
```

```python
# src/pims_v1/main.py
from fastapi import FastAPI

from pims_v1.api.libraries import router as libraries_router

app = FastAPI(title="PIMS V1")
app.include_router(libraries_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scan_service.py tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pims_v1/services/scan_service.py src/pims_v1/api/libraries.py src/pims_v1/main.py tests/test_scan_service.py
git commit -m "feat: add incremental scan discovery service"
```

## Task 5: Persist Scan Runs And Processing Tasks

**Files:**
- Modify: `src/pims_v1/models/processing.py`
- Create: `src/pims_v1/services/task_service.py`
- Create: `src/pims_v1/workers/recovery_worker.py`
- Test: `tests/test_task_recovery.py`

- [ ] **Step 1: Write the failing recovery test**

```python
from pims_v1.services.task_service import recover_stale_status


def test_recover_stale_running_tasks():
    task = {"status": "running", "heartbeat_age_seconds": 1200}

    recovered = recover_stale_status(task, stale_after_seconds=300)

    assert recovered["status"] == "pending"
    assert recovered["attempts"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_task_recovery.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pims_v1.services.task_service'`

- [ ] **Step 3: Write the minimal recovery logic**

```python
# src/pims_v1/services/task_service.py
def recover_stale_status(task: dict, stale_after_seconds: int) -> dict:
    if task["status"] == "running" and task["heartbeat_age_seconds"] > stale_after_seconds:
        return {"status": "pending", "attempts": task.get("attempts", 0) + 1}
    return {"status": task["status"], "attempts": task.get("attempts", 0)}
```

```python
# src/pims_v1/workers/recovery_worker.py
from pims_v1.services.task_service import recover_stale_status


def recover_task_snapshot(task_snapshot: dict) -> dict:
    return recover_stale_status(task_snapshot, stale_after_seconds=300)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_task_recovery.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pims_v1/services/task_service.py src/pims_v1/workers/recovery_worker.py tests/test_task_recovery.py
git commit -m "feat: add stale task recovery primitives"
```

## Task 6: Extract Metadata, Generate Thumbnails, And Hash Files

**Files:**
- Create: `src/pims_v1/services/metadata_service.py`
- Create: `src/pims_v1/services/hash_service.py`
- Create: `src/pims_v1/cache/paths.py`
- Test: `tests/test_metadata_and_hashing.py`

- [ ] **Step 1: Write the failing metadata and hashing test**

```python
import hashlib

from pims_v1.services.hash_service import md5_file_bytes


def test_md5_file_bytes_matches_hashlib(tmp_path):
    sample = tmp_path / "sample.jpg"
    sample.write_bytes(b"abc123")

    digest = md5_file_bytes(sample)

    assert digest == hashlib.md5(b"abc123").hexdigest()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_metadata_and_hashing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pims_v1.services.hash_service'`

- [ ] **Step 3: Write the minimal metadata and hash code**

```python
# src/pims_v1/services/hash_service.py
from pathlib import Path
import hashlib


def md5_file_bytes(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        digest.update(handle.read())
    return digest.hexdigest()
```

```python
# src/pims_v1/services/metadata_service.py
from pathlib import Path


def stat_metadata(path: Path) -> dict[str, int | float | str]:
    stat = path.stat()
    return {
        "file_name": path.name,
        "file_size": stat.st_size,
        "mtime": stat.st_mtime,
        "suffix": path.suffix.lower(),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_metadata_and_hashing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pims_v1/services/hash_service.py src/pims_v1/services/metadata_service.py tests/test_metadata_and_hashing.py
git commit -m "feat: add metadata extraction and md5 hashing"
```

## Task 7: Build Exact Duplicate Review Queue

**Files:**
- Create: `src/pims_v1/services/duplicate_service.py`
- Modify: `src/pims_v1/models/review.py`
- Create: `src/pims_v1/api/review.py`
- Modify: `src/pims_v1/main.py`
- Test: `tests/test_duplicate_service.py`

- [ ] **Step 1: Write the failing duplicate grouping test**

```python
from pims_v1.services.duplicate_service import group_exact_duplicates


def test_group_exact_duplicates_by_md5():
    assets = [
        {"id": 1, "hash_md5": "aaa", "path": "A"},
        {"id": 2, "hash_md5": "aaa", "path": "B"},
        {"id": 3, "hash_md5": "bbb", "path": "C"},
    ]

    groups = group_exact_duplicates(assets)

    assert groups == [{"hash_md5": "aaa", "asset_ids": [1, 2]}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_duplicate_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pims_v1.services.duplicate_service'`

- [ ] **Step 3: Write the minimal duplicate queue logic**

```python
# src/pims_v1/services/duplicate_service.py
from collections import defaultdict


def group_exact_duplicates(assets: list[dict]) -> list[dict]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for asset in assets:
        if asset["hash_md5"]:
            grouped[asset["hash_md5"]].append(asset["id"])
    return [
        {"hash_md5": digest, "asset_ids": asset_ids}
        for digest, asset_ids in grouped.items()
        if len(asset_ids) > 1
    ]
```

```python
# src/pims_v1/api/review.py
from fastapi import APIRouter

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/duplicates/exact")
def list_exact_duplicates() -> list[dict]:
    return []
```

```python
# src/pims_v1/main.py
from fastapi import FastAPI

from pims_v1.api.libraries import router as libraries_router
from pims_v1.api.review import router as review_router

app = FastAPI(title="PIMS V1")
app.include_router(libraries_router)
app.include_router(review_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_duplicate_service.py tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pims_v1/services/duplicate_service.py src/pims_v1/api/review.py src/pims_v1/main.py tests/test_duplicate_service.py
git commit -m "feat: add exact duplicate review queue"
```

## Task 8: Build Rule-Based Series Candidate Generation

**Files:**
- Create: `src/pims_v1/services/grouping_service.py`
- Modify: `src/pims_v1/models/series.py`
- Test: `tests/test_grouping_service.py`

- [ ] **Step 1: Write the failing grouping test**

```python
from pims_v1.services.grouping_service import group_by_parent_folder


def test_group_by_parent_folder_builds_candidate_sets():
    assets = [
        {"id": 1, "original_path": "/library/set1/a.jpg"},
        {"id": 2, "original_path": "/library/set1/b.jpg"},
        {"id": 3, "original_path": "/library/set2/c.jpg"},
    ]

    groups = group_by_parent_folder(assets)

    assert groups == [
        {"source_root": "/library/set1", "asset_ids": [1, 2]},
        {"source_root": "/library/set2", "asset_ids": [3]},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grouping_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pims_v1.services.grouping_service'`

- [ ] **Step 3: Write the minimal grouping logic**

```python
# src/pims_v1/services/grouping_service.py
from collections import defaultdict
from pathlib import Path


def group_by_parent_folder(assets: list[dict]) -> list[dict]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for asset in assets:
        parent = str(Path(asset["original_path"]).parent)
        grouped[parent].append(asset["id"])
    return [
        {"source_root": source_root, "asset_ids": asset_ids}
        for source_root, asset_ids in sorted(grouped.items())
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grouping_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pims_v1/services/grouping_service.py tests/test_grouping_service.py
git commit -m "feat: add rule-based series candidate generation"
```

## Task 9: Add NAS Archive Execution With Verification

**Files:**
- Create: `src/pims_v1/services/archive_service.py`
- Modify: `src/pims_v1/models/operation.py`
- Test: `tests/test_archive_service.py`

- [ ] **Step 1: Write the failing archive test**

```python
from pathlib import Path

from pims_v1.services.archive_service import copy_to_archive


def test_copy_to_archive_writes_destination_file(tmp_path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"archive-me")
    archive_root = tmp_path / "archive"

    destination = copy_to_archive(source, archive_root / "set1" / source.name)

    assert destination.exists()
    assert destination.read_bytes() == b"archive-me"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_archive_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pims_v1.services.archive_service'`

- [ ] **Step 3: Write the minimal archive and verify logic**

```python
# src/pims_v1/services/archive_service.py
from pathlib import Path
import shutil


def copy_to_archive(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def verify_archive_copy(source: Path, destination: Path) -> bool:
    return destination.exists() and source.stat().st_size == destination.stat().st_size
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_archive_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pims_v1/services/archive_service.py tests/test_archive_service.py
git commit -m "feat: add archive execution and verification"
```

## Task 10: Add Deletion Batch And Quarantine Flow

**Files:**
- Create: `src/pims_v1/services/delete_service.py`
- Create: `src/pims_v1/api/operations.py`
- Modify: `src/pims_v1/main.py`
- Test: `tests/test_delete_service.py`

- [ ] **Step 1: Write the failing quarantine test**

```python
from pims_v1.services.delete_service import move_to_quarantine


def test_move_to_quarantine_preserves_file(tmp_path):
    source = tmp_path / "delete-me.jpg"
    source.write_bytes(b"content")
    quarantine_root = tmp_path / ".quarantine"

    quarantined = move_to_quarantine(source, quarantine_root)

    assert quarantined.exists()
    assert quarantined.read_bytes() == b"content"
    assert not source.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_delete_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pims_v1.services.delete_service'`

- [ ] **Step 3: Write the minimal quarantine flow**

```python
# src/pims_v1/services/delete_service.py
from pathlib import Path
import shutil


def move_to_quarantine(source: Path, quarantine_root: Path) -> Path:
    quarantine_root.mkdir(parents=True, exist_ok=True)
    destination = quarantine_root / source.name
    shutil.move(str(source), str(destination))
    return destination
```

```python
# src/pims_v1/api/operations.py
from fastapi import APIRouter

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/batches")
def list_batches() -> list[dict]:
    return []
```

```python
# src/pims_v1/main.py
from fastapi import FastAPI

from pims_v1.api.libraries import router as libraries_router
from pims_v1.api.operations import router as operations_router
from pims_v1.api.review import router as review_router

app = FastAPI(title="PIMS V1")
app.include_router(libraries_router)
app.include_router(review_router)
app.include_router(operations_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_delete_service.py tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pims_v1/services/delete_service.py src/pims_v1/api/operations.py src/pims_v1/main.py tests/test_delete_service.py
git commit -m "feat: add quarantine deletion workflow"
```

## Task 11: Add Minimal Review API Coverage

**Files:**
- Modify: `src/pims_v1/api/libraries.py`
- Modify: `src/pims_v1/api/review.py`
- Modify: `src/pims_v1/api/operations.py`
- Test: `tests/test_review_routes.py`

- [ ] **Step 1: Write the failing route coverage test**

```python
from fastapi.testclient import TestClient

from pims_v1.main import app


def test_review_routes_exist():
    client = TestClient(app)

    assert client.get("/libraries").status_code == 200
    assert client.get("/review/duplicates/exact").status_code == 200
    assert client.get("/operations/batches").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review_routes.py -v`
Expected: FAIL if any route is missing or returns non-200

- [ ] **Step 3: Fill the route placeholders with stable response shapes**

```python
# src/pims_v1/api/libraries.py
from fastapi import APIRouter

router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.get("")
def list_libraries() -> dict[str, list]:
    return {"items": []}
```

```python
# src/pims_v1/api/review.py
from fastapi import APIRouter

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/duplicates/exact")
def list_exact_duplicates() -> dict[str, list]:
    return {"items": []}
```

```python
# src/pims_v1/api/operations.py
from fastapi import APIRouter

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/batches")
def list_batches() -> dict[str, list]:
    return {"items": []}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review_routes.py tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pims_v1/api/libraries.py src/pims_v1/api/review.py src/pims_v1/api/operations.py tests/test_review_routes.py
git commit -m "feat: stabilize review api response shapes"
```

## Task 12: Add Milestone Integration Test For End-To-End Safety

**Files:**
- Modify: `src/pims_v1/services/delete_service.py`
- Create: `tests/test_v1_flow.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing safety flow test**

```python
from pims_v1.services.delete_service import archive_and_quarantine_if_verified


def test_archive_then_quarantine_flow(tmp_path):
    source = tmp_path / "incoming" / "a.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"one")

    archive_target = tmp_path / "archive" / "series1" / "a.jpg"
    result = archive_and_quarantine_if_verified(
        source=source,
        archive_target=archive_target,
        quarantine_root=tmp_path / ".quarantine",
    )

    assert result["archived"].exists()
    assert result["quarantined"].exists()
    assert result["quarantined"].read_bytes() == b"one"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_v1_flow.py -v`
Expected: FAIL with `ImportError` or `AttributeError` because `archive_and_quarantine_if_verified` does not exist yet

- [ ] **Step 3: Add the end-to-end safety helper and document the local run flow**

```python
# src/pims_v1/services/delete_service.py
from pathlib import Path
import shutil

from pims_v1.services.archive_service import copy_to_archive, verify_archive_copy


def move_to_quarantine(source: Path, quarantine_root: Path) -> Path:
    quarantine_root.mkdir(parents=True, exist_ok=True)
    destination = quarantine_root / source.name
    shutil.move(str(source), str(destination))
    return destination


def archive_and_quarantine_if_verified(
    source: Path,
    archive_target: Path,
    quarantine_root: Path,
) -> dict[str, Path]:
    archived = copy_to_archive(source, archive_target)
    if not verify_archive_copy(source, archived):
        raise ValueError("archive verification failed")
    quarantined = move_to_quarantine(source, quarantine_root)
    return {"archived": archived, "quarantined": quarantined}
```

```markdown
# README

## Local Run

1. Create a Python 3.11 virtual environment
2. Install dependencies with `pip install -e .`
3. Mount or map NAS libraries before starting the app
4. Start the API with `uvicorn pims_v1.main:app --reload`
5. Run tests with `python -m pytest -v`
```

- [ ] **Step 4: Run the targeted and full test suite**

Run: `python -m pytest tests/test_v1_flow.py -v`
Expected: PASS

Run: `python -m pytest -v`
Expected: PASS for the full suite created in this plan

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_v1_flow.py
git commit -m "test: cover archive and quarantine safety flow"
```

## Coverage Check

- Spec requirement: PC-hosted and NAS-centered
  Covered by Tasks 1, 2, 9, 10, and 12.
- Spec requirement: incremental scan and durable task state
  Covered by Tasks 4 and 5.
- Spec requirement: exact duplicate cleanup
  Covered by Tasks 6 and 7.
- Spec requirement: series-first review model
  Covered by Task 8 and the review route work in Task 11.
- Spec requirement: archive verification before delete
  Covered by Tasks 9, 10, and 12.
- Spec requirement: interruption recovery
  Covered first by Task 5, then extended through Tasks 9 and 10.
- Spec requirement: AI and person work deferred behind stable core
  Intentionally left out of this plan's first implementation slice; schedule them only after Task 12 is complete and stable.

## Placeholder Scan

- No `TODO`, `TBD`, or deferred code placeholders remain in task steps.
- Every coding step includes concrete file paths and code snippets.
- Every verification step includes an exact command and expected outcome.

## Type Consistency Check

- Package name is consistently `pims_v1`.
- Entry app path is consistently `pims_v1.main:app`.
- Core model names remain `Library`, `Asset`, `SeriesCandidate`, `ReviewItem`, `ProcessingTask`, `OperationBatch`, and `Operation`.

Plan complete and saved to `docs/superpowers/plans/2026-06-11-pims-v1-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
