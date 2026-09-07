from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "pims.db"
REPORT_ROOT = PROJECT_ROOT / "data" / "reports"


@dataclass
class LogRow:
    action: str
    source: str
    target: str
    result: str
    detail: str = ""


def md5(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    stem, suffix = os.path.splitext(path)
    index = 1
    while True:
        candidate = f"{stem} [保留-{index}]{suffix}"
        if not os.path.exists(candidate):
            return candidate
        index += 1


def inside(path: str, root: str) -> bool:
    p = os.path.normcase(os.path.abspath(path))
    r = os.path.normcase(os.path.abspath(root))
    return p == r or p.startswith(r + os.sep)


class Cleaner:
    def __init__(self, root: str, execute: bool):
        self.root = root.rstrip("\\/")
        self.execute = execute
        self.logs: list[LogRow] = []
        self.moves: list[tuple[str, str]] = []

    def log(self, action: str, source: str, target: str, result: str, detail: str = "") -> None:
        self.logs.append(LogRow(action, source, target, result, detail))

    def ensure_safe(self, *paths: str) -> None:
        for path in paths:
            if not inside(path, self.root):
                raise RuntimeError(f"Path outside NAS root: {path}")

    def move_file(self, source: str, target: str, action: str) -> None:
        self.ensure_safe(source, target)
        if not os.path.isfile(source):
            self.log(action, source, target, "source_missing")
            return
        final = target
        if os.path.isfile(target):
            if os.path.getsize(source) == os.path.getsize(target) and md5(source) == md5(target):
                if self.execute:
                    os.remove(source)
                self.log(action, source, target, "deleted_exact_duplicate")
                return
            final = unique_path(target)
        elif os.path.exists(target):
            final = unique_path(target)
        if self.execute:
            os.makedirs(os.path.dirname(final), exist_ok=True)
            shutil.move(source, final)
        self.moves.append((source, final))
        self.log(action, source, final, "moved" if self.execute else "planned")

    def merge_dir(self, source: str, target: str, action: str) -> None:
        self.ensure_safe(source, target)
        if not os.path.isdir(source):
            self.log(action, source, target, "source_missing")
            return
        if os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(target)):
            return
        if not os.path.exists(target):
            if self.execute:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.rename(source, target)
            self.moves.append((source, target))
            self.log(action, source, target, "moved" if self.execute else "planned")
            return
        if not os.path.isdir(target):
            final = unique_path(target)
            if self.execute:
                os.rename(source, final)
            self.moves.append((source, final))
            self.log(action, source, final, "moved_conflict" if self.execute else "planned_conflict")
            return
        for name in sorted(os.listdir(source)):
            old = os.path.join(source, name)
            new = os.path.join(target, name)
            if os.path.isdir(old):
                self.merge_dir(old, new, action)
            else:
                self.move_file(old, new, action)
        if self.execute:
            try:
                os.rmdir(source)
            except OSError:
                pass

    def restore_quarantine(self) -> None:
        quarantine = os.path.join(self.root, "_待复核_重复与垃圾_勿删")
        if not os.path.isdir(quarantine):
            return
        delete_groups = {"junk_files", "junk_dirs"}
        restore_groups = {
            "visual_duplicate_dirs",
            "duplicate_dirs",
            "重复文件",
            "incomplete_album_shells",
        }
        for group in sorted(os.listdir(quarantine)):
            group_path = os.path.join(quarantine, group)
            if not os.path.isdir(group_path):
                continue
            if group in delete_groups:
                file_count = sum(len(files) for _, _, files in os.walk(group_path))
                if self.execute:
                    shutil.rmtree(group_path)
                self.log("remove_quarantined_junk", group_path, "", "removed" if self.execute else "planned", f"files={file_count}")
                continue
            if group not in restore_groups:
                # Unknown quarantine content is restored by its relative archive path.
                restore_groups.add(group)
            for dirpath, _, files in os.walk(group_path, topdown=False):
                for name in files:
                    source = os.path.join(dirpath, name)
                    rel = os.path.relpath(source, group_path)
                    parts = rel.split(os.sep)
                    # Quarantine layout preserves the archive-relative bucket path.
                    if parts and parts[0] in {"其它画册", "精品"}:
                        target = os.path.join(self.root, rel)
                    else:
                        target = os.path.join(self.root, "其它画册", "恢复内容", group, rel)
                    self.move_file(source, target, "restore_quarantine")

    def relocate_orphan_pic(self, original_by_hash: dict[str, str]) -> None:
        orphan = os.path.join(self.root, "其它画册", "Pic")
        if not os.path.isdir(orphan):
            return
        artist_root = os.path.join(self.root, "其它画册", "爆机少女喵小吉")
        for dirpath, _, files in os.walk(orphan, topdown=False):
            for name in files:
                source = os.path.join(dirpath, name)
                original = original_by_hash.get(md5(source), "")
                marker = "爆机少女喵小吉\\"
                normalized = original.replace("/", "\\")
                if marker in normalized:
                    suffix = normalized.split(marker, 1)[1]
                    target = os.path.join(artist_root, *suffix.split("\\"))
                else:
                    rel = os.path.relpath(source, orphan)
                    target = os.path.join(artist_root, "待识别附加图片", rel)
                self.move_file(source, target, "relocate_orphan_pic")

    def normalize_structure(self) -> None:
        other = os.path.join(self.root, "其它画册")
        boutique = os.path.join(self.root, "精品")

        # Direct albums that have an existing creator root.
        creator_names = ["仙仙桃", "小礼好困", "幼愛youmeko", "樱晚gigi", "落落Raku", "迷之呆梨"]
        if os.path.isdir(other):
            for name in creator_names:
                creator = os.path.join(other, name)
                if not os.path.isdir(creator):
                    continue
                for child in sorted(os.listdir(other)):
                    source = os.path.join(other, child)
                    if child != name and os.path.isdir(source) and child.startswith(name + " "):
                        self.merge_dir(source, os.path.join(creator, child), "group_creator_album")

        # Remove import wrapper layers while retaining meaningful album internals.
        wrapper_names = {"图册整理"}
        for dirpath, dirnames, _ in list(os.walk(self.root)):
            if "_待复核_重复与垃圾_勿删" in dirpath:
                continue
            for dirname in list(dirnames):
                if dirname in wrapper_names:
                    wrapper = os.path.join(dirpath, dirname)
                    for child in sorted(os.listdir(wrapper)):
                        old = os.path.join(wrapper, child)
                        new = os.path.join(dirpath, child)
                        if os.path.isdir(old):
                            self.merge_dir(old, new, "flatten_wrapper")
                        else:
                            self.move_file(old, new, "flatten_wrapper")

        # Artist range buckets are import artifacts, not archive categories.
        artist = os.path.join(other, "爆机少女喵小吉")
        if os.path.isdir(artist):
            for name in sorted(os.listdir(artist)):
                source = os.path.join(artist, name)
                if os.path.isdir(source) and name.startswith("X-BJSNMXJ-"):
                    for child in sorted(os.listdir(source)):
                        old = os.path.join(source, child)
                        new = os.path.join(artist, child)
                        if os.path.isdir(old):
                            self.merge_dir(old, new, "flatten_range_bucket")
                        else:
                            self.move_file(old, new, "flatten_range_bucket")

        # Merge split extraction suffixes only when the canonical sibling exists.
        for dirpath, dirnames, _ in list(os.walk(self.root)):
            for dirname in list(dirnames):
                if dirname.endswith("-1"):
                    base = dirname[:-2]
                    if base in dirnames and base in {"Pic", "图片", "视频"}:
                        self.merge_dir(
                            os.path.join(dirpath, dirname),
                            os.path.join(dirpath, base),
                            "merge_split_media_folder",
                        )

        # Known generic classification wrappers inside established series.
        flatten_paths = [
            os.path.join(boutique, "森萝财团", "未分类"),
            os.path.join(boutique, "紧急企划", "【内部VIP】", "R18", "其他"),
        ]
        for wrapper in flatten_paths:
            if not os.path.isdir(wrapper):
                continue
            parent = os.path.dirname(wrapper)
            for child in sorted(os.listdir(wrapper)):
                old = os.path.join(wrapper, child)
                new = os.path.join(parent, child)
                if os.path.isdir(old):
                    self.merge_dir(old, new, "flatten_generic_category")
                else:
                    self.move_file(old, new, "flatten_generic_category")

    def remove_empty_dirs(self) -> None:
        if not self.execute:
            return
        removed = 0
        for dirpath, _, _ in os.walk(self.root, topdown=False):
            if dirpath == self.root:
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
                    removed += 1
            except OSError:
                pass
        self.log("remove_empty_dirs", self.root, "", "removed", f"count={removed}")

    def update_database(self) -> None:
        if not self.execute or not self.moves:
            return
        path_columns = {
            "archive_execution_records": ["source_path", "target_path"],
            "archive_planning_records": ["source_root"],
            "archive_rollback_records": ["rollback_source_path", "rollback_target_path"],
            "assets": ["original_path", "current_path"],
            "operations": ["from_path", "to_path"],
            "series": ["archive_path"],
            "series_candidates": ["source_root"],
            "series_moderation_samples": ["sample_path"],
            "series_suggestions": ["suggested_archive_path"],
        }
        con = sqlite3.connect(DB_PATH, timeout=120)
        try:
            tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
            con.execute("begin")
            for old, new in self.moves:
                for table, columns in path_columns.items():
                    if table not in tables:
                        continue
                    existing = {r[1] for r in con.execute(f"pragma table_info({table})")}
                    for column in columns:
                        if column not in existing:
                            continue
                        con.execute(
                            f"update {table} set {column}=? || substr({column}, ?) "
                            f"where {column}=? or {column} like ?",
                            (new, len(old) + 1, old, old + "\\%"),
                        )
            # Confirmed series pointing to removed empty shells are stale, not missing content.
            rows = con.execute("select id, archive_path from series where status='confirmed'").fetchall()
            for sid, path in rows:
                if inside(path, self.root) and not os.path.exists(path):
                    con.execute(
                        "update series set status='failed', updated_at=CURRENT_TIMESTAMP where id=?",
                        (sid,),
                    )
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def load_original_hashes() -> dict[str, str]:
    con = sqlite3.connect(DB_PATH, timeout=120)
    try:
        return {
            hash_md5: original
            for hash_md5, original in con.execute(
                "select hash_md5, original_path from assets where hash_md5 is not null and original_path is not null"
            )
        }
    finally:
        con.close()


def write_report(rows: list[LogRow], timestamp: str) -> Path:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    path = REPORT_ROOT / f"nas-final-cleanup-{timestamp}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["Action", "Source", "Target", "Result", "Detail"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"Action": row.action, "Source": row.source, "Target": row.target, "Result": row.result, "Detail": row.detail})
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    con = sqlite3.connect(DB_PATH)
    try:
        root = con.execute("select root_path from libraries where kind='nas' order by id limit 1").fetchone()[0]
    finally:
        con.close()
    if not os.path.isdir(root):
        raise RuntimeError(f"NAS unavailable: {root}")
    cleaner = Cleaner(root, args.execute)
    hashes = load_original_hashes()
    cleaner.restore_quarantine()
    cleaner.relocate_orphan_pic(hashes)
    cleaner.normalize_structure()
    cleaner.remove_empty_dirs()
    cleaner.update_database()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report = write_report(cleaner.logs, timestamp)
    counts: dict[str, int] = {}
    for row in cleaner.logs:
        counts[row.result] = counts.get(row.result, 0) + 1
    print(f"mode={'execute' if args.execute else 'dry-run'}")
    print(f"rows={len(cleaner.logs)} results={counts}")
    print(f"moves={len(cleaner.moves)}")
    print(f"report={report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
