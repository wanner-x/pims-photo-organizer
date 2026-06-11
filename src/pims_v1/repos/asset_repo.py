from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset


def find_asset_by_path(session: Session, original_path: str) -> Asset | None:
    return session.query(Asset).filter(Asset.original_path == original_path).one_or_none()


def list_assets_missing_md5(session: Session, limit: int | None = None) -> list[Asset]:
    query = session.query(Asset).filter(Asset.hash_md5.is_(None)).order_by(Asset.id)
    if limit is not None:
        query = query.limit(limit)
    return list(query.all())


def upsert_discovered_asset(
    session: Session,
    *,
    library_id: int,
    original_path: str,
    file_name: str,
    file_ext: str,
    file_size: int,
    mtime: float,
) -> tuple[Asset, bool]:
    asset = find_asset_by_path(session, original_path)
    if asset is None:
        asset = Asset(
            library_id=library_id,
            original_path=original_path,
            current_path=original_path,
            file_name=file_name,
            file_ext=file_ext,
            file_size=file_size,
            mtime=mtime,
            stage="meta_done",
        )
        session.add(asset)
        session.flush()
        return asset, True

    asset.library_id = library_id
    asset.current_path = original_path
    asset.file_name = file_name
    asset.file_ext = file_ext
    asset.file_size = file_size
    asset.mtime = mtime
    asset.stage = "meta_done"
    session.flush()
    return asset, False
