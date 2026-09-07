from __future__ import annotations

import argparse
import csv
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nas_collection_tier_cleanup import (
    BOUTIQUE_DIR_NAME,
    OTHER_DIR_NAME,
    PRIORITY_SERIES,
    classify_priority,
    get_nas_root,
    unique_path,
    update_database,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_ROOT = PROJECT_ROOT / "data" / "reports"


@dataclass(frozen=True)
class RecursivePlan:
    source: str
    destination: str
    canonical_series: str
    source_bucket: str
    action: str
    reason: str


def relative_parts(path: str, root: str) -> list[str]:
    rel = os.path.relpath(path, root)
    if rel == ".":
        return []
    return rel.split(os.sep)


def top_bucket_for(path: str, other_root: str) -> str:
    parts = relative_parts(path, other_root)
    return parts[0] if parts else ""


def build_recursive_plan(root: str) -> list[RecursivePlan]:
    boutique_root = os.path.join(root, BOUTIQUE_DIR_NAME)
    other_root = os.path.join(root, OTHER_DIR_NAME)
    if not os.path.isdir(other_root):
        return []

    candidates: list[tuple[str, str, int]] = []
    for dirpath, dirnames, filenames in os.walk(other_root):
        if dirpath == other_root:
            continue
        canonical = classify_priority(os.path.basename(dirpath))
        if not canonical:
            continue
        depth = len(relative_parts(dirpath, other_root))
        candidates.append((dirpath, canonical, depth))

    # Move highest matching ancestors first and suppress their descendants.
    selected: list[tuple[str, str]] = []
    selected_sources: list[str] = []
    for source, canonical, _depth in sorted(candidates, key=lambda item: item[2]):
        source_prefix = source + os.sep
        if any(source == existing or source.startswith(existing + os.sep) for existing in selected_sources):
            continue
        selected.append((source, canonical))
        selected_sources.append(source)

    plans: list[RecursivePlan] = []
    for source, canonical in selected:
        bucket = top_bucket_for(source, other_root)
        name = os.path.basename(source)
        if bucket == name:
            destination = os.path.join(boutique_root, canonical, name)
            reason = "other_top_priority_match"
        else:
            destination = os.path.join(boutique_root, canonical, bucket, name)
            reason = f"recursive_priority_match;bucket={bucket}"
        action = "planned_unique_rename" if os.path.exists(destination) else "planned"
        plans.append(RecursivePlan(source, destination, canonical, bucket, action, reason))
    return plans


def write_plan(plans: list[RecursivePlan], timestamp: str) -> Path:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    path = REPORTS_ROOT / f"nas-recursive-boutique-regroup-plan-{timestamp}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "Source",
                "Destination",
                "CanonicalSeries",
                "SourceBucket",
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
                    "CanonicalSeries": plan.canonical_series,
                    "SourceBucket": plan.source_bucket,
                    "Action": plan.action,
                    "Reason": plan.reason,
                }
            )
    return path


def execute_plan(plans: list[RecursivePlan], timestamp: str) -> tuple[Path, Path]:
    result_path = REPORTS_ROOT / f"nas-recursive-boutique-regroup-result-{timestamp}.csv"
    rows: list[dict[str, str]] = []
    successful: list[tuple[str, str, str]] = []

    for plan in sorted(plans, key=lambda item: item.source.count(os.sep), reverse=True):
        result = "skipped_plan"
        error = ""
        final_destination = plan.destination
        try:
            if not os.path.isdir(plan.source):
                result = "skipped_source_missing"
            else:
                final_destination = unique_path(plan.destination)
                os.makedirs(os.path.dirname(final_destination), exist_ok=True)
                os.rename(plan.source, final_destination)
                successful.append((plan.source, final_destination, "recursive_boutique_regroup"))
                result = "moved" if final_destination == plan.destination else "moved_renamed_conflict"
        except Exception as exc:
            result = "error"
            error = repr(exc)
        rows.append(
            {
                "Source": plan.source,
                "Destination": plan.destination,
                "FinalDestination": final_destination,
                "CanonicalSeries": plan.canonical_series,
                "SourceBucket": plan.source_bucket,
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
                "FinalDestination",
                "CanonicalSeries",
                "SourceBucket",
                "PlanAction",
                "ResultAction",
                "Reason",
                "Error",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    db_report = update_database(successful, timestamp)
    return result_path, db_report


def print_summary(plans: list[RecursivePlan], paths: list[Path]) -> None:
    print("plans", len(plans), dict(Counter(plan.action for plan in plans)))
    print("series", dict(Counter(plan.canonical_series for plan in plans)))
    print("buckets", dict(Counter(plan.source_bucket for plan in plans).most_common(20)))
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
    plans = build_recursive_plan(root)
    plan_path = write_plan(plans, timestamp)
    paths = [plan_path]
    if args.execute:
        paths.extend(execute_plan(plans, timestamp))
    print_summary(plans, paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
