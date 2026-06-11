from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.models.base import Base


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (Index("ix_review_items_status_type_priority", "status", "item_type", "priority"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_type: Mapped[str] = mapped_column(String(50))
    subject_id: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(50), default="pending")
    priority: Mapped[int] = mapped_column(default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
