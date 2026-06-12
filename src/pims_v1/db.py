from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.config import settings
from pims_v1.models.base import Base


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def ensure_database_schema(bind=engine) -> None:
    Base.metadata.create_all(bind=bind)
    with bind.begin() as connection:
        existing_series_suggestion_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(series_suggestions)").fetchall()
        }
        for column_name, column_type in {
            "suggested_archive_path": "VARCHAR(2048)",
            "plan_summary": "TEXT",
            "risk_flags": "TEXT",
        }.items():
            if column_name not in existing_series_suggestion_columns:
                connection.exec_driver_sql(f"ALTER TABLE series_suggestions ADD COLUMN {column_name} {column_type}")
        connection.exec_driver_sql(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_notification_records_subject_once
            ON notification_records (channel, event_type, subject_type, subject_id)
            """
        )


__all__ = ["Base", "SessionLocal", "engine", "ensure_database_schema"]
