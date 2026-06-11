from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.models.base import Base


class SimilarGroup(Base):
    __tablename__ = "similar_groups"
    __table_args__ = (Index("ix_similar_groups_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    representative_phash: Mapped[str] = mapped_column(String(32))
    asset_count: Mapped[int] = mapped_column(default=0)
    threshold: Mapped[int] = mapped_column(default=6)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SimilarGroupAsset(Base):
    __tablename__ = "similar_group_assets"
    __table_args__ = (UniqueConstraint("group_id", "asset_id", name="uq_similar_group_asset"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("similar_groups.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
