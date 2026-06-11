from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.library import Library
from pims_v1.models.operation import Operation, OperationBatch
from pims_v1.services.operation_plan_service import (
    confirm_operation_batch,
    create_duplicate_quarantine_plan,
    execute_confirmed_batch,
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
    assert summary == {"batch_id": batch.id, "executed": 1, "failed": 0, "status": "executed"}
    assert not source.exists()
    assert operation_row.status == "executed"
    assert operation_row.to_path is not None
    assert asset_row.status == "quarantined"
    assert asset_row.current_path == operation_row.to_path


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
