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


def test_exclude_operation_cli_marks_operation_excluded(tmp_path, capsys, monkeypatch):
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
    operation = Operation(
        batch_id=batch.id,
        operation_type="quarantine_duplicate",
        from_path="D:\\photos\\a.jpg",
        status="planned",
    )
    session.add(operation)
    session.commit()
    operation_id = operation.id
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "exclude-operation",
            str(operation_id),
            "--database-url",
            database_url,
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "status=excluded" in output
    session = session_factory()
    assert session.get(Operation, operation_id).status == "excluded"


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


def test_suggest_series_title_cli_uses_injected_client(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "ai.db"
    database_url = f"sqlite:///{db_path}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            pass

        def chat(self, messages):
            return "AI Title"

    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/set/a.jpg",
        current_path="/library/set/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset

    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set")
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    candidate_id = candidate.id
    session.close()

    monkeypatch.setattr("pims_v1.cli.DeepSeekClient", FakeClient)
    monkeypatch.setattr("pims_v1.cli.settings.deepseek_api_key", "test-key")
    monkeypatch.setattr(
        "sys.argv",
        ["pims", "suggest-series-title", str(candidate_id), "--database-url", database_url],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "title=AI Title" in output
    session = session_factory()
    assert session.get(SeriesCandidate, candidate_id).status == "ai_suggested"


def test_phash_task_cli_enqueue_and_process(tmp_path, capsys, monkeypatch):
    from PIL import Image
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "phash.db"
    database_url = f"sqlite:///{db_path}"
    source = tmp_path / "a.jpg"
    Image.new("RGB", (8, 8), color="white").save(source)
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
    session.commit()
    asset_id = asset_row.id
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        ["pims", "enqueue-phash-tasks", "--database-url", database_url],
    )
    assert main() == 0
    enqueue_output = capsys.readouterr().out
    assert "queued=1" in enqueue_output

    monkeypatch.setattr(
        "sys.argv",
        ["pims", "process-phash-tasks", "--limit", "1", "--database-url", database_url],
    )
    assert main() == 0
    process_output = capsys.readouterr().out
    assert "processed=1" in process_output

    session = session_factory()
    assert session.get(Asset, asset_id).hash_phash is not None


def test_phash_task_cli_enqueue_skips_video_assets(tmp_path, capsys, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "phash-video.db"
    database_url = f"sqlite:///{db_path}"
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Videos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    session.add(
        Asset(
            library_id=library_row.id,
            original_path=str(source),
            current_path=str(source),
            file_name="clip.mp4",
            file_ext=".mp4",
            file_size=source.stat().st_size,
            mtime=1.0,
        )
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        ["pims", "enqueue-phash-tasks", "--database-url", database_url],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "queued=0" in output


def test_build_thumbnails_cli_creates_cached_thumbnail(tmp_path, capsys, monkeypatch):
    from PIL import Image
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "thumbs.db"
    database_url = f"sqlite:///{db_path}"
    source = tmp_path / "a.jpg"
    Image.new("RGB", (80, 80), color="white").save(source)
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
    session.commit()
    asset_id = asset_row.id
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "build-thumbnails",
            "--limit",
            "1",
            "--cache-root",
            str(tmp_path / ".cache"),
            "--database-url",
            database_url,
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "created=1" in output
    assert (tmp_path / ".cache" / "thumbnails" / f"{asset_id}.jpg").exists()


def test_confirm_series_cli_creates_series(tmp_path, capsys, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "series.db"
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/set/a.jpg",
        current_path="/library/set/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    from pims_v1.models.series import Series, SeriesCandidate, SeriesCandidateAsset

    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="/library/set",
        title="Set 01",
    )
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    candidate_id = candidate.id
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "confirm-series",
            str(candidate_id),
            "--archive-root",
            "/nas/archive",
            "--database-url",
            database_url,
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "archive_path=/nas/archive/Set 01" in output
    session = session_factory()
    assert session.query(Series).count() == 1


def test_auto_archive_series_cli_executes_dual_engine_archive(tmp_path, capsys, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "auto-archive.db"
    database_url = f"sqlite:///{db_path}"
    archive_root = tmp_path / "nas"
    source_root = tmp_path / "pc" / "source"
    source_root.mkdir(parents=True)
    source_file = source_root / "001.jpg"
    source_file.write_bytes(b"sample")

    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(source_file),
        current_path=str(source_file),
        file_name="001.jpg",
        file_ext=".jpg",
        file_size=source_file.stat().st_size,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()

    from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset

    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="D:/图册/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]",
        title="雪琪SAMA 透明女仆 [43P4V234MB]",
    )
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    candidate_id = candidate.id
    session.close()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, messages):
            return (
                '{"title":"雪琪SAMA 透明女仆 [43P4V234MB]","category":"雪琪SAMA",'
                '"archive_path":"","plan_summary":"保持人物目录结构","risk_flags":[],'
                '"tags":[],"r18_label":false,"r18_confidence":0.0,"r18_reason":"","confidence":0.93}'
            )

    monkeypatch.setattr("pims_v1.cli.DeepSeekClient", FakeClient)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "auto-archive-series",
            str(candidate_id),
            "--archive-root",
            str(archive_root),
            "--database-url",
            database_url,
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "decision_type=auto_apply" in output
    assert "status=confirmed" in output


def test_run_safe_workflow_cli_builds_duplicate_plan(tmp_path, capsys, monkeypatch):
    from PIL import Image
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "workflow.db"
    database_url = f"sqlite:///{db_path}"
    local_root = tmp_path / "pc"
    nas_root = tmp_path / "nas"
    local_root.mkdir()
    nas_root.mkdir()
    local_file = local_root / "a.jpg"
    nas_file = nas_root / "a.jpg"
    Image.new("RGB", (16, 16), color="white").save(local_file)
    nas_file.write_bytes(local_file.read_bytes())
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    for path in [local_file, nas_file]:
        session.add(
            Asset(
                library_id=library_row.id,
                original_path=str(path),
                current_path=str(path),
                file_name=path.name,
                file_ext=path.suffix,
                file_size=path.stat().st_size,
                mtime=1.0,
            )
        )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "run-safe-workflow",
            "--keep-root",
            str(nas_root),
            "--cache-root",
            str(tmp_path / ".cache"),
            "--md5-limit",
            "10",
            "--phash-limit",
            "10",
            "--thumbnail-limit",
            "10",
            "--min-series-assets",
            "1",
            "--database-url",
            database_url,
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "md5.processed=2" in output
    assert "duplicate_plan.operations=1" in output


def test_run_safe_workflow_cli_reports_batch_auto_archive_summary(tmp_path, capsys, monkeypatch):
    from PIL import Image
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "workflow-auto.db"
    database_url = f"sqlite:///{db_path}"
    archive_root = tmp_path / "nas"
    source_dir = tmp_path / "pc" / "Alice" / "Alice Set [8P]"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "001.jpg"
    Image.new("RGB", (16, 16), color="white").save(source_file)
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    session.add(
        Asset(
            library_id=library_row.id,
            original_path=str(source_file),
            current_path=str(source_file),
            file_name=source_file.name,
            file_ext=source_file.suffix,
            file_size=source_file.stat().st_size,
            mtime=1.0,
        )
    )
    session.commit()
    session.close()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, messages):
            return (
                '{"title":"Alice Set [8P]","category":"Alice",'
                '"archive_path":"","plan_summary":"keep person bucket","risk_flags":[],'
                '"tags":[],"r18_label":false,"r18_confidence":0.0,"r18_reason":"","confidence":0.93}'
            )

    monkeypatch.setattr("pims_v1.cli.DeepSeekClient", FakeClient)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "run-safe-workflow",
            "--keep-root",
            str(archive_root),
            "--cache-root",
            str(tmp_path / ".cache"),
            "--md5-limit",
            "10",
            "--phash-limit",
            "10",
            "--thumbnail-limit",
            "10",
            "--min-series-assets",
            "1",
            "--series-limit",
            "100",
            "--auto-archive-limit",
            "5",
            "--database-url",
            database_url,
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "archive_auto.processed=1" in output
    assert "archive_auto.auto_apply=1" in output


def test_run_safe_workflow_cli_reports_ai_suggest_summary(tmp_path, capsys, monkeypatch):
    from PIL import Image
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "workflow-ai-suggest.db"
    database_url = f"sqlite:///{db_path}"
    archive_root = tmp_path / "nas"
    source_dir = tmp_path / "pc" / "Alice" / "Alice Set [8P]"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "001.jpg"
    Image.new("RGB", (16, 16), color="white").save(source_file)
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    session.add(
        Asset(
            library_id=library_row.id,
            original_path=str(source_file),
            current_path=str(source_file),
            file_name=source_file.name,
            file_ext=source_file.suffix,
            file_size=source_file.stat().st_size,
            mtime=1.0,
        )
    )
    session.commit()
    session.close()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, messages):
            return (
                '{"title":"Alice Set [8P]","category":"Alice",'
                '"archive_path":"","plan_summary":"keep person bucket","risk_flags":[],"tags":[],'
                '"r18_label":false,"r18_confidence":0.0,"r18_reason":"","confidence":0.93}'
            )

    monkeypatch.setattr("pims_v1.cli.DeepSeekClient", FakeClient)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "run-safe-workflow",
            "--keep-root",
            str(archive_root),
            "--cache-root",
            str(tmp_path / ".cache"),
            "--md5-limit",
            "10",
            "--phash-limit",
            "10",
            "--thumbnail-limit",
            "10",
            "--min-series-assets",
            "1",
            "--series-limit",
            "100",
            "--ai-suggest-limit",
            "5",
            "--auto-archive-limit",
            "0",
            "--database-url",
            database_url,
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "ai_suggest.processed=1" in output
    assert "ai_suggest.suggested=1" in output


def test_scan_series_r18_cli_reports_flagged_summary(tmp_path, capsys, monkeypatch):
    from PIL import Image
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "scan-r18.db"
    database_url = f"sqlite:///{db_path}"
    source_dir = tmp_path / "pc" / "set"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "001.jpg"
    Image.new("RGB", (16, 16), color=(220, 180, 160)).save(source_file)
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(source_file),
        current_path=str(source_file),
        file_name="001.jpg",
        file_ext=".jpg",
        file_size=source_file.stat().st_size,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset

    candidate = SeriesCandidate(library_id=library_row.id, source_root=str(source_dir), title="set")
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    candidate_id = candidate.id
    session.close()

    monkeypatch.setattr(
        "sys.argv",
        ["pims", "scan-series-r18", str(candidate_id), "--database-url", database_url],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "r18_label=True" in output
    assert "provider=heuristic" in output


def test_run_safe_workflow_cli_reports_r18_scan_summary(tmp_path, capsys, monkeypatch):
    from PIL import Image
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "workflow-r18.db"
    database_url = f"sqlite:///{db_path}"
    archive_root = tmp_path / "nas"
    source_dir = tmp_path / "pc" / "Alice" / "Alice Set [8P]"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "001.jpg"
    Image.new("RGB", (16, 16), color=(220, 180, 160)).save(source_file)
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    session.add(
        Asset(
            library_id=library_row.id,
            original_path=str(source_file),
            current_path=str(source_file),
            file_name=source_file.name,
            file_ext=source_file.suffix,
            file_size=source_file.stat().st_size,
            mtime=1.0,
        )
    )
    session.commit()
    session.close()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, messages):
            return (
                '{"title":"Alice Set [8P]","category":"Alice",'
                '"archive_path":"","plan_summary":"keep person bucket","risk_flags":[],'
                '"tags":[],"r18_label":false,"r18_confidence":0.0,"r18_reason":"","confidence":0.93}'
            )

    monkeypatch.setattr("pims_v1.cli.DeepSeekClient", FakeClient)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "run-safe-workflow",
            "--keep-root",
            str(archive_root),
            "--cache-root",
            str(tmp_path / ".cache"),
            "--md5-limit",
            "10",
            "--phash-limit",
            "10",
            "--thumbnail-limit",
            "10",
            "--min-series-assets",
            "1",
            "--series-limit",
            "100",
            "--r18-scan-limit",
            "5",
            "--auto-archive-limit",
            "5",
            "--database-url",
            database_url,
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "r18_scan.processed=1" in output
    assert "r18_scan.flagged=1" in output


def test_backup_db_cli_copies_sqlite_database(tmp_path, capsys, monkeypatch):
    database = tmp_path / "pims.db"
    database.write_bytes(b"sqlite-data")
    backup_dir = tmp_path / "backups"

    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "backup-db",
            "--database-url",
            f"sqlite:///{database}",
            "--backup-dir",
            str(backup_dir),
            "--label",
            "manual",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "status=created" in output
    assert (backup_dir / "manual-pims.db").exists()
