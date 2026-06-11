from argparse import ArgumentParser
from collections import Counter
from pathlib import Path
from time import perf_counter

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.config import settings
from pims_v1 import models
from pims_v1.services.duplicate_index_service import build_exact_duplicate_reviews
from pims_v1.services.hash_index_service import compute_missing_md5
from pims_v1.services.index_service import index_library
from pims_v1.services.scan_service import DEFAULT_MEDIA_SUFFIXES, ScanService
from pims_v1.services.series_index_service import build_series_candidates


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

    duplicates = subparsers.add_parser("build-duplicates")
    duplicates.add_argument("--database-url", default=settings.database_url)

    series = subparsers.add_parser("build-series")
    series.add_argument("--min-assets", type=int, default=2)
    series.add_argument("--database-url", default=settings.database_url)

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
    if args.command == "build-duplicates":
        return run_build_duplicates(database_url=args.database_url)
    if args.command == "build-series":
        return run_build_series(min_assets=args.min_assets, database_url=args.database_url)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
