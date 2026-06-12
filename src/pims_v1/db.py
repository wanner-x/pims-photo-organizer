from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.config import settings
from pims_v1.models.base import Base


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def ensure_database_schema(bind=engine) -> None:
    Base.metadata.create_all(bind=bind)
    with bind.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_notification_records_subject_once
            ON notification_records (channel, event_type, subject_type, subject_id)
            """
        )


__all__ = ["Base", "SessionLocal", "engine", "ensure_database_schema"]
