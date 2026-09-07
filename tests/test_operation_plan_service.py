from sqlalchemy import create_engine
from sqlalchemy.orm import Query
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.library import Library
from pims_v1.models.operation import Operation, OperationBatch
from pims_v1.services.operation_plan_service import (
    auto_quarantine_exact_duplicates,
    confirm_operation_batch,
    create_duplicate_quarantine_plan,
    execute_confirmed_batch,
    exclude_operation,
    list_operation_batches,
)


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def add_asset(session, library_id: int, path: str, digest: str) -> Asset:
    asset_row = Asset(
        library_id=library_id,
        original_path=path,
        current_path=path,
        file_name=path.rsplit("\\", 1)[-1],
        file_ext=".jpg",
        file_size=10,
        mtime=1.0,
        hash_md5=digest,
    )
    session.add(asset_row)
    session.flush()
    return asset_row


def test_create_duplicate_quarantine_plan_keeps_nas_copy(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Photos", kind="local", root_path="D:\\photos")
    session.add(library_row)
    session.flush()
    nas_asset = add_asset(
        session,
        library_row.id,
        "\\\\192.168.31.10\\personal_folder\\nas_photos\\set\\a.jpg",
        "same",
    )
    local_asset = add_asset(session, library_row.id, "D:\\photos\\set\\a.jpg", "same")
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

    summary = create_duplicate_quarantine_plan(
        session=session,
        keep_root="\\\\192.168.31.10\\personal_folder\\nas_photos",
    )

    batch = session.query(OperationBatch).one()
    planned = session.query(Operation).one()
    assert summary == {"batch_id": batch.id, "operations": 1}
    assert batch.status == "planned"
    assert planned.asset_id == local_asset.id
    assert planned.operation_type == "quarantine_duplicate"
    assert planned.from_path == "D:\\photos\\set\\a.jpg"


def test_create_duplicate_quarantine_plan_does_not_duplicate_active_operations(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Photos", kind="local", root_path="D:\\photos")
    session.add(library_row)
    session.flush()
    nas_asset = add_asset(
        session,
        library_row.id,
        "\\\\192.168.31.10\\personal_folder\\nas_photos\\set\\a.jpg",
        "same",
    )
    local_asset = add_asset(session, library_row.id, "D:\\photos\\set\\a.jpg", "same")
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

    first = create_duplicate_quarantine_plan(
        session=session,
        keep_root="\\\\192.168.31.10\\personal_folder\\nas_photos",
    )
    second = create_duplicate_quarantine_plan(
        session=session,
        keep_root="\\\\192.168.31.10\\personal_folder\\nas_photos",
    )

    assert first["operations"] == 1
    assert second["operations"] == 0
    assert session.query(Operation).count() == 1
    assert session.query(OperationBatch).count() == 1


def test_confirm_operation_batch_marks_planned_operations_confirmed(tmp_path):
    session = make_session(tmp_path)
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

    result = confirm_operation_batch(session=session, batch_id=batch.id)

    operation_row = session.query(Operation).one()
    assert result == {"batch_id": batch.id, "operations": 1, "status": "confirmed"}
    assert batch.status == "confirmed"
    assert operation_row.status == "confirmed"


def test_confirm_operation_batch_uses_bulk_update_without_loading_operations(tmp_path, monkeypatch):
    session = make_session(tmp_path)
    batch = OperationBatch(batch_type="duplicate_quarantine", status="planned")
    session.add(batch)
    session.flush()
    session.add_all(
        [
            Operation(
                batch_id=batch.id,
                operation_type="quarantine_duplicate",
                from_path=f"D:\\photos\\{index}.jpg",
                status="planned",
            )
            for index in range(3)
        ]
    )
    session.commit()
    original_all = Query.all

    def fail_if_operations_are_materialized(query):
        if query.column_descriptions[0].get("entity") is Operation:
            raise AssertionError("confirm_operation_batch must bulk-update operations")
        return original_all(query)

    monkeypatch.setattr(Query, "all", fail_if_operations_are_materialized)

    result = confirm_operation_batch(session=session, batch_id=batch.id)

    assert result == {"batch_id": batch.id, "operations": 3, "status": "confirmed"}
    assert session.query(Operation).filter(Operation.status == "confirmed").count() == 3


def test_exclude_operation_marks_planned_operation_excluded(tmp_path):
    session = make_session(tmp_path)
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

    result = exclude_operation(session=session, operation_id=operation.id)

    session.refresh(operation)
    assert result == {"operation_id": operation.id, "status": "excluded"}
    assert operation.status == "excluded"


def test_list_operation_batches_includes_operation_counts(tmp_path):
    session = make_session(tmp_path)
    batch = OperationBatch(batch_type="duplicate_quarantine", status="planned")
    session.add(batch)
    session.flush()
    session.add_all(
        [
            Operation(
                batch_id=batch.id,
                operation_type="quarantine_duplicate",
                from_path="D:\\photos\\a.jpg",
            ),
            Operation(
                batch_id=batch.id,
                operation_type="quarantine_duplicate",
                from_path="D:\\photos\\b.jpg",
            ),
        ]
    )
    session.commit()

    batches = list_operation_batches(session=session)

    assert batches == [
        {
            "id": batch.id,
            "batch_type": "duplicate_quarantine",
            "status": "planned",
            "description": None,
            "operation_count": 2,
        }
    ]


def test_execute_confirmed_batch_moves_files_to_quarantine(tmp_path):
    session = make_session(tmp_path)
    source = tmp_path / "library" / "a.jpg"
    source.parent.mkdir()
    source.write_bytes(b"duplicate")
    library_row = Library(name="Photos", kind="local", root_path=str(source.parent))
    session.add(library_row)
    session.flush()
    asset_row = add_asset(session, library_row.id, str(source), "same")
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

    summary = execute_confirmed_batch(
        session=session,
        batch_id=batch.id,
        quarantine_root=tmp_path / ".quarantine",
    )

    operation_row = session.query(Operation).one()
    session.refresh(asset_row)
    assert summary["batch_id"] == batch.id
    assert summary["executed"] == 1
    assert summary["failed"] == 0
    assert summary["status"] == "executed"
    assert not source.exists()
    assert operation_row.status == "executed"
    assert operation_row.to_path is not None
    assert asset_row.status == "quarantined"
    assert asset_row.current_path == operation_row.to_path


def test_auto_quarantine_exact_duplicates_moves_safe_duplicate(tmp_path):
    session = make_session(tmp_path)
    keep_root = tmp_path / "nas"
    local_root = tmp_path / "pc"
    keep_root.mkdir()
    local_root.mkdir()
    keep_file = keep_root / "a.jpg"
    local_file = local_root / "a.jpg"
    keep_file.write_bytes(b"identical")
    local_file.write_bytes(b"identical")

    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    keep_asset = add_asset(session, library_row.id, str(keep_file), "same")
    local_asset = add_asset(session, library_row.id, str(local_file), "same")
    group = DuplicateGroup(hash_md5="same", asset_count=2)
    session.add(group)
    session.flush()
    session.add_all(
        [
            DuplicateGroupAsset(group_id=group.id, asset_id=keep_asset.id),
            DuplicateGroupAsset(group_id=group.id, asset_id=local_asset.id),
        ]
    )
    session.commit()

    plan = create_duplicate_quarantine_plan(session=session, keep_root=str(keep_root))

    summary = auto_quarantine_exact_duplicates(
        session=session,
        keep_root=str(keep_root),
        quarantine_root=tmp_path / ".quarantine",
        limit=10,
    )

    session.refresh(local_asset)
    batch = session.get(OperationBatch, plan["batch_id"])
    operation = session.query(Operation).filter(Operation.asset_id == local_asset.id).one()
    assert summary["executed"] == 1
    assert summary["held_no_keep_copy"] == 0
    assert not local_file.exists()
    assert keep_file.exists()
    assert operation.status == "executed"
    assert local_asset.status == "quarantined"
    assert batch.status == "executed"


def test_auto_quarantine_holds_when_keep_copy_missing_on_disk(tmp_path):
    session = make_session(tmp_path)
    keep_root = tmp_path / "nas"
    local_root = tmp_path / "pc"
    keep_root.mkdir()
    local_root.mkdir()
    local_file = local_root / "a.jpg"
    local_file.write_bytes(b"identical")
    # keep copy is recorded in DB but does NOT exist on disk (e.g. NAS unmounted)
    keep_path = keep_root / "a.jpg"

    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    keep_asset = add_asset(session, library_row.id, str(keep_path), "same")
    local_asset = add_asset(session, library_row.id, str(local_file), "same")
    group = DuplicateGroup(hash_md5="same", asset_count=2)
    session.add(group)
    session.flush()
    session.add_all(
        [
            DuplicateGroupAsset(group_id=group.id, asset_id=keep_asset.id),
            DuplicateGroupAsset(group_id=group.id, asset_id=local_asset.id),
        ]
    )
    session.commit()

    create_duplicate_quarantine_plan(session=session, keep_root=str(keep_root))

    summary = auto_quarantine_exact_duplicates(
        session=session,
        keep_root=str(keep_root),
        quarantine_root=tmp_path / ".quarantine",
        limit=10,
    )

    session.refresh(local_asset)
    operation = session.query(Operation).filter(Operation.asset_id == local_asset.id).one()
    assert summary["executed"] == 0
    assert summary["held_no_keep_copy"] == 1
    assert local_file.exists()
    assert operation.status == "planned"


def _build_confirmed_delete_fixture(tmp_path, count: int):
    session = make_session(tmp_path)
    keep_root = tmp_path / "nas"
    keep_root.mkdir()
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    batch = OperationBatch(batch_type="duplicate_quarantine", status="confirmed")
    session.add(batch)
    session.flush()
    # One retained keep copy on disk so deletes are safe.
    keep_file = keep_root / "keep.jpg"
    keep_file.write_bytes(b"identical")
    add_asset(session, library_row.id, str(keep_file), "same")
    dup_files = []
    for index in range(count):
        dup = tmp_path / f"dup_{index}.jpg"
        dup.write_bytes(b"identical")
        dup_files.append(dup)
        dup_asset = add_asset(session, library_row.id, str(dup), "same")
        session.add(
            Operation(
                batch_id=batch.id,
                operation_type="quarantine_duplicate",
                asset_id=dup_asset.id,
                from_path=str(dup),
                status="confirmed",
            )
        )
    session.commit()
    return session, batch, keep_file, dup_files


def test_execute_confirmed_batch_deletes_without_quarantine_backup(tmp_path):
    session, batch, keep_file, dup_files = _build_confirmed_delete_fixture(tmp_path, 1)
    quarantine_root = tmp_path / ".quarantine"

    summary = execute_confirmed_batch(
        session=session,
        batch_id=batch.id,
        quarantine_root=quarantine_root,
        action="delete",
    )

    operation_row = session.query(Operation).filter(Operation.from_path == str(dup_files[0])).one()
    assert summary["executed"] == 1
    assert summary["status"] == "executed"
    assert not dup_files[0].exists()
    assert keep_file.exists()
    # delete leaves no quarantine backup behind
    assert not quarantine_root.exists() or not any(quarantine_root.iterdir())
    assert operation_row.status == "executed"
    asset_row = session.get(Asset, operation_row.asset_id)
    assert asset_row.status == "deleted"


def test_execute_confirmed_batch_delete_holds_when_no_safe_keep_copy(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    batch = OperationBatch(batch_type="duplicate_quarantine", status="confirmed")
    session.add(batch)
    session.flush()
    only = tmp_path / "only.jpg"
    only.write_bytes(b"identical")
    only_asset = add_asset(session, library_row.id, str(only), "same")
    session.add(
        Operation(
            batch_id=batch.id,
            operation_type="quarantine_duplicate",
            asset_id=only_asset.id,
            from_path=str(only),
            status="confirmed",
        )
    )
    session.commit()

    summary = execute_confirmed_batch(
        session=session,
        batch_id=batch.id,
        quarantine_root=tmp_path / ".quarantine",
        action="delete",
    )

    assert summary["executed"] == 0
    assert summary["held_no_keep_copy"] == 1
    assert only.exists()
    operation_row = session.query(Operation).one()
    assert operation_row.status == "confirmed"


def test_execute_confirmed_batch_respects_limit_and_is_resumable(tmp_path):
    session, batch, keep_file, dup_files = _build_confirmed_delete_fixture(tmp_path, 5)

    first = execute_confirmed_batch(
        session=session,
        batch_id=batch.id,
        quarantine_root=tmp_path / ".quarantine",
        action="delete",
        limit=2,
        chunk_size=1,
    )
    assert first["executed"] == 2
    assert first["status"] == "confirmed"
    remaining = session.query(Operation).filter(Operation.status == "confirmed").count()
    assert remaining == 3

    second = execute_confirmed_batch(
        session=session,
        batch_id=batch.id,
        quarantine_root=tmp_path / ".quarantine",
        action="delete",
        limit=100,
        chunk_size=2,
    )
    assert second["executed"] == 3
    assert second["status"] == "executed"
    assert session.query(Operation).filter(Operation.status == "confirmed").count() == 0
    assert all(not dup.exists() for dup in dup_files)
    assert keep_file.exists()


def test_auto_quarantine_deletes_when_action_delete(tmp_path):
    session = make_session(tmp_path)
    keep_root = tmp_path / "nas"
    keep_root.mkdir()
    keep_file = keep_root / "a.jpg"
    local_file = tmp_path / "a.jpg"
    keep_file.write_bytes(b"identical")
    local_file.write_bytes(b"identical")
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    keep_asset = add_asset(session, library_row.id, str(keep_file), "same")
    local_asset = add_asset(session, library_row.id, str(local_file), "same")
    group = DuplicateGroup(hash_md5="same", asset_count=2)
    session.add(group)
    session.flush()
    session.add_all(
        [
            DuplicateGroupAsset(group_id=group.id, asset_id=keep_asset.id),
            DuplicateGroupAsset(group_id=group.id, asset_id=local_asset.id),
        ]
    )
    session.commit()

    create_duplicate_quarantine_plan(session=session, keep_root=str(keep_root))
    quarantine_root = tmp_path / ".quarantine"
    summary = auto_quarantine_exact_duplicates(
        session=session,
        keep_root=str(keep_root),
        quarantine_root=quarantine_root,
        limit=10,
        action="delete",
    )

    session.refresh(local_asset)
    assert summary["executed"] == 1
    assert not local_file.exists()
    assert keep_file.exists()
    assert not quarantine_root.exists() or not any(quarantine_root.iterdir())
    assert local_asset.status == "deleted"


def test_execute_confirmed_batch_rejects_unconfirmed_batch(tmp_path):
    session = make_session(tmp_path)
    batch = OperationBatch(batch_type="duplicate_quarantine", status="planned")
    session.add(batch)
    session.commit()

    try:
        execute_confirmed_batch(
            session=session,
            batch_id=batch.id,
            quarantine_root=tmp_path / ".quarantine",
        )
    except ValueError as exc:
        assert "not confirmed" in str(exc)
    else:
        raise AssertionError("Expected unconfirmed batch to be rejected")
