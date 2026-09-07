from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "pims.db"
REPORTS_ROOT = PROJECT_ROOT / "data" / "reports"

BOUTIQUE_DIR_NAME = "\u7cbe\u54c1"
OTHER_DIR_NAME = "\u5176\u5b83\u753b\u518c"

BOUTIQUE_RULES: dict[str, list[str]] = {
    "\u68ee\u841d\u8d22\u56e2": ["\u68ee\u841d\u8d22\u56e2", "\u68ee\u841d", "X-077"],
    "\u7d27\u6025\u4f01\u5212": ["\u7d27\u6025\u4f01\u5212"],
    "\u5c11\u5973\u79e9\u5e8f": ["\u5c11\u5973\u79e9\u5e8f"],
    "\u6a59\u5b50\u55b5": ["\u6a59\u5b50\u55b5"],
    "\u6751\u4e0a\u897f\u74dc": ["\u6751\u4e0a\u897f\u74dc"],
    "\u7d20\u4eba\u6e14\u592b": ["\u7d20\u4eba\u6e14\u592b"],
    "\u6d41\u6b32xx\u5de5\u574a": ["\u6d41\u6b32xx\u5de5\u574a", "\u6d41\u6b32", "xx\u5de5\u574a"],
    "\u840c\u91cf\u5b88\u6052": ["\u840c\u91cf\u5b88\u6052"],
    "\u7a1a\u4e56\u753b\u518c": ["\u7a1a\u4e56"],
    "\u91d1\u9c7ckinngyo\uff08\u82b1\u97f3\u6817\u5b50\uff09": [
        "\u91d1\u9c7c",
        "kinngyo",
        "\u82b1\u97f3\u6817\u5b50",
    ],
}

ORDINARY_RULES: dict[str, list[str]] = {
    "\u7206\u673a\u5c11\u5973\u55b5\u5c0f\u5409": [
        "\u7206\u673a\u5c11\u5973\u55b5\u5c0f\u5409",
        "\u55b5\u5c0f\u5409",
    ],
}

GENERIC_PREFIXES = {
    "\u5199\u771f",
    "\u5408\u96c6",
    "\u5957\u56fe",
    "\u753b\u518c",
    "\u56fe\u7247",
    "\u89c6\u9891",
    "cos",
    "cosplay",
    "photo",
    "photos",
}

JUNK_EXACT_NAMES = {
    "\u6c38\u4e45\u5730\u5740 - \u53d1\u5e03\u9875.txt",
    "\u673a\u5668\u732b\u6b21\u5143 - \u6574\u7406\u53d1\u5e03.txt",
    "\u673a\u5668\u732b\u6b21\u5143.url",
}


@dataclass(frozen=True)
class DirectoryInfo:
    path: str
    relative_path: str
    parts: tuple[str, ...]
    depth: int
    parent: str
    name: str
    child_directory_count: int
    file_count: int
    total_bytes: int
    top_bucket: str


@dataclass(frozen=True)
class MoveRow:
    source_path: str
    target_path: str
    rule: str
    alias: str
    action: str
    reason: str
    review_status: str


@dataclass(frozen=True)
class ExecutionResult:
    source_path: str
    target_path: str
    rule: str
    alias: str
    action: str
    reason: str
    review_status: str
    result: str
    final_target_path: str
    error: str


PATH_COLUMNS = {
    "archive_execution_records": ["source_path", "target_path"],
    "archive_planning_records": ["source_root"],
    "archive_rollback_records": ["rollback_source_path", "rollback_target_path"],
    "assets": ["original_path", "current_path"],
    "operations": ["from_path", "to_path"],
    "scan_runs": ["root_path"],
    "series": ["archive_path"],
    "series_candidates": ["source_root"],
    "series_moderation_samples": ["sample_path"],
    "series_suggestions": ["suggested_archive_path"],
}


def norm(value: str) -> str:
    return re.sub(r"\s+", "", value.casefold())


def get_nas_root() -> str:
    con = sqlite3.connect(DB_PATH)
    try:
        row = con.execute(
            "select root_path from libraries where kind='nas' order by id limit 1"
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise RuntimeError("No NAS library root found.")
    return row[0]


def relative_parts(path: str, root: str) -> tuple[str, ...]:
    rel = os.path.relpath(path, root)
    if rel == ".":
        return ()
    return tuple(rel.split(os.sep))


def immediate_counts(path: str) -> tuple[int, int, int]:
    dirs = 0
    files = 0
    total = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        dirs += 1
                    elif entry.is_file(follow_symlinks=False):
                        files += 1
                        total += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    except OSError:
        return 0, 0, 0
    return dirs, files, total


def scan_directories(root: str) -> list[DirectoryInfo]:
    rows: list[DirectoryInfo] = []
    for dirpath, dirnames, _filenames in os.walk(root):
        dirnames.sort()
        parts = relative_parts(dirpath, root)
        child_dirs, file_count, total_bytes = immediate_counts(dirpath)
        rows.append(
            DirectoryInfo(
                path=dirpath,
                relative_path="" if not parts else "\\".join(parts),
                parts=parts,
                depth=len(parts),
                parent=os.path.dirname(dirpath),
                name=os.path.basename(dirpath),
                child_directory_count=child_dirs,
                file_count=file_count,
                total_bytes=total_bytes,
                top_bucket=parts[0] if parts else "root",
            )
        )
    return rows


def write_directory_baseline(rows: list[DirectoryInfo], timestamp: str) -> Path:
    path = REPORTS_ROOT / f"nas-closeout-baseline-{timestamp}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "Path",
                "RelativePath",
                "Depth",
                "Parent",
                "Name",
                "ChildDirectoryCount",
                "FileCount",
                "TotalBytes",
                "TopBucket",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "Path": row.path,
                    "RelativePath": row.relative_path,
                    "Depth": row.depth,
                    "Parent": row.parent,
                    "Name": row.name,
                    "ChildDirectoryCount": row.child_directory_count,
                    "FileCount": row.file_count,
                    "TotalBytes": row.total_bytes,
                    "TopBucket": row.top_bucket,
                }
            )
    return path


def top_bucket_for_path(path: str, root: str) -> str:
    parts = relative_parts(path, root)
    return parts[0] if parts else "root"


def write_series_baseline(root: str, timestamp: str) -> tuple[Path, int]:
    path = REPORTS_ROOT / f"nas-closeout-series-baseline-{timestamp}.csv"
    missing_confirmed = 0
    con = sqlite3.connect(DB_PATH)
    try:
        rows = con.execute(
            "select id, title, status, archive_path from series order by id"
        ).fetchall()
    finally:
        con.close()
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["SeriesId", "Title", "Status", "ArchivePath", "Exists", "TopBucket"],
        )
        writer.writeheader()
        for sid, title, status, archive_path in rows:
            exists = os.path.exists(archive_path)
            if status == "confirmed" and not exists:
                missing_confirmed += 1
            writer.writerow(
                {
                    "SeriesId": sid,
                    "Title": title,
                    "Status": status,
                    "ArchivePath": archive_path,
                    "Exists": exists,
                    "TopBucket": top_bucket_for_path(archive_path, root)
                    if archive_path.startswith(root)
                    else "",
                }
            )
    return path, missing_confirmed


def write_rules(timestamp: str) -> Path:
    path = REPORTS_ROOT / f"nas-closeout-series-rules-{timestamp}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["Bucket", "Canonical", "Alias"])
        writer.writeheader()
        for canonical, aliases in BOUTIQUE_RULES.items():
            for alias in aliases:
                writer.writerow({"Bucket": BOUTIQUE_DIR_NAME, "Canonical": canonical, "Alias": alias})
        for canonical, aliases in ORDINARY_RULES.items():
            for alias in aliases:
                writer.writerow({"Bucket": OTHER_DIR_NAME, "Canonical": canonical, "Alias": alias})
    return path


def alias_match(value: str, rules: dict[str, list[str]]) -> tuple[str, str] | None:
    lowered = norm(value)
    matches: list[tuple[str, str]] = []
    for canonical, aliases in rules.items():
        for alias in aliases:
            if norm(alias) in lowered:
                matches.append((canonical, alias))
    if len({canonical for canonical, _alias in matches}) == 1:
        return matches[0]
    return None


def under(path: str, ancestor: str) -> bool:
    path_n = os.path.normcase(os.path.abspath(path))
    ancestor_n = os.path.normcase(os.path.abspath(ancestor))
    return path_n == ancestor_n or path_n.startswith(ancestor_n + os.sep)


def has_selected_ancestor(path: str, selected: list[str]) -> bool:
    return any(under(path, source) for source in selected)


def target_status(source: str, target: str) -> tuple[str, str]:
    if os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(target)):
        return "keep", "already_at_target"
    if os.path.exists(target):
        return "review_conflict", "target_exists"
    if under(target, source):
        return "review_conflict", "target_inside_source"
    return "move", "target_available"


def strip_noise_for_prefix(name: str) -> str:
    value = re.sub(r"[\[\(（【].*?[\]\)）】]", " ", name)
    value = re.sub(r"\b(?:vol|no|part|episode|ep)\.?\s*\d+.*$", " ", value, flags=re.I)
    value = re.sub(r"\b\d{1,4}\s*[._-].*$", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -_+.")
    return value


def discovered_prefix(name: str) -> str:
    cleaned = strip_noise_for_prefix(name)
    vol_match = re.match(r"^(.{2,80}?)\s+(?:Vol|VOL|vol|NO|No|no)\.?\s*\d+", name)
    if vol_match:
        cleaned = vol_match.group(1)
    for sep in [" - ", "_", " + ", "\u5199\u771f", "\u753b\u518c"]:
        if sep in cleaned:
            cleaned = cleaned.split(sep, 1)[0]
            break
    cleaned = cleaned.strip(" -_+.")
    if len(cleaned) < 2:
        return ""
    if norm(cleaned) in {norm(item) for item in GENERIC_PREFIXES}:
        return ""
    return cleaned


def direct_other_children(rows: list[DirectoryInfo]) -> list[DirectoryInfo]:
    return [row for row in rows if row.parts[:1] == (OTHER_DIR_NAME,) and row.depth == 2]


def is_special_root_path(parts: tuple[str, ...]) -> bool:
    return bool(parts) and parts[0].startswith("_")


def is_joint_collection(name: str) -> bool:
    """Joint sets belong to their own boutique root, not either participant."""
    lowered = norm(name)
    return name.startswith("联名 -") or ("&" in name and "爆机少女喵小吉" in name and ("金鱼" in name or "花音栗子" in name))


def build_move_plan(root: str, rows: list[DirectoryInfo]) -> tuple[list[MoveRow], list[MoveRow]]:
    boutique_root = os.path.join(root, BOUTIQUE_DIR_NAME)
    other_root = os.path.join(root, OTHER_DIR_NAME)
    row_by_path = {row.path: row for row in rows}
    candidates: list[MoveRow] = []
    selected_sources: list[str] = []

    for row in sorted(rows, key=lambda item: item.depth):
        if row.depth == 0 or row.path in {boutique_root, other_root}:
            continue
        if is_special_root_path(row.parts):
            continue
        if any(is_joint_collection(part) for part in row.parts):
            continue
        if has_selected_ancestor(row.path, selected_sources):
            continue
        match = alias_match(row.name, BOUTIQUE_RULES)
        if not match:
            continue
        canonical, alias = match
        canonical_root = os.path.join(boutique_root, canonical)
        if under(row.path, canonical_root):
            action = "keep"
            reason = "already_under_boutique_target"
            target = row.path
            review = "not_required"
        elif row.parts[:1] == (BOUTIQUE_DIR_NAME,):
            action = "review_conflict"
            reason = "under_different_boutique_folder"
            target = os.path.join(canonical_root, row.name)
            review = "required"
        else:
            target = canonical_root if row.name == canonical else os.path.join(canonical_root, row.name)
            action, status_reason = target_status(row.path, target)
            reason = f"boutique_alias;{status_reason}"
            review = "not_required" if action in {"move", "keep"} else "required"
        candidates.append(MoveRow(row.path, target, canonical, alias, action, reason, review))
        if action == "move":
            selected_sources.append(row.path)

    for row in sorted(rows, key=lambda item: item.depth):
        if row.depth == 0 or is_special_root_path(row.parts) or has_selected_ancestor(row.path, selected_sources):
            continue
        if any(is_joint_collection(part) for part in row.parts):
            continue
        match = alias_match(row.name, ORDINARY_RULES)
        if not match:
            continue
        canonical, alias = match
        canonical_root = os.path.join(other_root, canonical)
        if under(row.path, canonical_root):
            candidates.append(
                MoveRow(
                    row.path,
                    row.path,
                    canonical,
                    alias,
                    "keep",
                    "already_under_ordinary_target",
                    "not_required",
                )
            )
            continue
        target = canonical_root if row.name == canonical else os.path.join(canonical_root, row.name)
        action, status_reason = target_status(row.path, target)
        review = "required" if row.parts[:1] == (BOUTIQUE_DIR_NAME,) or action == "review_conflict" else "not_required"
        reason = "ordinary_alias;" + status_reason
        if row.parts[:1] == (BOUTIQUE_DIR_NAME,):
            action = "review_conflict"
            reason = "ordinary_alias_under_boutique"
        candidates.append(MoveRow(row.path, target, canonical, alias, action, reason, review))
        if action == "move" and review == "not_required":
            selected_sources.append(row.path)

    used_sources = {row.source_path for row in candidates}
    groups: dict[str, list[DirectoryInfo]] = defaultdict(list)
    for row in direct_other_children(rows):
        if is_special_root_path(row.parts) or row.path in used_sources or row.child_directory_count >= 2:
            continue
        prefix = discovered_prefix(row.name)
        if prefix:
            groups[prefix].append(row)

    uncertain: list[MoveRow] = []
    for prefix, members in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0].casefold())):
        if len(members) < 2:
            continue
        target_root = os.path.join(other_root, prefix)
        deterministic = len(members) >= 3
        for member in members:
            target = os.path.join(target_root, member.name)
            action, status_reason = target_status(member.path, target)
            generic = norm(prefix) in {norm(item) for item in GENERIC_PREFIXES}
            if not deterministic or generic or action == "review_conflict":
                uncertain.append(
                    MoveRow(
                        member.path,
                        target,
                        prefix,
                        prefix,
                        "review",
                        f"discovered_prefix_count={len(members)};{status_reason}",
                        "required",
                    )
                )
            else:
                candidates.append(
                    MoveRow(
                        member.path,
                        target,
                        prefix,
                        prefix,
                        "move",
                        f"discovered_prefix_count={len(members)};{status_reason}",
                        "not_required",
                    )
                )

    return candidates, uncertain


def write_move_rows(path: Path, rows: list[MoveRow]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["SourcePath", "TargetPath", "Rule", "Alias", "Action", "Reason", "ReviewStatus"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "SourcePath": row.source_path,
                    "TargetPath": row.target_path,
                    "Rule": row.rule,
                    "Alias": row.alias,
                    "Action": row.action,
                    "Reason": row.reason,
                    "ReviewStatus": row.review_status,
                }
            )
    return path


def should_execute_row(row: MoveRow, auto_policy: str) -> bool:
    if row.action == "move" and row.review_status == "not_required":
        return True
    if auto_policy == "full" and row.action == "review":
        return True
    return False


def directory_is_empty(path: str) -> bool:
    try:
        if not os.path.isdir(path):
            return False
        with os.scandir(path) as entries:
            return not any(entries)
    except OSError:
        return False


def move_directory_without_overwrite(source: str, target: str) -> tuple[str, str, str]:
    source_abs = os.path.abspath(source)
    target_abs = os.path.abspath(target)
    if os.path.normcase(source_abs) == os.path.normcase(target_abs):
        return "kept", target, ""
    if not os.path.isdir(source):
        return "source_missing", target, ""
    if under(target, source):
        return "blocked_target_inside_source", target, ""
    if os.path.exists(target):
        if directory_is_empty(target):
            os.rmdir(target)
        else:
            return "collision", target, ""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.rename(source, target)
    return "moved", target, ""


def sqlite_table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in con.execute(f"pragma table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def sqlite_tables(con: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in con.execute("select name from sqlite_master where type='table'").fetchall()
    }


def replace_path_prefix(value: str | None, old_prefix: str, new_prefix: str) -> str | None:
    if value is None:
        return None
    old_norm = old_prefix.replace("/", "\\")
    new_norm = new_prefix.replace("/", "\\")
    current = value.replace("/", "\\")
    if current == old_norm:
        return new_norm
    prefix = old_norm + "\\"
    if current.startswith(prefix):
        return new_norm + current[len(old_norm) :]
    return None


def update_database_paths(successful_moves: list[tuple[str, str]], timestamp: str) -> Path:
    report_path = REPORTS_ROOT / f"nas-closeout-db-updates-{timestamp}.csv"
    rows: list[dict[str, object]] = []
    con = sqlite3.connect(DB_PATH)
    try:
        tables = sqlite_tables(con)
        cur = con.cursor()
        cur.execute("begin")
        for table, columns in PATH_COLUMNS.items():
            if table not in tables:
                continue
            table_columns = sqlite_table_columns(con, table)
            existing_columns = [column for column in columns if column in table_columns]
            if not existing_columns:
                continue
            id_column = "id" if "id" in table_columns else "rowid"
            has_updated_at = "updated_at" in table_columns
            select_columns = ", ".join([id_column, *existing_columns])
            for result_row in cur.execute(f"select {select_columns} from {table}").fetchall():
                row_id = result_row[0]
                values = dict(zip(existing_columns, result_row[1:]))
                updates: dict[str, str] = {}
                for column, value in values.items():
                    for old_prefix, new_prefix in successful_moves:
                        replacement = replace_path_prefix(value, old_prefix, new_prefix)
                        if replacement is not None:
                            updates[column] = replacement
                            rows.append(
                                {
                                    "OldPrefix": old_prefix,
                                    "NewPrefix": new_prefix,
                                    "Table": table,
                                    "Column": column,
                                    "RowId": row_id,
                                    "OldValue": value,
                                    "NewValue": replacement,
                                }
                            )
                            break
                if not updates:
                    continue
                if table == "series" and "archive_path" in updates:
                    can_update = displace_non_confirmed_series_conflict(
                        con,
                        row_id,
                        updates["archive_path"],
                        rows,
                    )
                    if not can_update:
                        continue
                assignments = [f"{column}=?" for column in updates]
                params: list[object] = list(updates.values())
                if has_updated_at:
                    assignments.append("updated_at=CURRENT_TIMESTAMP")
                params.append(row_id)
                cur.execute(
                    f"update {table} set {', '.join(assignments)} where {id_column}=?",
                    params,
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
                "OldPrefix",
                "NewPrefix",
                "Table",
                "Column",
                "RowId",
                "OldValue",
                "NewValue",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return report_path


def unique_displaced_archive_path(con: sqlite3.Connection, base_path: str, row_id: object) -> str:
    candidate = f"{base_path}__duplicate_series_{row_id}"
    existing = con.execute(
        "select 1 from series where archive_path=? limit 1",
        (candidate,),
    ).fetchone()
    if not existing:
        return candidate
    for index in range(1, 10_000):
        numbered = f"{candidate}_{index}"
        existing = con.execute(
            "select 1 from series where archive_path=? limit 1",
            (numbered,),
        ).fetchone()
        if not existing:
            return numbered
    raise RuntimeError(f"Unable to create unique displaced archive path for {base_path}")


def displace_non_confirmed_series_conflict(
    con: sqlite3.Connection,
    row_id: object,
    replacement: str,
    rows: list[dict[str, object]],
) -> bool:
    conflict = con.execute(
        "select id, title, status, archive_path from series where archive_path=? and id<>?",
        (replacement, row_id),
    ).fetchone()
    if not conflict:
        return True
    conflict_id, _title, status, old_archive_path = conflict
    if status == "confirmed":
        rows.append(
            {
                "OldPrefix": old_archive_path,
                "NewPrefix": replacement,
                "Table": "series",
                "Column": "archive_path",
                "RowId": row_id,
                "OldValue": old_archive_path,
                "NewValue": "skipped_confirmed_conflict",
            }
        )
        return False
    displaced_path = unique_displaced_archive_path(con, replacement, conflict_id)
    con.execute(
        "update series set archive_path=?, updated_at=CURRENT_TIMESTAMP where id=?",
        (displaced_path, conflict_id),
    )
    rows.append(
        {
            "OldPrefix": old_archive_path,
            "NewPrefix": displaced_path,
            "Table": "series",
            "Column": "archive_path",
            "RowId": conflict_id,
            "OldValue": old_archive_path,
            "NewValue": displaced_path,
        }
    )
    return True


def write_execution_results(timestamp: str, rows: list[ExecutionResult]) -> Path:
    path = REPORTS_ROOT / f"nas-closeout-move-result-{timestamp}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "SourcePath",
                "TargetPath",
                "Rule",
                "Alias",
                "Action",
                "Reason",
                "ReviewStatus",
                "Result",
                "FinalTargetPath",
                "Error",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "SourcePath": row.source_path,
                    "TargetPath": row.target_path,
                    "Rule": row.rule,
                    "Alias": row.alias,
                    "Action": row.action,
                    "Reason": row.reason,
                    "ReviewStatus": row.review_status,
                    "Result": row.result,
                    "FinalTargetPath": row.final_target_path,
                    "Error": row.error,
                }
            )
    return path


def execute_move_rows(
    move_rows: list[MoveRow],
    uncertain_rows: list[MoveRow],
    timestamp: str,
    auto_policy: str,
) -> tuple[Path, Path, list[ExecutionResult]]:
    if auto_policy not in {"conservative", "full"}:
        raise ValueError(f"Unsupported auto policy: {auto_policy}")

    ordered_rows = [*move_rows, *uncertain_rows]
    results: list[ExecutionResult] = []
    successful_moves: list[tuple[str, str]] = []
    for row in sorted(ordered_rows, key=lambda item: item.source_path.count(os.sep), reverse=True):
        result = "skipped"
        final_target = row.target_path
        error = ""
        if row.action == "keep":
            result = "kept"
        elif should_execute_row(row, auto_policy):
            try:
                result, final_target, error = move_directory_without_overwrite(
                    row.source_path, row.target_path
                )
                if result == "moved":
                    successful_moves.append((row.source_path, final_target))
            except Exception as exc:
                result = "error"
                error = repr(exc)
        results.append(
            ExecutionResult(
                source_path=row.source_path,
                target_path=row.target_path,
                rule=row.rule,
                alias=row.alias,
                action=row.action,
                reason=row.reason,
                review_status=row.review_status,
                result=result,
                final_target_path=final_target,
                error=error,
            )
        )

    result_path = write_execution_results(timestamp, results)
    db_report = update_database_paths(successful_moves, timestamp)
    return result_path, db_report, results


def write_junk_report(root: str, timestamp: str) -> tuple[Path, int]:
    path = REPORTS_ROOT / f"nas-closeout-junk-files-{timestamp}.csv"
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["Path", "RelativePath", "FileName", "Status"])
        writer.writeheader()
        for dirpath, dirnames, filenames in os.walk(root):
            if is_special_root_path(relative_parts(dirpath, root)):
                dirnames[:] = []
                continue
            for name in filenames:
                if name in JUNK_EXACT_NAMES:
                    count += 1
                    full = os.path.join(dirpath, name)
                    writer.writerow(
                        {
                            "Path": full,
                            "RelativePath": os.path.relpath(full, root),
                            "FileName": name,
                            "Status": "exact_junk_remaining",
                        }
                    )
    return path, count


def delete_exact_junk_files(root: str, timestamp: str) -> tuple[Path, list[dict[str, str]]]:
    path = REPORTS_ROOT / f"nas-closeout-junk-delete-result-{timestamp}.csv"
    rows: list[dict[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        if is_special_root_path(relative_parts(dirpath, root)):
            dirnames[:] = []
            continue
        for name in filenames:
            if name not in JUNK_EXACT_NAMES:
                continue
            full = os.path.join(dirpath, name)
            result = "skipped"
            error = ""
            try:
                if os.path.isfile(full):
                    os.remove(full)
                    result = "deleted"
                else:
                    result = "missing"
            except Exception as exc:
                result = "error"
                error = repr(exc)
            rows.append(
                {
                    "Path": full,
                    "RelativePath": os.path.relpath(full, root),
                    "FileName": name,
                    "Result": result,
                    "Error": error,
                }
            )
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["Path", "RelativePath", "FileName", "Result", "Error"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path, rows


def write_summary(
    timestamp: str,
    directory_count: int,
    missing_confirmed: int,
    move_rows: list[MoveRow],
    uncertain_rows: list[MoveRow],
    junk_remaining: int,
    paths: list[Path],
) -> Path:
    path = REPORTS_ROOT / f"nas-closeout-final-summary-{timestamp}.txt"
    action_counts = Counter(row.action for row in move_rows)
    rule_counts = Counter(row.rule for row in move_rows if row.action == "move")
    uncertain_groups = Counter(row.rule for row in uncertain_rows)
    with path.open("w", encoding="utf-8") as file:
        file.write(f"Directory count: {directory_count}\n")
        file.write(f"Move rows: {len(move_rows)}\n")
        file.write(f"Move action counts: {dict(action_counts)}\n")
        file.write(f"Move rule counts: {dict(rule_counts)}\n")
        file.write(f"Uncertain rows: {len(uncertain_rows)}\n")
        file.write(f"Uncertain groups: {len(uncertain_groups)}\n")
        file.write(f"Confirmed series missing: {missing_confirmed}\n")
        file.write(f"Exact junk remaining: {junk_remaining}\n")
        file.write("Reports:\n")
        for report_path in paths:
            file.write(f"- {report_path}\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Generate reports only.")
    mode.add_argument("--execute", action="store_true", help="Generate reports and execute safe moves.")
    parser.add_argument(
        "--auto-policy",
        choices=["conservative", "full"],
        default="conservative",
        help="Execution policy. full also executes inferred review rows unless blocked.",
    )
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    root = get_nas_root()
    if not os.path.isdir(root):
        raise RuntimeError(f"NAS root does not exist: {root}")

    directories = scan_directories(root)
    baseline_path = write_directory_baseline(directories, timestamp)
    series_path, missing_confirmed = write_series_baseline(root, timestamp)
    rules_path = write_rules(timestamp)
    move_rows, uncertain_rows = build_move_plan(root, directories)
    move_path = write_move_rows(REPORTS_ROOT / f"nas-closeout-move-plan-{timestamp}.csv", move_rows)
    uncertain_path = write_move_rows(
        REPORTS_ROOT / f"nas-closeout-uncertain-{timestamp}.csv", uncertain_rows
    )
    junk_path, junk_remaining = write_junk_report(root, timestamp)
    paths = [baseline_path, series_path, rules_path, move_path, uncertain_path, junk_path]
    if args.execute:
        if missing_confirmed:
            raise RuntimeError(
                f"Refusing to execute because confirmed series paths are missing: {missing_confirmed}"
            )
        result_path, db_report, _results = execute_move_rows(
            move_rows=move_rows,
            uncertain_rows=uncertain_rows,
            timestamp=timestamp,
            auto_policy=args.auto_policy,
        )
        deleted_junk_path, _deleted_junk_rows = delete_exact_junk_files(root, timestamp)
        paths.extend([result_path, db_report, deleted_junk_path])
        junk_path, junk_remaining = write_junk_report(root, timestamp)
        paths.append(junk_path)
    summary_path = write_summary(
        timestamp,
        len(directories),
        missing_confirmed,
        move_rows,
        uncertain_rows,
        junk_remaining,
        paths,
    )
    paths.append(summary_path)

    print(f"timestamp={timestamp}")
    print(f"directories={len(directories)}")
    print(f"missing_confirmed={missing_confirmed}")
    print(f"move_rows={len(move_rows)}")
    print(f"move_actions={dict(Counter(row.action for row in move_rows))}")
    print(f"uncertain_rows={len(uncertain_rows)}")
    print(f"uncertain_groups={len(set(row.rule for row in uncertain_rows))}")
    print(f"junk_remaining={junk_remaining}")
    for report_path in paths:
        print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
