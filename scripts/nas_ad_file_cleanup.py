from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "pims.db"
REPORTS_ROOT = PROJECT_ROOT / "data" / "reports"

EXACT_JUNK_NAMES = {
    "永久地址 - 发布页.txt",
    "机器猫次元 - 整理发布.txt",
    "机器猫次元.url",
}

UNCERTAIN_EXTENSIONS = {".txt", ".url"}
UNCERTAIN_KEYWORDS = [
    "发布页",
    "地址",
    "永久",
    "防迷路",
    "图小乐",
    "官网",
    "网址",
    "主页",
    "导航",
    "收藏",
    "微信",
    "QQ群",
    "qq",
    "twitter",
    "telegram",
]
MAX_UNCERTAIN_BYTES = 64 * 1024


@dataclass(frozen=True)
class FileFinding:
    path: str
    relative_path: str
    file_name: str
    size: int
    category: str
    reason: str


def get_nas_root() -> str:
    con = sqlite3.connect(DB_PATH)
    try:
        row = con.execute(
            "select root_path from libraries where kind='nas' order by id limit 1"
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise RuntimeError("No NAS library root found in libraries table.")
    return row[0]


def split_stem_suffix(name: str) -> tuple[str, str]:
    stem, suffix = os.path.splitext(name)
    return stem, suffix.lower()


def is_exact_junk_name(name: str) -> bool:
    if name in EXACT_JUNK_NAMES:
        return True
    stem, suffix = split_stem_suffix(name)
    match = re.match(r"^(?P<base>.+)-(?P<number>[1-9][0-9]*)$", stem)
    if not match:
        return False
    base_name = match.group("base") + suffix
    return base_name in EXACT_JUNK_NAMES


def uncertain_reason(name: str, size: int) -> str | None:
    stem, suffix = split_stem_suffix(name)
    if suffix not in UNCERTAIN_EXTENSIONS:
        return None
    if size > MAX_UNCERTAIN_BYTES:
        return None
    lowered = name.casefold()
    hits = [keyword for keyword in UNCERTAIN_KEYWORDS if keyword.casefold() in lowered]
    if not hits:
        return None
    if is_exact_junk_name(name):
        return None
    return "keywords=" + "|".join(hits)


def scan(root: str) -> tuple[list[FileFinding], list[FileFinding]]:
    exact: list[FileFinding] = []
    uncertain: list[FileFinding] = []
    seen: set[str] = set()
    con = sqlite3.connect(DB_PATH)
    try:
        rows = con.execute(
            "select file_name, file_size, current_path, original_path from assets "
            "where lower(file_ext) in ('.txt', '.url') "
            "or file_name in (?, ?, ?)",
            tuple(EXACT_JUNK_NAMES),
        ).fetchall()
    finally:
        con.close()

    for file_name, stored_size, current_path, original_path in rows:
        for candidate_path in (current_path, original_path):
            if not candidate_path or candidate_path in seen:
                continue
            seen.add(candidate_path)
            if not candidate_path.startswith(root):
                continue
            if not os.path.isfile(candidate_path):
                continue
            try:
                size = os.path.getsize(candidate_path)
            except OSError:
                size = stored_size if stored_size is not None else -1
            relative = os.path.relpath(candidate_path, root)
            actual_name = os.path.basename(candidate_path)
            if is_exact_junk_name(actual_name):
                exact.append(
                    FileFinding(
                        path=candidate_path,
                        relative_path=relative,
                        file_name=actual_name,
                        size=size,
                        category="exact_delete",
                        reason="explicit_name_or_numeric_conflict_variant",
                    )
                )
                continue
            reason = uncertain_reason(actual_name, size)
            if reason:
                uncertain.append(
                    FileFinding(
                        path=candidate_path,
                        relative_path=relative,
                        file_name=actual_name,
                        size=size,
                        category="uncertain_review",
                        reason=reason,
                    )
                )
    return exact, uncertain


def write_findings(path: Path, findings: list[FileFinding]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["Path", "RelativePath", "FileName", "Size", "Category", "Reason"],
        )
        writer.writeheader()
        for finding in findings:
            writer.writerow(
                {
                    "Path": finding.path,
                    "RelativePath": finding.relative_path,
                    "FileName": finding.file_name,
                    "Size": finding.size,
                    "Category": finding.category,
                    "Reason": finding.reason,
                }
            )


def mark_assets_deleted(paths: list[str], timestamp: str) -> Path:
    report_path = REPORTS_ROOT / f"nas-ad-file-cleanup-db-updates-{timestamp}.csv"
    rows: list[dict[str, object]] = []
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        cur.execute("begin")
        for path in paths:
            normalized = path.replace("/", "\\")
            asset_rows = cur.execute(
                "select id, status, current_path, original_path from assets "
                "where current_path = ? or original_path = ?",
                (normalized, normalized),
            ).fetchall()
            for asset_id, old_status, current_path, original_path in asset_rows:
                cur.execute(
                    "update assets set status = 'deleted', updated_at = CURRENT_TIMESTAMP where id = ?",
                    (asset_id,),
                )
                rows.append(
                    {
                        "AssetId": asset_id,
                        "OldStatus": old_status,
                        "NewStatus": "deleted",
                        "CurrentPath": current_path or "",
                        "OriginalPath": original_path or "",
                    }
                )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    with report_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "AssetId",
                "OldStatus",
                "NewStatus",
                "CurrentPath",
                "OriginalPath",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return report_path


def execute_delete(findings: list[FileFinding], timestamp: str) -> tuple[Path, Path]:
    result_path = REPORTS_ROOT / f"nas-ad-file-cleanup-delete-result-{timestamp}.csv"
    rows: list[dict[str, object]] = []
    deleted_paths: list[str] = []
    for finding in findings:
        result = "skipped"
        error = ""
        try:
            if not os.path.isfile(finding.path):
                result = "missing"
            else:
                os.remove(finding.path)
                deleted_paths.append(finding.path)
                result = "deleted"
        except Exception as exc:
            result = "error"
            error = repr(exc)
        rows.append(
            {
                "Path": finding.path,
                "RelativePath": finding.relative_path,
                "FileName": finding.file_name,
                "Size": finding.size,
                "Result": result,
                "Error": error,
            }
        )

    with result_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["Path", "RelativePath", "FileName", "Size", "Result", "Error"],
        )
        writer.writeheader()
        writer.writerows(rows)
    db_report_path = mark_assets_deleted(deleted_paths, timestamp)
    return result_path, db_report_path


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    root = get_nas_root()
    exact, uncertain = scan(root)

    exact_report = REPORTS_ROOT / f"nas-ad-file-cleanup-exact-{timestamp}.csv"
    uncertain_report = REPORTS_ROOT / f"nas-ad-file-cleanup-uncertain-{timestamp}.csv"
    write_findings(exact_report, exact)
    write_findings(uncertain_report, uncertain)

    print("root", root)
    print("exact", len(exact), dict(Counter(f.file_name for f in exact).most_common(20)))
    print(
        "uncertain",
        len(uncertain),
        dict(Counter(f.file_name for f in uncertain).most_common(20)),
    )
    print("report", exact_report)
    print("report", uncertain_report)

    if args.execute:
        result_report, db_report = execute_delete(exact, timestamp)
        print("report", result_report)
        print("report", db_report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
