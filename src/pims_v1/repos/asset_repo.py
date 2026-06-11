from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset


def find_asset_by_path(session: Session, original_path: str) -> Asset | None:
    return session.query(Asset).filter(Asset.original_path == original_path).one_or_none()
