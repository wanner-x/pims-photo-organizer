from argparse import ArgumentParser
from collections import Counter
from pathlib import Path
from time import perf_counter

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.config import settings
from pims_v1 import models
from pims_v1.services.ai_naming_service import suggest_series_title
from pims_v1.services.backup_service import backup_sqlite_database
from pims_v1.services.deepseek_client import DeepSeekClient
from pims_v1.services.duplicate_index_service import build_exact_duplicate_reviews
from pims_v1.services.hash_index_service import compute_missing_md5
from pims_v1.services.index_service import index_library
from pims_v1.services.operation_plan_service import (
    confirm_operation_batch,
    create_duplicate_quarantine_plan,
    exclude_operation,
    execute_confirmed_batch,
    list_operation_batches,
)
from pims_v1.services.phash_index_service import IMAGE_SUFFIXES, compute_missing_phash
from pims_v1.services.review_service import list_series_candidates
from pims_v1.services.safe_workflow_service import run_safe_workflow
from pims_v1.services.scan_service import DEFAULT_MEDIA_SUFFIXES, ScanService
from pims_v1.services.series_index_service import build_series_candidates
from pims_v1.services.series_confirm_service import confirm_series_candidate
from pims_v1.services.similar_index_service import build_similar_image_reviews
from pims_v1.services.status_service import database_status
from pims_v1.services.task_service import enqueue_task, list_tasks, recover_stale_tasks
from pims_v1.services.task_worker_service import process_md5_tasks, process_phash_tasks
from pims_v1.services.thumbnail_service import ensure_thumbnail


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="pims")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_sample = subparsers.add_parser("scan-sample")
    scan_sample.add_argument("root")
    scan_sample.add_argument("--limit", type=int, default=1000)
    scan_sample.add_argument("--all-files", action="store_true")

    index = subparsers.add_parser("index-library")
    index.add_argument("root")
    index.add_argument("--name", required=True)
    index.add_argument("--kind", choices=["local", "nas", "import"], required=True)
    index.add_argument("--limit", type=int, default=None)
    index.add_argument("--database-url", default=settings.database_url)

    hash_md5 = subparsers.add_parser("hash-md5")
    hash_md5.add_argument("--limit", type=int, default=None)
    hash_md5.add_argument("--max-size-mb", type=int, default=None)
    hash_md5.add_argument("--database-url", default=settings.database_url)

    hash_phash = subparsers.add_parser("hash-phash")
    hash_phash.add_argument("--limit", type=int, default=None)
    hash_phash.add_argument("--database-url", default=settings.database_url)

    duplicates = subparsers.add_parser("build-duplicates")
    duplicates.add_argument("--database-url", default=settings.database_url)

    similar = subparsers.add_parser("build-similar")
    similar.add_argument("--threshold", type=int, default=6)
    similar.add_argument("--database-url", default=settings.database_url)

    series = subparsers.add_parser("build-series")
    series.add_argument("--min-assets", type=int, default=2)
    series.add_argument("--database-url", default=settings.database_url)

    status = subparsers.add_parser("status")
    status.add_argument("--database-url", default=settings.database_url)

    list_series = subparsers.add_parser("list-series")
    list_series.add_argument("--limit", type=int, default=20)
    list_series.add_argument("--database-url", default=settings.database_url)

    duplicate_plan = subparsers.add_parser("plan-duplicate-quarantine")
    duplicate_plan.add_argument("--keep-root", required=True)
    duplicate_plan.add_argument("--database-url", default=settings.database_url)

    list_batches = subparsers.add_parser("list-batches")
    list_batches.add_argument("--database-url", default=settings.database_url)

    confirm_batch = subparsers.add_parser("confirm-batch")
    confirm_batch.add_argument("batch_id", type=int)
    confirm_batch.add_argument("--database-url", default=settings.database_url)

    exclude = subparsers.add_parser("exclude-operation")
    exclude.add_argument("operation_id", type=int)
    exclude.add_argument("--database-url", default=settings.database_url)

    execute_batch = subparsers.add_parser("execute-batch")
    execute_batch.add_argument("batch_id", type=int)
    execute_batch.add_argument("--quarantine-root", default=settings.quarantine_root)
    execute_batch.add_argument("--database-url", default=settings.database_url)

    enqueue_md5 = subparsers.add_parser("enqueue-md5-tasks")
    enqueue_md5.add_argument("--limit", type=int, default=None)
    enqueue_md5.add_argument("--database-url", default=settings.database_url)

    list_task_parser = subparsers.add_parser("list-tasks")
    list_task_parser.add_argument("--status", default=None)
    list_task_parser.add_argument("--limit", type=int, default=100)
    list_task_parser.add_argument("--database-url", default=settings.database_url)

    recover_tasks = subparsers.add_parser("recover-tasks")
    recover_tasks.add_argument("--stale-after-seconds", type=int, default=300)
    recover_tasks.add_argument("--database-url", default=settings.database_url)

    process_md5 = subparsers.add_parser("process-md5-tasks")
    process_md5.add_argument("--limit", type=int, default=100)
    process_md5.add_argument("--max-size-mb", type=int, default=None)
    process_md5.add_argument("--database-url", default=settings.database_url)

    suggest_title = subparsers.add_parser("suggest-series-title")
    suggest_title.add_argument("candidate_id", type=int)
    suggest_title.add_argument("--database-url", default=settings.database_url)

    enqueue_phash = subparsers.add_parser("enqueue-phash-tasks")
    enqueue_phash.add_argument("--limit", type=int, default=None)
    enqueue_phash.add_argument("--database-url", default=settings.database_url)

    process_phash = subparsers.add_parser("process-phash-tasks")
    process_phash.add_argument("--limit", type=int, default=100)
    process_phash.add_argument("--database-url", default=settings.database_url)

    thumbnails = subparsers.add_parser("build-thumbnails")
    thumbnails.add_argument("--limit", type=int, default=100)
    thumbnails.add_argument("--cache-root", default=settings.cache_root)
    thumbnails.add_argument("--database-url", default=settings.database_url)

    confirm_series = subparsers.add_parser("confirm-series")
    confirm_series.add_argument("candidate_id", type=int)
    confirm_series.add_argument("--archive-root", required=True)
    confirm_series.add_argument("--database-url", default=settings.database_url)

    safe_workflow = subparsers.add_parser("run-safe-workflow")
    safe_workflow.add_argument("--keep-root", default=None)
    safe_workflow.add_argument("--cache-root", default=settings.cache_root)
    safe_workflow.add_argument("--md5-limit", type=int, default=1000)
    safe_workflow.add_argument("--phash-limit", type=int, default=1000)
    safe_workflow.add_argument("--thumbnail-limit", type=int, default=1000)
    safe_workflow.add_argument("--min-series-assets", type=int, default=2)
    safe_workflow.add_argument("--similar-threshold", type=int, default=6)
    safe_workflow.add_argument("--database-url", default=settings.database_url)

    backup = subparsers.add_parser("backup-db")
    backup.add_argument("--database-url", default=settings.database_url)
    backup.add_argument("--backup-dir", default="./data/backups")
    backup.add_argument("--label", default="manual")

    return parser


def run_scan_sample(root: Path, limit: int, all_files: bool) -> int:
    service = ScanService()
    suffixes = None if all_files else DEFAULT_MEDIA_SUFFIXES
    start = perf_counter()
    paths = service.discover_paths(root, limit=limit, suffixes=suffixes)
    elapsed = perf_counter() - start

    extensions = Counter(path.suffix.lower() or "<none>" for path in paths)
    top_dirs = Counter()
    for path in paths:
        relative = path.relative_to(root)
        top_dirs[relative.parts[0] if relative.parts else "<root>"] += 1

    print(f"root={root}")
    print(f"exists={root.exists()}")
    print(f"sampled_files={len(paths)}")
    print(f"elapsed_seconds={elapsed:.3f}")
    print("extensions=")
    for suffix, count in extensions.most_common(20):
        print(f"  {suffix}: {count}")
    print("top_dirs=")
    for name, count in top_dirs.most_common(10):
        print(f"  {name}: {count}")
    print("sample_paths=")
    for path in paths[:10]:
        print(f"  {path}")
    return 0


def run_index_library(
    root: Path,
    name: str,
    kind: str,
    limit: int | None,
    database_url: str,
) -> int:
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        summary = index_library(
            session=session,
            name=name,
            kind=kind,
            root_path=root,
            limit=limit,
        )
    finally:
        session.close()

    print(f"root={root}")
    print(f"database_url={database_url}")
    print(f"discovered={summary['discovered']}")
    print(f"created={summary['created']}")
    print(f"updated={summary['updated']}")
    return 0


def make_session(database_url: str):
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def run_hash_md5(limit: int | None, max_size_mb: int | None, database_url: str) -> int:
    session = make_session(database_url)
    max_bytes = max_size_mb * 1024 * 1024 if max_size_mb is not None else None
    try:
        summary = compute_missing_md5(session=session, limit=limit, max_bytes=max_bytes)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"processed={summary['processed']}")
    print(f"skipped_missing={summary['skipped_missing']}")
    print(f"skipped_oversize={summary['skipped_oversize']}")
    return 0


def run_hash_phash(limit: int | None, database_url: str) -> int:
    session = make_session(database_url)
    try:
        summary = compute_missing_phash(session=session, limit=limit)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"processed={summary['processed']}")
    print(f"skipped_missing={summary['skipped_missing']}")
    print(f"skipped_non_image={summary['skipped_non_image']}")
    print(f"failed={summary['failed']}")
    return 0


def run_build_duplicates(database_url: str) -> int:
    session = make_session(database_url)
    try:
        summary = build_exact_duplicate_reviews(session=session)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"groups={summary['groups']}")
    print(f"review_items={summary['review_items']}")
    return 0


def run_build_similar(threshold: int, database_url: str) -> int:
    session = make_session(database_url)
    try:
        summary = build_similar_image_reviews(session=session, threshold=threshold)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"groups={summary['groups']}")
    print(f"review_items={summary['review_items']}")
    return 0


def run_build_series(min_assets: int, database_url: str) -> int:
    session = make_session(database_url)
    try:
        summary = build_series_candidates(session=session, min_assets=min_assets)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"candidates={summary['candidates']}")
    print(f"review_items={summary['review_items']}")
    return 0


def run_status(database_url: str) -> int:
    session = make_session(database_url)
    try:
        status = database_status(session)
    finally:
        session.close()

    print(f"database_url={database_url}")
    for key, value in status.items():
        print(f"{key}={value}")
    return 0


def run_list_series(limit: int, database_url: str) -> int:
    session = make_session(database_url)
    try:
        candidates = list_series_candidates(session, limit=limit)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"series_candidates={len(candidates)}")
    for candidate in candidates:
        print(
            f"{candidate['id']} | {candidate['asset_count']} | "
            f"{candidate['status']} | {candidate['title']} | {candidate['source_root']}"
        )
    return 0


def run_plan_duplicate_quarantine(keep_root: str, database_url: str) -> int:
    session = make_session(database_url)
    try:
        summary = create_duplicate_quarantine_plan(session=session, keep_root=keep_root)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"batch_id={summary['batch_id']}")
    print(f"operations={summary['operations']}")
    return 0


def run_list_batches(database_url: str) -> int:
    session = make_session(database_url)
    try:
        batches = list_operation_batches(session=session)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"batches={len(batches)}")
    for batch in batches:
        print(
            f"{batch['id']} | {batch['operation_count']} | "
            f"{batch['status']} | {batch['batch_type']} | {batch['description']}"
        )
    return 0


def run_confirm_batch(batch_id: int, database_url: str) -> int:
    session = make_session(database_url)
    try:
        summary = confirm_operation_batch(session=session, batch_id=batch_id)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"batch_id={summary['batch_id']}")
    print(f"operations={summary['operations']}")
    print(f"status={summary['status']}")
    return 0


def run_exclude_operation(operation_id: int, database_url: str) -> int:
    session = make_session(database_url)
    try:
        summary = exclude_operation(session=session, operation_id=operation_id)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"operation_id={summary['operation_id']}")
    print(f"status={summary['status']}")
    return 0


def run_execute_batch(batch_id: int, quarantine_root: str, database_url: str) -> int:
    session = make_session(database_url)
    try:
        summary = execute_confirmed_batch(
            session=session,
            batch_id=batch_id,
            quarantine_root=quarantine_root,
        )
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"batch_id={summary['batch_id']}")
    print(f"executed={summary['executed']}")
    print(f"failed={summary['failed']}")
    print(f"status={summary['status']}")
    return 0


def run_enqueue_md5_tasks(limit: int | None, database_url: str) -> int:
    session = make_session(database_url)
    try:
        query = (
            session.query(models.Asset)
            .filter(models.Asset.hash_md5.is_(None))
            .order_by(models.Asset.id)
        )
        if limit is not None:
            query = query.limit(limit)
        queued = 0
        for asset in query.all():
            before_id = (
                session.query(models.ProcessingTask.id)
                .filter(
                    models.ProcessingTask.task_type == "hash_md5",
                    models.ProcessingTask.subject_type == "asset",
                    models.ProcessingTask.subject_id == asset.id,
                    models.ProcessingTask.status.in_(("pending", "running")),
                )
                .scalar()
            )
            enqueue_task(session, "hash_md5", "asset", asset.id)
            if before_id is None:
                queued += 1
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"queued={queued}")
    return 0


def run_list_tasks(status: str | None, limit: int, database_url: str) -> int:
    session = make_session(database_url)
    try:
        tasks = list_tasks(session, status=status, limit=limit)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"tasks={len(tasks)}")
    for task in tasks:
        print(
            f"{task['id']} | {task['status']} | {task['attempts']} | "
            f"{task['task_type']} | {task['subject_type']}:{task['subject_id']} | "
            f"{task['last_error']}"
        )
    return 0


def run_recover_tasks(stale_after_seconds: int, database_url: str) -> int:
    session = make_session(database_url)
    try:
        summary = recover_stale_tasks(
            session,
            stale_after_seconds=stale_after_seconds,
        )
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"recovered={summary['recovered']}")
    return 0


def run_process_md5_tasks(
    limit: int,
    max_size_mb: int | None,
    database_url: str,
) -> int:
    session = make_session(database_url)
    max_bytes = max_size_mb * 1024 * 1024 if max_size_mb is not None else None
    try:
        summary = process_md5_tasks(
            session=session,
            limit=limit,
            max_bytes=max_bytes,
        )
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"processed={summary['processed']}")
    print(f"failed={summary['failed']}")
    print(f"skipped_oversize={summary['skipped_oversize']}")
    return 0


def run_suggest_series_title(candidate_id: int, database_url: str) -> int:
    session = make_session(database_url)
    client = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    try:
        result = suggest_series_title(
            session=session,
            candidate_id=candidate_id,
            client=client,
        )
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"candidate_id={result['candidate_id']}")
    print(f"title={result['title']}")
    return 0


def run_enqueue_phash_tasks(limit: int | None, database_url: str) -> int:
    session = make_session(database_url)
    try:
        query = (
            session.query(models.Asset)
            .filter(models.Asset.hash_phash.is_(None))
            .filter(models.Asset.file_ext.in_(sorted(IMAGE_SUFFIXES)))
            .order_by(models.Asset.id)
        )
        if limit is not None:
            query = query.limit(limit)
        queued = 0
        for asset in query.all():
            before_id = (
                session.query(models.ProcessingTask.id)
                .filter(
                    models.ProcessingTask.task_type == "hash_phash",
                    models.ProcessingTask.subject_type == "asset",
                    models.ProcessingTask.subject_id == asset.id,
                    models.ProcessingTask.status.in_(("pending", "running")),
                )
                .scalar()
            )
            enqueue_task(session, "hash_phash", "asset", asset.id)
            if before_id is None:
                queued += 1
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"queued={queued}")
    return 0


def run_process_phash_tasks(limit: int, database_url: str) -> int:
    session = make_session(database_url)
    try:
        summary = process_phash_tasks(session=session, limit=limit)
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"processed={summary['processed']}")
    print(f"failed={summary['failed']}")
    print(f"skipped_non_image={summary['skipped_non_image']}")
    return 0


def run_build_thumbnails(limit: int, cache_root: str, database_url: str) -> int:
    session = make_session(database_url)
    summary = {
        "created": 0,
        "exists": 0,
        "skipped_non_image": 0,
        "missing": 0,
        "failed": 0,
    }
    try:
        assets = session.query(models.Asset).order_by(models.Asset.id).limit(limit).all()
        for asset in assets:
            result = ensure_thumbnail(
                session=session,
                asset_id=asset.id,
                cache_root=cache_root,
            )
            status = str(result["status"])
            if status in summary:
                summary[status] += 1
    finally:
        session.close()

    print(f"database_url={database_url}")
    for key, value in summary.items():
        print(f"{key}={value}")
    return 0


def run_confirm_series(candidate_id: int, archive_root: str, database_url: str) -> int:
    session = make_session(database_url)
    try:
        result = confirm_series_candidate(
            session=session,
            candidate_id=candidate_id,
            archive_root=archive_root,
        )
    finally:
        session.close()

    print(f"database_url={database_url}")
    print(f"candidate_id={result['candidate_id']}")
    print(f"series_id={result['series_id']}")
    print(f"archive_path={result['archive_path']}")
    return 0


def run_safe_workflow_command(
    *,
    keep_root: str | None,
    cache_root: str,
    md5_limit: int,
    phash_limit: int,
    thumbnail_limit: int,
    min_series_assets: int,
    similar_threshold: int,
    database_url: str,
) -> int:
    session = make_session(database_url)
    try:
        summary = run_safe_workflow(
            session=session,
            keep_root=keep_root,
            cache_root=cache_root,
            md5_limit=md5_limit,
            phash_limit=phash_limit,
            thumbnail_limit=thumbnail_limit,
            min_series_assets=min_series_assets,
            similar_threshold=similar_threshold,
        )
    finally:
        session.close()

    print(f"database_url={database_url}")
    for section, values in summary.items():
        for key, value in values.items():
            print(f"{section}.{key}={value}")
    return 0


def run_backup_db(database_url: str, backup_dir: str, label: str) -> int:
    result = backup_sqlite_database(
        database_url=database_url,
        backup_dir=backup_dir,
        label=label,
    )
    print(f"database_url={database_url}")
    print(f"status={result['status']}")
    print(f"path={result['path']}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "scan-sample":
        return run_scan_sample(Path(args.root), args.limit, args.all_files)
    if args.command == "index-library":
        return run_index_library(
            root=Path(args.root),
            name=args.name,
            kind=args.kind,
            limit=args.limit,
            database_url=args.database_url,
        )
    if args.command == "hash-md5":
        return run_hash_md5(
            limit=args.limit,
            max_size_mb=args.max_size_mb,
            database_url=args.database_url,
        )
    if args.command == "hash-phash":
        return run_hash_phash(limit=args.limit, database_url=args.database_url)
    if args.command == "build-duplicates":
        return run_build_duplicates(database_url=args.database_url)
    if args.command == "build-similar":
        return run_build_similar(threshold=args.threshold, database_url=args.database_url)
    if args.command == "build-series":
        return run_build_series(min_assets=args.min_assets, database_url=args.database_url)
    if args.command == "status":
        return run_status(database_url=args.database_url)
    if args.command == "list-series":
        return run_list_series(limit=args.limit, database_url=args.database_url)
    if args.command == "plan-duplicate-quarantine":
        return run_plan_duplicate_quarantine(
            keep_root=args.keep_root,
            database_url=args.database_url,
        )
    if args.command == "list-batches":
        return run_list_batches(database_url=args.database_url)
    if args.command == "confirm-batch":
        return run_confirm_batch(batch_id=args.batch_id, database_url=args.database_url)
    if args.command == "exclude-operation":
        return run_exclude_operation(
            operation_id=args.operation_id,
            database_url=args.database_url,
        )
    if args.command == "execute-batch":
        return run_execute_batch(
            batch_id=args.batch_id,
            quarantine_root=args.quarantine_root,
            database_url=args.database_url,
        )
    if args.command == "enqueue-md5-tasks":
        return run_enqueue_md5_tasks(limit=args.limit, database_url=args.database_url)
    if args.command == "list-tasks":
        return run_list_tasks(
            status=args.status,
            limit=args.limit,
            database_url=args.database_url,
        )
    if args.command == "recover-tasks":
        return run_recover_tasks(
            stale_after_seconds=args.stale_after_seconds,
            database_url=args.database_url,
        )
    if args.command == "process-md5-tasks":
        return run_process_md5_tasks(
            limit=args.limit,
            max_size_mb=args.max_size_mb,
            database_url=args.database_url,
        )
    if args.command == "suggest-series-title":
        return run_suggest_series_title(
            candidate_id=args.candidate_id,
            database_url=args.database_url,
        )
    if args.command == "enqueue-phash-tasks":
        return run_enqueue_phash_tasks(limit=args.limit, database_url=args.database_url)
    if args.command == "process-phash-tasks":
        return run_process_phash_tasks(limit=args.limit, database_url=args.database_url)
    if args.command == "build-thumbnails":
        return run_build_thumbnails(
            limit=args.limit,
            cache_root=args.cache_root,
            database_url=args.database_url,
        )
    if args.command == "confirm-series":
        return run_confirm_series(
            candidate_id=args.candidate_id,
            archive_root=args.archive_root,
            database_url=args.database_url,
        )
    if args.command == "run-safe-workflow":
        return run_safe_workflow_command(
            keep_root=args.keep_root,
            cache_root=args.cache_root,
            md5_limit=args.md5_limit,
            phash_limit=args.phash_limit,
            thumbnail_limit=args.thumbnail_limit,
            min_series_assets=args.min_series_assets,
            similar_threshold=args.similar_threshold,
            database_url=args.database_url,
        )
    if args.command == "backup-db":
        return run_backup_db(
            database_url=args.database_url,
            backup_dir=args.backup_dir,
            label=args.label,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
