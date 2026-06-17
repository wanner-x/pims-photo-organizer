from pims_v1.db import engine, ensure_database_schema


def test_sqlite_engine_waits_for_busy_writer():
    with engine.connect() as connection:
        timeout_ms = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()

    assert timeout_ms >= 30000


def test_sqlite_database_uses_wal_journal_mode():
    ensure_database_schema(engine)

    with engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()

    assert journal_mode.lower() == "wal"
