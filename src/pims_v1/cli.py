from argparse import ArgumentParser
from collections import Counter
from pathlib import Path
from time import perf_counter

from pims_v1.services.scan_service import DEFAULT_MEDIA_SUFFIXES, ScanService


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="pims")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_sample = subparsers.add_parser("scan-sample")
    scan_sample.add_argument("root")
    scan_sample.add_argument("--limit", type=int, default=1000)
    scan_sample.add_argument("--all-files", action="store_true")

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


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "scan-sample":
        return run_scan_sample(Path(args.root), args.limit, args.all_files)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
