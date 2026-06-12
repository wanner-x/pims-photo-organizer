from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.operation import Operation, OperationBatch
from pims_v1.services.delete_service import move_to_quarantine


def _normalize_windows_path(path: str) -> str:
    return path.replace("/", "\\").rstrip("\\").casefold()


def _is_under_root(path: str, root: str) -> bool:
    normalized_path = _normalize_windows_path(path)
    normalized_root = _normalize_windows_path(root)
    return normalized_path == normalized_root or normalized_path.startswith(
        normalized_root + "\\"
    )


def _asset_path(asset: Asset) -> str:
    return asset.current_path or asset.original_path


def _choose_keep_asset(assets: list[Asset], keep_root: str) -> Asset:
    for asset in sorted(assets, key=lambda row: row.id):
        if _is_under_root(_asset_path(asset), keep_root):
            return asset
    return sorted(assets, key=lambda row: row.id)[0]


def create_duplicate_quarantine_plan(session: Session, keep_root: str) -> dict[str, int]:
    batch = OperationBatch(
        batch_type="duplicate_quarantine",
        status="planned",
        description=f"Keep copies under {keep_root}; quarantine duplicate copies elsewhere.",
    )
    session.add(batch)
    session.flush()

    operation_count = 0
    groups = session.query(DuplicateGroup).order_by(DuplicateGroup.id).all()
    for group in groups:
        assets = (
            session.query(Asset)
            .join(DuplicateGroupAsset, DuplicateGroupAsset.asset_id == Asset.id)
            .filter(DuplicateGroupAsset.group_id == group.id)
            .order_by(Asset.id)
            .all()
        )
        if len(assets) < 2:
            continue

        keep_asset = _choose_keep_asset(assets, keep_root)
        for asset in assets:
            if asset.id == keep_asset.id:
                continue
            existing = (
                session.query(Operation.id)
                .filter(
                    Operation.operation_type == "quarantine_duplicate",
                    Operation.asset_id == asset.id,
                    Operation.status.in_(("planned", "confirmed", "executed")),
                )
                .first()
            )
            if existing is not None:
                continue
            session.add(
                Operation(
                    batch_id=batch.id,
                    operation_type="quarantine_duplicate",
                    asset_id=asset.id,
                    from_path=_asset_path(asset),
                    status="planned",
                )
            )
            operation_count += 1

    session.commit()
    return {"batch_id": batch.id, "operations": operation_count}


def exclude_operation(session: Session, operation_id: int) -> dict[str, int | str]:
    operation = session.get(Operation, operation_id)
    if operation is None:
        raise ValueError(f"Operation not found: {operation_id}")
    if operation.status != "planned":
        raise ValueError(f"Operation is not planned: {operation.status}")
    operation.status = "excluded"
    session.commit()
    return {"operation_id": operation.id, "status": operation.status}


def confirm_operation_batch(session: Session, batch_id: int) -> dict[str, int | str]:
    batch = session.get(OperationBatch, batch_id)
    if batch is None:
        raise ValueError(f"Operation batch not found: {batch_id}")
    if batch.status != "planned":
        raise ValueError(f"Operation batch is not planned: {batch.status}")

    operations = (
        session.query(Operation)
        .filter(Operation.batch_id == batch_id, Operation.status == "planned")
        .all()
    )
    for operation in operations:
        operation.status = "confirmed"
    batch.status = "confirmed"
    session.commit()
    return {"batch_id": batch.id, "operations": len(operations), "status": batch.status}


def list_operation_batches(session: Session) -> list[dict[str, int | str | None]]:
    rows = (
        session.query(
            OperationBatch,
            func.count(Operation.id).label("operation_count"),
        )
        .outerjoin(Operation, Operation.batch_id == OperationBatch.id)
        .group_by(OperationBatch.id)
        .order_by(OperationBatch.id)
        .all()
    )
    return [
        {
            "id": batch.id,
            "batch_type": batch.batch_type,
            "status": batch.status,
            "description": batch.description,
            "operation_count": operation_count,
        }
        for batch, operation_count in rows
    ]


def execute_confirmed_batch(
    session: Session,
    batch_id: int,
    quarantine_root: str | Path,
) -> dict[str, int | str]:
    batch = session.get(OperationBatch, batch_id)
    if batch is None:
        raise ValueError(f"Operation batch not found: {batch_id}")
    if batch.status != "confirmed":
        raise ValueError(f"Operation batch is not confirmed: {batch.status}")

    operations = (
        session.query(Operation)
        .filter(Operation.batch_id == batch_id, Operation.status == "confirmed")
        .order_by(Operation.id)
        .all()
    )
    executed = 0
    failed = 0
    for operation in operations:
        try:
            if operation.operation_type != "quarantine_duplicate":
                raise ValueError(f"Unsupported operation type: {operation.operation_type}")
            destination = move_to_quarantine(Path(operation.from_path), Path(quarantine_root))
        except Exception:
            operation.status = "failed"
            failed += 1
            continue

        operation.to_path = str(destination)
        operation.status = "executed"
        if operation.asset_id is not None:
            asset = session.get(Asset, operation.asset_id)
            if asset is not None:
                asset.current_path = str(destination)
                asset.status = "quarantined"
        executed += 1

    batch.status = "executed" if failed == 0 else "failed"
    session.commit()
    return {
        "batch_id": batch.id,
        "executed": executed,
        "failed": failed,
        "status": batch.status,
    }
