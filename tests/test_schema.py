from sqlalchemy import inspect
from sqlalchemy import create_engine

from pims_v1.db import Base, ensure_database_schema
from pims_v1.models import archive_decision, asset, duplicate, library, notification, operation, processing, review, series


def test_core_tables_exist(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}", future=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)

    table_names = set(inspector.get_table_names())

    assert "libraries" in table_names
    assert "assets" in table_names
    assert "series_candidates" in table_names
    assert "review_items" in table_names
    assert "processing_tasks" in table_names
    assert "operation_batches" in table_names
    assert "notification_records" in table_names
    assert "duplicate_groups" in table_names
    assert "similar_groups" in table_names
    assert "series_candidate_assets" in table_names
    assert "series_suggestions" in table_names
    assert "archive_planning_records" in table_names
    assert "archive_execution_records" in table_names
    assert "archive_rollback_records" in table_names
    assert "archive_risk_events" in table_names
    assert "series_moderation_runs" in table_names
    assert "series_moderation_samples" in table_names


def test_notification_records_have_business_unique_index(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}", future=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)

    indexes = inspector.get_indexes("notification_records")

    assert any(
        index.get("unique")
        and set(index["column_names"]) == {"channel", "event_type", "subject_type", "subject_id"}
        for index in indexes
    )


def test_ensure_database_schema_creates_notification_business_unique_index(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}", future=True)

    ensure_database_schema(engine)
    inspector = inspect(engine)
    indexes = inspector.get_indexes("notification_records")

    assert any(index["name"] == "ux_notification_records_subject_once" and index.get("unique") for index in indexes)


def test_ensure_database_schema_adds_series_suggestion_plan_columns(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}", future=True)

    ensure_database_schema(engine)
    inspector = inspect(engine)
    column_names = {column["name"] for column in inspector.get_columns("series_suggestions")}

    assert {"suggested_archive_path", "plan_summary", "risk_flags"}.issubset(column_names)


def test_ensure_database_schema_adds_series_suggestion_tag_columns(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}", future=True)

    ensure_database_schema(engine)
    inspector = inspect(engine)
    column_names = {column["name"] for column in inspector.get_columns("series_suggestions")}

    assert {"content_tags", "r18_label", "r18_confidence", "r18_reason"}.issubset(column_names)


def test_archive_planning_records_have_decision_index(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}", future=True)

    ensure_database_schema(engine)
    inspector = inspect(engine)
    indexes = inspector.get_indexes("archive_planning_records")

    assert any(index["name"] == "ix_archive_planning_records_decision_type_created_at" for index in indexes)


def test_series_moderation_runs_have_candidate_index(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}", future=True)

    ensure_database_schema(engine)
    inspector = inspect(engine)
    indexes = inspector.get_indexes("series_moderation_runs")

    assert any(index["name"] == "ix_series_moderation_runs_candidate_created_at" for index in indexes)
