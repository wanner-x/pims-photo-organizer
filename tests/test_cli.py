from pims_v1.cli import main
from pims_v1.db import Base
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.library import Library
from pims_v1.models.operation import Operation, OperationBatch
from pims_v1.models.processing import ProcessingTask


def test_scan_sample_cli_reports_media_files(tmp_path, capsys, monkeypatch):
    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "a.jpg").write_bytes(b"jpeg-data")
    (library_root / "b.txt").write_bytes(b"text-data")

    monkeypatch.setattr(
        "sys.argv",
        ["pims", "scan-sample", str(library_root), "--limit", "1000"],
    )

    exit_code = main()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "sampled_files=1" in output
    assert ".jpg: 1" in output


def test_index_library_cli_writes_to_requested_database(tmp_path, capsys, monkeypatch):
    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "a.jpg").write_bytes(b"jpeg-data")
    db_path = tmp_path / "index.db"

    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "index-library",
            str(library_root),
            "--name",
            "Local photos",
            "--kind",
            "local",
            "--database-url",
            f"sqlite:///{db_path}",
        ],
    )

    exit_code = main()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "created=1" in output

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()

    assert session.query(Asset).count() == 1


def test_plan_duplicate_quarantine_cli_creates_batch(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "ops.db"
    database_url = f"sqlite:///{db_path}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path="D:\\photos")
    session.add(library_row)
    session.flush()
    nas_asset = Asset(
        library_id=library_row.id,
        original_path="\\\\192.168.31.10\\personal_folder\\nas_photos\\set\\a.jpg",
        current_path="\\\\192.168.31.10\\personal_folder\\nas_photos\\set\\a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
        hash_md5="same",
    )
    local_asset = Asset(
        library_id=library_row.id,
        original_path="D:\\photos\\set\\a.jpg",
        current_path="D:\\photos\\set\\a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
        hash_md5="same",
    )
    session.add_all([nas_asset, local_asset])
    session.flush()
    group = DuplicateGroup(hash_md5="same", asset_count=2)
    session.add(group)
    session.flush()
    session.add_all(
        [
            DuplicateGroupAsset(group_id=group.id, asset_id=nas_asset.id),
            DuplicateGroupAsset(group_id=group.id, asset_id=local_asset.id),
        ]
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "plan-duplicate-quarantine",
            "--keep-root",
            "\\\\192.168.31.10\\personal_folder\\nas_photos",
            "--database-url",
            database_url,
        ],
    )

    exit_code = main()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "operations=1" in output

    session = session_factory()
    assert session.query(OperationBatch).count() == 1
    operation_row = session.query(Operation).one()
    assert operation_row.from_path == "D:\\photos\\set\\a.jpg"


def test_confirm_batch_cli_marks_batch_confirmed(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "ops.db"
    database_url = f"sqlite:///{db_path}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    batch = OperationBatch(batch_type="duplicate_quarantine", status="planned")
    session.add(batch)
    session.flush()
    session.add(
        Operation(
            batch_id=batch.id,
            operation_type="quarantine_duplicate",
            from_path="D:\\photos\\a.jpg",
            status="planned",
        )
    )
    session.commit()
    batch_id = batch.id
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "confirm-batch",
            str(batch_id),
            "--database-url",
            database_url,
        ],
    )

    exit_code = main()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "status=confirmed" in output

    session = session_factory()
    assert session.get(OperationBatch, batch_id).status == "confirmed"


def test_execute_batch_cli_moves_confirmed_file_to_quarantine(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "ops.db"
    database_url = f"sqlite:///{db_path}"
    source = tmp_path / "library" / "a.jpg"
    source.parent.mkdir()
    source.write_bytes(b"duplicate")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path=str(source.parent))
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(source),
        current_path=str(source),
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
        hash_md5="same",
    )
    session.add(asset_row)
    session.flush()
    batch = OperationBatch(batch_type="duplicate_quarantine", status="confirmed")
    session.add(batch)
    session.flush()
    session.add(
        Operation(
            batch_id=batch.id,
            operation_type="quarantine_duplicate",
            asset_id=asset_row.id,
            from_path=str(source),
            status="confirmed",
        )
    )
    session.commit()
    batch_id = batch.id
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "execute-batch",
            str(batch_id),
            "--quarantine-root",
            str(tmp_path / ".quarantine"),
            "--database-url",
            database_url,
        ],
    )

    exit_code = main()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "executed=1" in output
    assert "failed=0" in output
    assert not source.exists()


def test_enqueue_md5_tasks_cli_creates_tasks_for_unhashed_assets(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "tasks.db"
    database_url = f"sqlite:///{db_path}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path="D:\\photos")
    session.add(library_row)
    session.flush()
    session.add_all(
        [
            Asset(
                library_id=library_row.id,
                original_path="D:\\photos\\a.jpg",
                current_path="D:\\photos\\a.jpg",
                file_name="a.jpg",
                file_ext=".jpg",
                file_size=1,
                mtime=1.0,
                hash_md5=None,
            ),
            Asset(
                library_id=library_row.id,
                original_path="D:\\photos\\b.jpg",
                current_path="D:\\photos\\b.jpg",
                file_name="b.jpg",
                file_ext=".jpg",
                file_size=1,
                mtime=1.0,
                hash_md5="done",
            ),
        ]
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        ["pims", "enqueue-md5-tasks", "--database-url", database_url],
    )

    exit_code = main()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "queued=1" in output
    session = session_factory()
    assert session.query(ProcessingTask).count() == 1


def test_enqueue_md5_tasks_cli_respects_limit(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "tasks.db"
    database_url = f"sqlite:///{db_path}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path="D:\\photos")
    session.add(library_row)
    session.flush()
    for index in range(3):
        session.add(
            Asset(
                library_id=library_row.id,
                original_path=f"D:\\photos\\{index}.jpg",
                current_path=f"D:\\photos\\{index}.jpg",
                file_name=f"{index}.jpg",
                file_ext=".jpg",
                file_size=1,
                mtime=1.0,
                hash_md5=None,
            )
        )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        ["pims", "enqueue-md5-tasks", "--limit", "2", "--database-url", database_url],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "queued=2" in output
    session = session_factory()
    assert session.query(ProcessingTask).count() == 2


def test_task_cli_lists_and_recovers_tasks(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "tasks.db"
    database_url = f"sqlite:///{db_path}"
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    task = ProcessingTask(
        task_type="hash_md5",
        subject_type="asset",
        subject_id=1,
        status="running",
        attempts=1,
        heartbeat_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=30),
    )
    session.add(task)
    session.commit()
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        ["pims", "recover-tasks", "--stale-after-seconds", "300", "--database-url", database_url],
    )
    assert main() == 0
    recover_output = capsys.readouterr().out
    assert "recovered=1" in recover_output

    monkeypatch.setattr(
        "sys.argv",
        ["pims", "list-tasks", "--status", "pending", "--database-url", database_url],
    )
    assert main() == 0
    list_output = capsys.readouterr().out
    assert "tasks=1" in list_output
    assert "hash_md5" in list_output


def test_process_md5_tasks_cli_hashes_queued_asset(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "tasks.db"
    database_url = f"sqlite:///{db_path}"
    source = tmp_path / "a.jpg"
    source.write_bytes(b"hash-me")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(source),
        current_path=str(source),
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=source.stat().st_size,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    session.add(
        ProcessingTask(
            task_type="hash_md5",
            subject_type="asset",
            subject_id=asset_row.id,
            status="pending",
        )
    )
    session.commit()
    asset_id = asset_row.id
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        ["pims", "process-md5-tasks", "--limit", "1", "--database-url", database_url],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "processed=1" in output
    session = session_factory()
    assert session.get(Asset, asset_id).hash_md5 == "0b893466231ec15a31520cfb1f761f4f"
