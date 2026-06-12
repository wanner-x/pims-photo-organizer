from sqlalchemy import inspect
from sqlalchemy import create_engine

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, notification, operation, processing, review, series


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
