from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pims_v1.models.base import Base


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index("ix_assets_library_file_name", "library_id", "file_name"),
        Index("ix_assets_hash_md5", "hash_md5"),
        Index("ix_assets_hash_phash", "hash_phash"),
        Index("ix_assets_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id"))
    original_path: Mapped[str] = mapped_column(String(2048), unique=True)
    current_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_ext: Mapped[str] = mapped_column(String(32))
    file_type: Mapped[str] = mapped_column(String(50), default="image")
    file_size: Mapped[int] = mapped_column()
    mtime: Mapped[float] = mapped_column()
    hash_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hash_phash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    capture_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    duration: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="normal")
    stage: Mapped[str] = mapped_column(String(50), default="discovered")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
