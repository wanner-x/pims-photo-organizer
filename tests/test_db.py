from pims_v1.db import engine


def test_sqlite_engine_waits_for_busy_writer():
    with engine.connect() as connection:
        timeout_ms = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()

    assert timeout_ms >= 30000
