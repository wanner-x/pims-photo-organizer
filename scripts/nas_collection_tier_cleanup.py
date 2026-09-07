from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "pims.db"
REPORTS_ROOT = PROJECT_ROOT / "data" / "reports"
BOUTIQUE_DIR_NAME = "精品"
OTHER_DIR_NAME = "其它画册"

PRIORITY_SERIES = [
    "森萝财团",
    "紧急企划",
    "少女秩序",
    "橙子喵",
    "村上西瓜",
    "金鱼kinngyo（花音栗子）",
    "素人渔夫",
    "流欲XX工坊",
    "萌量守恒",
    "稚乖画册",
]

PRIORITY_ALIASES = {
    "金鱼kinngyo（花音栗子）": [
        "金鱼kinngyo（花音栗子）",
        "金鱼kinngyo (花音栗子)",
        "金鱼kinngyo",
        "花音栗子",
    ],
    "流欲XX工坊": ["流欲XX工坊", "流欲xx工坊"],
}

SYSTEM_ROOTS = {BOUTIQUE_DIR_NAME, OTHER_DIR_NAME, "其他画册"}
GENERIC_SERIES_ROOTS = {
    "1",
    "GIF",
    "Pic",
    "Video",
    "图片",
    "视频",
    "有料",
    "無料",
    "有料&无料",
    "R15",
    "R17",
    "R18",
}

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


@dataclass(frozen=True)
class MovePlan:
    source: str
    destination: str
    category: str
    mode: str
    canonical_series: str
    action: str
    reason: str


def norm_key(value: str) -> str:
    return value.casefold().replace(" ", "")


def path_join(*parts: str) -> str:
    result = parts[0]
    for part in parts[1:]:
        result = os.path.join(result, part)
    return result


def unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    parent = os.path.dirname(path)
    name = os.path.basename(path)
    stem, suffix = os.path.splitext(name)
    for index in range(1, 10_000):
        candidate = os.path.join(parent, f"{stem}-{index}{suffix}")
        if not os.path.exists(candidate):
            return candidate
    raise RuntimeError(f"Unable to find unique path for {path}")


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


def list_top_dirs(root: str) -> list[str]:
    return sorted(
        name for name in os.listdir(root) if os.path.isdir(os.path.join(root, name))
    )


def classify_priority(name: str) -> str | None:
    lowered = norm_key(name)
    for series in PRIORITY_SERIES:
        aliases = PRIORITY_ALIASES.get(series, [series])
        if any(norm_key(alias) in lowered for alias in aliases):
            return series
    return None


def is_priority_series_folder(name: str, canonical: str) -> bool:
    aliases = PRIORITY_ALIASES.get(canonical, [canonical])
    return any(norm_key(name) == norm_key(alias) for alias in aliases)


def child_counts(path: str) -> tuple[int, int]:
    dirs = 0
    files = 0
    for child in os.listdir(path):
        child_path = os.path.join(path, child)
        if os.path.isdir(child_path):
            dirs += 1
        elif os.path.isfile(child_path):
            files += 1
    return dirs, files


def build_plan(root: str) -> list[MovePlan]:
    top_dirs = list_top_dirs(root)
    plans: list[MovePlan] = []
    boutique_root = os.path.join(root, BOUTIQUE_DIR_NAME)
    other_root = os.path.join(root, OTHER_DIR_NAME)

    for name in top_dirs:
        if name in SYSTEM_ROOTS:
            continue

        source = os.path.join(root, name)
        priority = classify_priority(name)
        if priority:
            if name == priority:
                destination = os.path.join(boutique_root, priority)
                mode = "priority_series_folder"
            else:
                destination = os.path.join(boutique_root, priority, name)
                mode = "priority_matched_set"
            action = "planned"
            reason = "priority_series_match"
            if os.path.exists(destination):
                action = "skip_destination_exists"
            plans.append(
                MovePlan(source, destination, "精品", mode, priority, action, reason)
            )
            continue

        dirs, files = child_counts(source)
        if dirs == 0 and files == 0:
            plans.append(
                MovePlan(
                    source,
                    "",
                    "cleanup",
                    "remove_empty_top_directory",
                    "",
                    "planned",
                    "empty_top_directory",
                )
            )
            continue

        if dirs == 1 and files == 0:
            child_name = next(
                child
                for child in os.listdir(source)
                if os.path.isdir(os.path.join(source, child))
            )
            child_source = os.path.join(source, child_name)
            move_source = child_source
            child_priority = classify_priority(child_name)
            if child_priority:
                destination = os.path.join(boutique_root, child_priority, child_name)
                mode = "priority_matched_set"
                reason = "single_child_priority_match"
                category = "精品"
                canonical = child_priority
            else:
                destination = os.path.join(other_root, child_name)
                mode = "other_single_flatten"
                reason = "single_child_directory"
                category = "其它画册"
                canonical = ""
            action = "planned"
            if os.path.exists(destination):
                fallback_destination = os.path.join(other_root, name)
                if category == "其它画册" and not os.path.exists(fallback_destination):
                    move_source = source
                    destination = fallback_destination
                    mode = "other_single_wrapper_fallback"
                    reason = "single_child_destination_exists_fallback"
                else:
                    action = "skip_destination_exists"
            plans.append(
                MovePlan(move_source, destination, category, mode, canonical, action, reason)
            )
            continue

        destination = os.path.join(other_root, name)
        mode = "other_series_folder" if dirs >= 2 else "other_mixed_folder"
        reason = f"top_dirs={dirs};top_files={files}"
        action = "planned"
        if os.path.exists(destination):
            action = "skip_destination_exists"
        plans.append(MovePlan(source, destination, "其它画册", mode, "", action, reason))

    planned_sources = {plan.source for plan in plans}
    if os.path.isdir(other_root):
        other_names = list_top_dirs(other_root)
        other_set = set(other_names)
        for name in other_names:
            source = os.path.join(other_root, name)
            if source in planned_sources:
                continue
            priority = classify_priority(name)
            if not priority:
                continue
            if is_priority_series_folder(name, priority):
                destination = os.path.join(boutique_root, priority)
                mode = "priority_series_folder"
            else:
                destination = os.path.join(boutique_root, priority, name)
                mode = "priority_matched_set"
            action = "planned_merge" if os.path.exists(destination) else "planned"
            plans.append(
                MovePlan(
                    source,
                    destination,
                    "精品",
                    mode,
                    priority,
                    action,
                    "other_root_priority_match",
                )
            )
            planned_sources.add(source)

        series_roots = [
            name
            for name in other_names
            if name not in GENERIC_SERIES_ROOTS
            and os.path.join(other_root, name) not in planned_sources
        ]
        for name in other_names:
            source = os.path.join(other_root, name)
            if source in planned_sources:
                continue
            matched = None
            for base in sorted(series_roots, key=len, reverse=True):
                if base == name or len(base) < 3:
                    continue
                prefixes = (
                    base + " ",
                    base + " -",
                    base + " –",
                    base + "-",
                    base + "(",
                    base + "（",
                )
                if name.startswith(prefixes):
                    matched = base
                    break
            if not matched:
                continue
            destination = os.path.join(other_root, matched, name)
            action = "planned_merge" if os.path.exists(destination) else "planned"
            plans.append(
                MovePlan(
                    source,
                    destination,
                    "其它画册",
                    "other_existing_series_match",
                    "",
                    action,
                    f"matched_existing_series={matched}",
                )
            )
            planned_sources.add(source)

    return plans


def write_plan(plans: list[MovePlan], timestamp: str) -> Path:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    path = REPORTS_ROOT / f"nas-collection-tier-plan-{timestamp}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "Source",
                "Destination",
                "Category",
                "Mode",
                "CanonicalSeries",
                "Action",
                "Reason",
            ],
        )
        writer.writeheader()
        for plan in plans:
            writer.writerow(
                {
                    "Source": plan.source,
                    "Destination": plan.destination,
                    "Category": plan.category,
                    "Mode": plan.mode,
                    "CanonicalSeries": plan.canonical_series,
                    "Action": plan.action,
                    "Reason": plan.reason,
                }
            )
    return path


def replace_prefix(value: str, old: str, new: str) -> str | None:
    if value == old:
        return new
    prefix = old + "\\"
    if value.startswith(prefix):
        return new + value[len(old) :]
    return None


def update_database(successful_moves: list[tuple[str, str, str]], timestamp: str) -> Path:
    report_path = REPORTS_ROOT / f"nas-collection-tier-db-updates-{timestamp}.csv"
    rows: list[dict[str, object]] = []
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        cur.execute("begin")
        for old, new, mode in successful_moves:
            old_prefix = old.replace("/", "\\")
            new_prefix = new.replace("/", "\\")
            prefixes = [(old_prefix, new_prefix, "source_prefix")]

            # Flattening a single-set wrapper can leave a series row pointing to
            # the old wrapper. Map exact wrapper rows to the flattened set path.
            if mode == "other_single_flatten":
                old_parent = os.path.dirname(old_prefix)
                prefixes.append((old_parent, new_prefix, "single_wrapper_exact"))

            for table, columns in PATH_COLUMNS.items():
                for column in columns:
                    for source_prefix, destination_prefix, update_mode in prefixes:
                        count = cur.execute(
                            f"select count(*) from {table} where {column} = ? or {column} like ?",
                            (source_prefix, source_prefix + "\\%"),
                        ).fetchone()[0]
                        if not count:
                            continue
                        # For wrapper exact updates, descendants are intentionally
                        # excluded because child paths are handled by source_prefix.
                        if update_mode == "single_wrapper_exact":
                            exact_count = cur.execute(
                                f"select count(*) from {table} where {column} = ?",
                                (source_prefix,),
                            ).fetchone()[0]
                            if not exact_count:
                                continue
                            cur.execute(
                                f"update {table} set {column} = ? where {column} = ?",
                                (destination_prefix, source_prefix),
                            )
                            count = exact_count
                        else:
                            cur.execute(
                                f"update {table} set {column} = ? || substr({column}, ?) "
                                f"where {column} = ? or {column} like ?",
                                (
                                    destination_prefix,
                                    len(source_prefix) + 1,
                                    source_prefix,
                                    source_prefix + "\\%",
                                ),
                            )
                        rows.append(
                            {
                                "OldPrefix": source_prefix,
                                "NewPrefix": destination_prefix,
                                "Mode": mode,
                                "UpdateMode": update_mode,
                                "Table": table,
                                "Column": column,
                                "Rows": count,
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
                "OldPrefix",
                "NewPrefix",
                "Mode",
                "UpdateMode",
                "Table",
                "Column",
                "Rows",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return report_path


def execute_plan(plans: list[MovePlan], timestamp: str) -> tuple[Path, Path]:
    result_path = REPORTS_ROOT / f"nas-collection-tier-result-{timestamp}.csv"
    rows: list[dict[str, str]] = []
    successful_moves: list[tuple[str, str, str]] = []
    mode_order = {
        "priority_series_folder": 0,
        "priority_matched_set": 1,
        "other_series_folder": 2,
        "other_mixed_folder": 3,
        "other_single_wrapper_fallback": 4,
        "other_single_flatten": 5,
        "remove_empty_top_directory": 6,
    }

    for plan in sorted(plans, key=lambda item: (mode_order.get(item.mode, 99), item.source)):
        result = "skipped_plan"
        error = ""
        if plan.action in {"planned", "planned_merge"}:
            try:
                if plan.mode == "remove_empty_top_directory":
                    if os.path.isdir(plan.source):
                        os.rmdir(plan.source)
                        result = "removed_empty_dir"
                    else:
                        result = "skipped_source_missing"
                elif not os.path.isdir(plan.source):
                    result = "skipped_source_missing"
                elif os.path.exists(plan.destination):
                    if not os.path.isdir(plan.destination):
                        result = "skipped_destination_exists"
                    else:
                        moved_children = 0
                        renamed_children = 0
                        for child in sorted(os.listdir(plan.source)):
                            old_child = os.path.join(plan.source, child)
                            new_child = os.path.join(plan.destination, child)
                            if os.path.exists(new_child):
                                new_child = unique_path(new_child)
                                renamed_children += 1
                            os.rename(old_child, new_child)
                            successful_moves.append(
                                (old_child, new_child, "merge_child_into_existing_series")
                            )
                            moved_children += 1
                        try:
                            os.rmdir(plan.source)
                        except OSError:
                            pass
                        result = (
                            "merged_children"
                            if moved_children
                            else "skipped_destination_exists"
                        )
                        error = f"moved_children={moved_children};renamed_children={renamed_children}"
                else:
                    os.makedirs(os.path.dirname(plan.destination), exist_ok=True)
                    os.rename(plan.source, plan.destination)
                    result = "moved"
                    successful_moves.append((plan.source, plan.destination, plan.mode))
                    if plan.mode in {"other_single_flatten", "priority_matched_set"}:
                        old_wrapper = os.path.dirname(plan.source)
                        try:
                            os.rmdir(old_wrapper)
                        except OSError:
                            pass
            except Exception as exc:
                result = "error"
                error = repr(exc)
        rows.append(
            {
                "Source": plan.source,
                "Destination": plan.destination,
                "Category": plan.category,
                "Mode": plan.mode,
                "CanonicalSeries": plan.canonical_series,
                "PlanAction": plan.action,
                "ResultAction": result,
                "Reason": plan.reason,
                "Error": error,
            }
        )

    with result_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "Source",
                "Destination",
                "Category",
                "Mode",
                "CanonicalSeries",
                "PlanAction",
                "ResultAction",
                "Reason",
                "Error",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    db_report = update_database(successful_moves, timestamp)
    return result_path, db_report


def print_summary(plans: list[MovePlan], paths: list[Path]) -> None:
    print("plans", len(plans), dict(Counter(plan.action for plan in plans)))
    print("by_mode", dict(Counter(plan.mode for plan in plans if plan.action == "planned")))
    print(
        "priority",
        dict(Counter(plan.canonical_series for plan in plans if plan.canonical_series)),
    )
    for path in paths:
        print("report", path)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    root = get_nas_root()
    if not os.path.isdir(root):
        raise RuntimeError(f"NAS root does not exist: {root}")
    plans = build_plan(root)
    plan_path = write_plan(plans, timestamp)
    paths = [plan_path]
    if args.execute:
        paths.extend(execute_plan(plans, timestamp))
    print_summary(plans, paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
