from sqlalchemy import inspect

from pims_v1.db import Base, engine
from pims_v1.models import asset, library, operation, processing, review, series


def test_core_tables_exist():
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
