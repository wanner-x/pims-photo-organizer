from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.models.base import Base


class SeriesModerationRun(Base):
    __tablename__ = "series_moderation_runs"
    __table_args__ = (
        Index("ix_series_moderation_runs_candidate_created_at", "candidate_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("series_candidates.id"))
    provider: Mapped[str] = mapped_column(String(80), default="heuristic")
    mode: Mapped[str] = mapped_column(String(50), default="manual")
    status: Mapped[str] = mapped_column(String(50), default="completed")
    total_samples: Mapped[int] = mapped_column(Integer, default=0)
    flagged_samples: Mapped[int] = mapped_column(Integer, default=0)
    unsupported_samples: Mapped[int] = mapped_column(Integer, default=0)
    max_score: Mapped[float] = mapped_column(Float, default=0.0)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SeriesModerationSample(Base):
    __tablename__ = "series_moderation_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("series_moderation_runs.id"))
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    sample_path: Mapped[str] = mapped_column(String(2048))
    media_kind: Mapped[str] = mapped_column(String(30), default="image")
    sample_status: Mapped[str] = mapped_column(String(50), default="completed")
    label: Mapped[str] = mapped_column(String(80), default="safe")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    provider_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
