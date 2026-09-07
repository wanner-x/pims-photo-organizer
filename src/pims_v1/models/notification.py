from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.models.base import Base


class NotificationRecord(Base):
    """One row per (channel, event, subject) notification attempt.

    ``status`` lifecycle: ``sending`` (reserved) -> ``sent`` | ``failed``;
    digest mode adds ``digest_pending`` (queued for the daily digest) ->
    ``digested`` (included in a sent digest). Only ``failed`` reservations are
    retried; every other status permanently dedupes the subject.
    """

    __tablename__ = "notification_records"
    __table_args__ = (
        Index("ix_notification_records_channel_event", "channel", "event_type"),
        Index(
            "ux_notification_records_subject_once",
            "channel",
            "event_type",
            "subject_type",
            "subject_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    channel: Mapped[str] = mapped_column(String(50))
    event_type: Mapped[str] = mapped_column(String(100))
    subject_type: Mapped[str] = mapped_column(String(50))
    subject_id: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(50), default="sending")
    last_error: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class NotificationDigestEntry(Base):
    """One queued line for the daily digest message (digest mode only).

    Created instead of an immediate webhook send when ``PIMS_WECHAT_DIGEST``
    is enabled; flushed by ``send_wechat_daily_digest`` at the end of the safe
    workflow. ``status`` is ``pending`` until the entry has been included in a
    successfully sent digest, then ``sent`` with ``digest_date`` recording the
    day (YYYY-MM-DD) it was reported in.
    """

    __tablename__ = "notification_digest_entries"
    __table_args__ = (Index("ix_notification_digest_entries_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("notification_records.id"), unique=True
    )
    channel: Mapped[str] = mapped_column(String(50))
    event_type: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    digest_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
