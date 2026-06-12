from pims_v1.services.backup_service import backup_sqlite_database


def test_backup_sqlite_database_copies_database_file(tmp_path):
    database = tmp_path / "pims.db"
    database.write_bytes(b"sqlite-data")
    backup_dir = tmp_path / "backups"

    result = backup_sqlite_database(
        database_url=f"sqlite:///{database}",
        backup_dir=backup_dir,
        label="before-run",
    )

    assert result["status"] == "created"
    assert result["path"].endswith("before-run-pims.db")
    assert (backup_dir / "before-run-pims.db").read_bytes() == b"sqlite-data"
