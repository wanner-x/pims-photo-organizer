from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.models.base import Base


class SeriesCandidate(Base):
    __tablename__ = "series_candidates"
    __table_args__ = (Index("ix_series_candidates_status_confidence", "status", "confidence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id"))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_root: Mapped[str] = mapped_column(String(2048))
    confidence: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id"))
    title: Mapped[str] = mapped_column(String(255))
    archive_path: Mapped[str] = mapped_column(String(2048), unique=True)
    status: Mapped[str] = mapped_column(String(50), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SeriesAsset(Base):
    __tablename__ = "series_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    role: Mapped[str] = mapped_column(String(50), default="normal")
    sort_order: Mapped[int] = mapped_column(default=0)
