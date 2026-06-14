from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.library import Library
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
    planned_operations = []
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
            planned_operations.append(
                {
                    "asset_id": asset.id,
                    "from_path": _asset_path(asset),
                }
            )

    if not planned_operations:
        return {"batch_id": 0, "operations": 0}

    batch = OperationBatch(
        batch_type="duplicate_quarantine",
        status="planned",
        description=f"Keep copies under {keep_root}; quarantine duplicate copies elsewhere.",
    )
    session.add(batch)
    session.flush()

    for operation in planned_operations:
        session.add(
            Operation(
                batch_id=batch.id,
                operation_type="quarantine_duplicate",
                asset_id=operation["asset_id"],
                from_path=operation["from_path"],
                status="planned",
            )
        )

    session.commit()
    return {"batch_id": batch.id, "operations": len(planned_operations)}


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
        .update({Operation.status: "confirmed"}, synchronize_session=False)
    )
    batch.status = "confirmed"
    session.commit()
    return {"batch_id": batch.id, "operations": operations, "status": batch.status}


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


def _media_url(asset: Asset) -> str:
    return f"/media/assets/{asset.id}"


def _thumbnail_url(asset: Asset) -> str:
    return f"/thumbnails/{asset.id}.jpg"


def _operation_asset_payload(asset: Asset | None) -> dict[str, int | str | None] | None:
    if asset is None:
        return None
    return {
        "id": asset.id,
        "file_name": asset.file_name,
        "current_path": asset.current_path or asset.original_path,
        "file_ext": asset.file_ext,
        "file_size": asset.file_size,
        "hash_md5": asset.hash_md5,
        "hash_phash": asset.hash_phash,
        "media_url": _media_url(asset),
        "thumbnail_url": _thumbnail_url(asset),
    }


def _keep_root_from_description(description: str | None) -> str | None:
    if not description or not description.startswith("Keep copies under "):
        return None
    keep_root, _, _ = description[len("Keep copies under ") :].partition(";")
    return keep_root or None


def _duplicate_role(asset: Asset, operation: Operation, keep_root: str | None) -> tuple[str, str]:
    if asset.id == operation.asset_id:
        return "duplicate_target", "重复位置，将隔离"
    if keep_root and _is_under_root(_asset_path(asset), keep_root):
        return "keep_copy", "已存在位置，建议保留"
    return "related_copy", "同内容副本"


def _duplicate_asset_payload(
    *,
    asset: Asset,
    library_kind: str | None,
    operation: Operation,
    keep_root: str | None,
) -> dict[str, int | str | None]:
    role, role_label = _duplicate_role(asset, operation, keep_root)
    return {
        "id": asset.id,
        "file_name": asset.file_name,
        "current_path": asset.current_path or asset.original_path,
        "file_ext": asset.file_ext,
        "file_size": asset.file_size,
        "hash_md5": asset.hash_md5,
        "hash_phash": asset.hash_phash,
        "library_kind": library_kind,
        "media_url": _media_url(asset),
        "role": role,
        "role_label": role_label,
        "thumbnail_url": _thumbnail_url(asset),
    }


def _operation_duplicate_assets(
    session: Session,
    operation: Operation,
    asset: Asset | None,
    keep_root: str | None,
) -> list[dict[str, int | str | None]]:
    if asset is None or not asset.hash_md5:
        return []

    rows = (
        session.query(Asset, Library.kind)
        .join(Library, Library.id == Asset.library_id)
        .filter(Asset.hash_md5 == asset.hash_md5)
        .order_by(Asset.id)
        .all()
    )
    return [
        _duplicate_asset_payload(
            asset=row_asset,
            library_kind=library_kind,
            operation=operation,
            keep_root=keep_root,
        )
        for row_asset, library_kind in rows
    ]


def list_batch_operations(
    session: Session,
    batch_id: int,
    *,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, int | str | None | dict[str, int | str | None]]]:
    query = (
        session.query(Operation)
        .filter(Operation.batch_id == batch_id)
        .order_by(Operation.id)
    )
    if status is not None:
        query = query.filter(Operation.status == status)

    operations = query.offset(offset).limit(limit).all()
    result = []
    batch = session.get(OperationBatch, batch_id)
    keep_root = _keep_root_from_description(batch.description if batch else None)
    for operation in operations:
        asset = session.get(Asset, operation.asset_id) if operation.asset_id is not None else None
        result.append(
            {
                "id": operation.id,
                "batch_id": operation.batch_id,
                "operation_type": operation.operation_type,
                "status": operation.status,
                "from_path": operation.from_path,
                "to_path": operation.to_path,
                "asset": _operation_asset_payload(asset),
                "duplicate_assets": _operation_duplicate_assets(
                    session=session,
                    operation=operation,
                    asset=asset,
                    keep_root=keep_root,
                ),
            }
        )
    return result


def count_batch_operations(
    session: Session,
    batch_id: int,
    *,
    status: str | None = None,
) -> int:
    query = session.query(Operation).filter(Operation.batch_id == batch_id)
    if status is not None:
        query = query.filter(Operation.status == status)
    return query.count()


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
