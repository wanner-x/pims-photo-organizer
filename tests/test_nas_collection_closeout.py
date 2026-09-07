from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "nas_collection_closeout.py"
SPEC = importlib.util.spec_from_file_location("nas_collection_closeout", MODULE_PATH)
assert SPEC and SPEC.loader
closeout = importlib.util.module_from_spec(SPEC)
sys.modules["nas_collection_closeout"] = closeout
SPEC.loader.exec_module(closeout)


def test_full_auto_policy_moves_uncertain_group_and_updates_paths(tmp_path, monkeypatch):
    root = tmp_path / "nas"
    other = root / "其它画册"
    source = other / "Alpha Vol 001"
    target = other / "Alpha" / "Alpha Vol 001"
    source.mkdir(parents=True)
    (source / "cover.jpg").write_bytes(b"image")

    db_path = tmp_path / "pims.db"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        create table series (
            id integer primary key,
            title text not null,
            archive_path text not null,
            status text not null,
            updated_at text
        );
        create table assets (
            id integer primary key,
            original_path text not null,
            current_path text,
            status text not null,
            updated_at text
        );
        """
    )
    con.execute(
        "insert into series(id, title, archive_path, status) values (1, 'Alpha Vol 001', ?, 'confirmed')",
        (str(source),),
    )
    con.execute(
        "insert into assets(id, original_path, current_path, status) values (1, ?, ?, 'active')",
        (str(source / "cover.jpg"), str(source / "cover.jpg")),
    )
    con.commit()
    con.close()

    monkeypatch.setattr(closeout, "DB_PATH", db_path)
    monkeypatch.setattr(closeout, "REPORTS_ROOT", tmp_path / "reports")
    closeout.REPORTS_ROOT.mkdir()

    row = closeout.MoveRow(
        source_path=str(source),
        target_path=str(target),
        rule="Alpha",
        alias="Alpha",
        action="review",
        reason="discovered_prefix_count=2;target_available",
        review_status="required",
    )

    result_path, db_report, results = closeout.execute_move_rows(
        move_rows=[],
        uncertain_rows=[row],
        timestamp="20260101-000000",
        auto_policy="full",
    )

    assert result_path.exists()
    assert db_report.exists()
    assert [result.result for result in results] == ["moved"]
    assert not source.exists()
    assert (target / "cover.jpg").exists()

    con = sqlite3.connect(db_path)
    assert con.execute("select archive_path from series where id=1").fetchone()[0] == str(target)
    asset_paths = con.execute("select original_path, current_path from assets where id=1").fetchone()
    con.close()
    assert asset_paths == (str(target / "cover.jpg"), str(target / "cover.jpg"))


def test_execute_skips_existing_nonempty_target_without_overwrite(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "source.jpg").write_bytes(b"source")
    (target / "existing.jpg").write_bytes(b"existing")

    db_path = tmp_path / "pims.db"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        create table series (id integer primary key, archive_path text not null);
        create table assets (id integer primary key, original_path text not null, current_path text);
        """
    )
    con.commit()
    con.close()

    monkeypatch.setattr(closeout, "DB_PATH", db_path)
    monkeypatch.setattr(closeout, "REPORTS_ROOT", tmp_path / "reports")
    closeout.REPORTS_ROOT.mkdir()

    row = closeout.MoveRow(
        source_path=str(source),
        target_path=str(target),
        rule="collision",
        alias="collision",
        action="move",
        reason="target_available",
        review_status="not_required",
    )

    _result_path, _db_report, results = closeout.execute_move_rows(
        move_rows=[row],
        uncertain_rows=[],
        timestamp="20260101-000001",
        auto_policy="full",
    )

    assert [result.result for result in results] == ["collision"]
    assert source.exists()
    assert (source / "source.jpg").exists()
    assert (target / "existing.jpg").exists()


def test_delete_exact_junk_files_removes_only_known_names(tmp_path, monkeypatch):
    root = tmp_path / "nas"
    root.mkdir()
    exact = root / "永久地址 - 发布页.txt"
    unknown = root / "疑似发布页.txt"
    exact.write_text("ad", encoding="utf-8")
    unknown.write_text("maybe", encoding="utf-8")
    monkeypatch.setattr(closeout, "REPORTS_ROOT", tmp_path / "reports")
    closeout.REPORTS_ROOT.mkdir()

    report_path, results = closeout.delete_exact_junk_files(str(root), "20260101-000002")

    assert report_path.exists()
    assert [row["Result"] for row in results] == ["deleted"]
    assert not exact.exists()
    assert unknown.exists()


def test_main_execute_full_calls_execute_with_generated_plan(tmp_path, monkeypatch):
    root = tmp_path / "nas"
    root.mkdir()
    monkeypatch.setattr(closeout, "REPORTS_ROOT", tmp_path / "reports")
    monkeypatch.setattr(closeout, "get_nas_root", lambda: str(root))
    monkeypatch.setattr(closeout.os.path, "isdir", lambda path: True)
    monkeypatch.setattr(closeout, "scan_directories", lambda _root: [])
    monkeypatch.setattr(closeout, "write_directory_baseline", lambda _rows, _timestamp: tmp_path / "baseline.csv")
    monkeypatch.setattr(closeout, "write_series_baseline", lambda _root, _timestamp: (tmp_path / "series.csv", 0))
    monkeypatch.setattr(closeout, "write_rules", lambda _timestamp: tmp_path / "rules.csv")
    monkeypatch.setattr(closeout, "build_move_plan", lambda _root, _rows: ([], []))
    monkeypatch.setattr(closeout, "write_move_rows", lambda path, _rows: path)
    monkeypatch.setattr(closeout, "write_junk_report", lambda _root, _timestamp: (tmp_path / "junk.csv", 0))
    monkeypatch.setattr(closeout, "delete_exact_junk_files", lambda _root, _timestamp: (tmp_path / "deleted.csv", []))
    monkeypatch.setattr(closeout, "write_summary", lambda *_args: tmp_path / "summary.txt")
    calls = []

    def fake_execute(move_rows, uncertain_rows, timestamp, auto_policy):
        calls.append((move_rows, uncertain_rows, timestamp, auto_policy))
        return tmp_path / "result.csv", tmp_path / "db.csv", []

    monkeypatch.setattr(closeout, "execute_move_rows", fake_execute)
    monkeypatch.setattr(sys, "argv", ["nas_collection_closeout.py", "--execute", "--auto-policy", "full"])

    assert closeout.main() == 0
    assert calls
    assert calls[0][3] == "full"


def test_update_database_paths_displaces_failed_series_archive_conflict(tmp_path, monkeypatch):
    old_path = str(tmp_path / "old" / "set")
    new_path = str(tmp_path / "new" / "set")
    db_path = tmp_path / "pims.db"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        create table series (
            id integer primary key,
            title text not null,
            archive_path text not null unique,
            status text not null,
            updated_at text
        );
        """
    )
    con.execute(
        "insert into series(id, title, archive_path, status) values (1, 'active set', ?, 'confirmed')",
        (old_path,),
    )
    con.execute(
        "insert into series(id, title, archive_path, status) values (2, 'stale failed set', ?, 'failed')",
        (new_path,),
    )
    con.commit()
    con.close()

    monkeypatch.setattr(closeout, "DB_PATH", db_path)
    monkeypatch.setattr(closeout, "REPORTS_ROOT", tmp_path / "reports")
    closeout.REPORTS_ROOT.mkdir()

    report = closeout.update_database_paths([(old_path, new_path)], "20260101-000003")

    assert report.exists()
    con = sqlite3.connect(db_path)
    active = con.execute("select archive_path from series where id=1").fetchone()[0]
    stale = con.execute("select archive_path from series where id=2").fetchone()[0]
    con.close()
    assert active == new_path
    assert stale != new_path
    assert stale.endswith("__duplicate_series_2")


def test_build_move_plan_ignores_special_quarantine_root(tmp_path, monkeypatch):
    root = str(tmp_path / "nas")
    source = str(
        tmp_path
        / "nas"
        / "_待复核_重复与垃圾_勿删"
        / "空目录"
        / "其它画册"
        / "爆机少女喵小吉"
    )
    rows = [
        closeout.DirectoryInfo(root, "", (), 0, str(tmp_path), "nas", 2, 0, 0, "root"),
        closeout.DirectoryInfo(
            source,
            "_待复核_重复与垃圾_勿删\\空目录\\其它画册\\爆机少女喵小吉",
            ("_待复核_重复与垃圾_勿删", "空目录", "其它画册", "爆机少女喵小吉"),
            4,
            str(tmp_path),
            "爆机少女喵小吉",
            0,
            0,
            0,
            "_待复核_重复与垃圾_勿删",
        ),
    ]

    move_rows, uncertain_rows = closeout.build_move_plan(root, rows)

    assert move_rows == []
    assert uncertain_rows == []
