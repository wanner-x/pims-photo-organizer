from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
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


class SeriesCandidateAsset(Base):
    __tablename__ = "series_candidate_assets"
    __table_args__ = (
        UniqueConstraint("candidate_id", "asset_id", name="uq_series_candidate_asset"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("series_candidates.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    sort_order: Mapped[int] = mapped_column(default=0)


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


class SeriesSuggestion(Base):
    __tablename__ = "series_suggestions"
    __table_args__ = (Index("ix_series_suggestions_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("series_candidates.id"), unique=True)
    suggested_title: Mapped[str] = mapped_column(String(255))
    suggested_category: Mapped[str] = mapped_column(String(255), default="未分类")
    suggested_archive_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    plan_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_flags: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    r18_label: Mapped[bool] = mapped_column(default=False)
    r18_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    r18_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    status: Mapped[str] = mapped_column(String(50), default="pending_review")
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
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
