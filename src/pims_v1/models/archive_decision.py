from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.models.base import Base


class ArchivePlanningRecord(Base):
    __tablename__ = "archive_planning_records"
    __table_args__ = (
        Index("ix_archive_planning_records_decision_type_created_at", "decision_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("series_candidates.id"))
    source_root: Mapped[str] = mapped_column(String(2048))
    rule_plan_json: Mapped[str] = mapped_column(Text)
    ai_plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_plan_json: Mapped[str] = mapped_column(Text)
    decision_type: Mapped[str] = mapped_column(String(50))
    rule_score: Mapped[float] = mapped_column(Float, default=0.0)
    ai_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    decision_reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ArchiveExecutionRecord(Base):
    __tablename__ = "archive_execution_records"
    __table_args__ = (
        Index("ix_archive_execution_records_planning_status", "planning_record_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    planning_record_id: Mapped[int] = mapped_column(ForeignKey("archive_planning_records.id"))
    operation_type: Mapped[str] = mapped_column(String(50))
    source_path: Mapped[str] = mapped_column(String(2048))
    target_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ArchiveRollbackRecord(Base):
    __tablename__ = "archive_rollback_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_record_id: Mapped[int] = mapped_column(ForeignKey("archive_execution_records.id"))
    rollback_source_path: Mapped[str] = mapped_column(String(2048))
    rollback_target_path: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    operator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ArchiveRiskEvent(Base):
    __tablename__ = "archive_risk_events"
    __table_args__ = (
        Index("ix_archive_risk_events_planning_severity", "planning_record_id", "severity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    planning_record_id: Mapped[int] = mapped_column(ForeignKey("archive_planning_records.id"))
    event_type: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(50), default="info")
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
