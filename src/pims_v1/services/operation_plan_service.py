from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.library import Library
from pims_v1.models.operation import Operation, OperationBatch
from pims_v1.services.delete_service import delete_file, move_to_quarantine


def _perform_file_removal(source: Path, quarantine_root: str | Path, action: str) -> str:
    """Remove one redundant duplicate copy and return the resulting ``to_path``.

    ``action="delete"`` removes the file permanently (no quarantine backup),
    ``action="quarantine"`` (default) moves it into the reversible quarantine root.
    """
    if action == "delete":
        delete_file(source)
        return ""
    destination = move_to_quarantine(source, Path(quarantine_root))
    return str(destination)


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
    # Load all assets that already have an active quarantine operation once, so the
    # per-group loop avoids an N+1 existence query per duplicate copy.
    assets_with_active_operation = {
        row[0]
        for row in session.query(Operation.asset_id)
        .filter(
            Operation.operation_type == "quarantine_duplicate",
            Operation.status.in_(("planned", "confirmed", "executed")),
            Operation.asset_id.is_not(None),
        )
        .all()
    }
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
            if asset.id in assets_with_active_operation:
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


def _has_active_quarantine_operation(session: Session, asset_id: int) -> bool:
    return (
        session.query(Operation.id)
        .filter(
            Operation.operation_type == "quarantine_duplicate",
            Operation.asset_id == asset_id,
            Operation.status.in_(("planned", "confirmed", "executed")),
        )
        .first()
        is not None
    )


def _has_safe_keep_copy(session: Session, asset: Asset) -> bool:
    """A quarantine is only safe if a byte-identical copy is being retained (i.e.
    a same-MD5 sibling that the plan did not schedule for quarantine) and that
    copy still exists on disk, so we never remove the last accessible copy.

    This relies on the plan's own keep decision rather than re-matching the keep
    root string, which makes it robust to path-encoding differences between the
    configured keep root and the indexed asset paths.
    """
    if not asset.hash_md5:
        return False
    siblings = (
        session.query(Asset)
        .filter(Asset.hash_md5 == asset.hash_md5, Asset.id != asset.id)
        .all()
    )
    for sibling in siblings:
        if _has_active_quarantine_operation(session, sibling.id):
            continue
        if Path(_asset_path(sibling)).exists():
            return True
    return False


def _refresh_batch_status(session: Session, batch_id: int) -> None:
    batch = session.get(OperationBatch, batch_id)
    if batch is None or batch.status not in ("planned", "confirmed"):
        return
    unresolved = (
        session.query(Operation.id)
        .filter(
            Operation.batch_id == batch_id,
            Operation.status.in_(("planned", "confirmed")),
        )
        .first()
    )
    if unresolved is not None:
        return
    executed = (
        session.query(Operation.id)
        .filter(Operation.batch_id == batch_id, Operation.status == "executed")
        .first()
    )
    batch.status = "executed" if executed is not None else "failed"


def auto_quarantine_exact_duplicates(
    *,
    session: Session,
    keep_root: str,
    quarantine_root: str | Path,
    limit: int,
    action: str = "quarantine",
) -> dict[str, int]:
    """Automatically approve and remove byte-identical (exact MD5) duplicates.

    This is safe to automate because an exact MD5 match means the files are
    identical, and each operation is only executed when a verified keep copy
    (a same-MD5 sibling not scheduled for removal, present on disk) still exists
    for the same content. With ``action="delete"`` the redundant copy is removed
    permanently (no quarantine backup); with ``action="quarantine"`` the move is
    reversible.
    """
    summary = {
        "considered": 0,
        "executed": 0,
        "failed": 0,
        "held_no_keep_copy": 0,
        "skipped_missing_source": 0,
    }
    if limit <= 0:
        return summary

    operations = (
        session.query(Operation)
        .filter(
            Operation.operation_type == "quarantine_duplicate",
            Operation.status == "planned",
        )
        .order_by(Operation.id)
        .limit(limit)
        .all()
    )
    summary["considered"] = len(operations)
    touched_batches: set[int] = set()

    for operation in operations:
        touched_batches.add(operation.batch_id)
        asset = session.get(Asset, operation.asset_id) if operation.asset_id is not None else None
        if asset is None:
            continue

        if not _has_safe_keep_copy(session, asset):
            summary["held_no_keep_copy"] += 1
            continue

        source = Path(operation.from_path)
        if not source.exists():
            summary["skipped_missing_source"] += 1
            continue

        try:
            to_path = _perform_file_removal(source, quarantine_root, action)
        except Exception:
            operation.status = "failed"
            summary["failed"] += 1
            continue

        operation.to_path = to_path
        operation.status = "executed"
        if action == "delete":
            asset.status = "deleted"
        else:
            asset.current_path = to_path
            asset.status = "quarantined"
        summary["executed"] += 1

    session.flush()
    for batch_id in touched_batches:
        _refresh_batch_status(session, batch_id)

    session.commit()
    return summary


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
    *,
    action: str = "quarantine",
    limit: int | None = None,
    chunk_size: int = 500,
) -> dict[str, int | str]:
    """Execute a confirmed duplicate batch in bounded, incrementally-committed
    chunks so large batches do not load every operation/asset into memory at
    once (which previously exhausted RAM and crashed the run).

    The work is resumable: each chunk commits, and the batch stays ``confirmed``
    until fully drained, so a later call (or workflow round) continues where this
    left off. ``limit`` caps how many operations a single call processes.

    With ``action="delete"`` a redundant copy is only removed once a verified
    byte-identical keep copy still exists on disk, so the last accessible copy is
    never deleted.
    """
    batch = session.get(OperationBatch, batch_id)
    if batch is None:
        raise ValueError(f"Operation batch not found: {batch_id}")
    if batch.status != "confirmed":
        raise ValueError(f"Operation batch is not confirmed: {batch.status}")

    executed = 0
    failed = 0
    held_no_keep_copy = 0
    skipped_missing_source = 0
    processed = 0
    cursor = 0
    reached_limit = False

    while not reached_limit:
        remaining = None if limit is None else max(0, limit - processed)
        if remaining == 0:
            break
        fetch = chunk_size if remaining is None else min(chunk_size, remaining)
        operations = (
            session.query(Operation)
            .filter(
                Operation.batch_id == batch_id,
                Operation.status == "confirmed",
                Operation.id > cursor,
            )
            .order_by(Operation.id)
            .limit(fetch)
            .all()
        )
        if not operations:
            break

        for operation in operations:
            cursor = operation.id
            processed += 1
            asset = (
                session.get(Asset, operation.asset_id)
                if operation.asset_id is not None
                else None
            )

            if operation.operation_type != "quarantine_duplicate":
                operation.status = "failed"
                failed += 1
            elif action == "delete" and (asset is None or not _has_safe_keep_copy(session, asset)):
                # Never delete the last accessible copy; leave it confirmed for a
                # later attempt (cursor advances so this call does not re-scan it).
                held_no_keep_copy += 1
            else:
                source = Path(operation.from_path)
                if not source.exists():
                    operation.status = "executed"
                    operation.to_path = "" if action == "delete" else operation.to_path
                    if asset is not None:
                        asset.status = "deleted" if action == "delete" else "quarantined"
                    skipped_missing_source += 1
                else:
                    try:
                        to_path = _perform_file_removal(source, quarantine_root, action)
                    except Exception:
                        operation.status = "failed"
                        failed += 1
                    else:
                        operation.to_path = to_path
                        operation.status = "executed"
                        if asset is not None:
                            if action == "delete":
                                asset.status = "deleted"
                            else:
                                asset.current_path = to_path
                                asset.status = "quarantined"
                        executed += 1

            if limit is not None and processed >= limit:
                reached_limit = True
                break

        session.commit()
        session.expire_all()

    remaining_confirmed = (
        session.query(Operation.id)
        .filter(Operation.batch_id == batch_id, Operation.status == "confirmed")
        .first()
    )
    batch = session.get(OperationBatch, batch_id)
    if remaining_confirmed is None:
        any_executed = (
            session.query(Operation.id)
            .filter(Operation.batch_id == batch_id, Operation.status == "executed")
            .first()
        )
        batch.status = "executed" if any_executed is not None else "failed"
        session.commit()

    return {
        "batch_id": batch_id,
        "executed": executed,
        "failed": failed,
        "held_no_keep_copy": held_no_keep_copy,
        "skipped_missing_source": skipped_missing_source,
        "status": batch.status,
    }
