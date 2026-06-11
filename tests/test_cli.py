from pims_v1.cli import main
from pims_v1.models.asset import Asset


def test_scan_sample_cli_reports_media_files(tmp_path, capsys, monkeypatch):
    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "a.jpg").write_bytes(b"jpeg-data")
    (library_root / "b.txt").write_bytes(b"text-data")

    monkeypatch.setattr(
        "sys.argv",
        ["pims", "scan-sample", str(library_root), "--limit", "1000"],
    )

    exit_code = main()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "sampled_files=1" in output
    assert ".jpg: 1" in output


def test_index_library_cli_writes_to_requested_database(tmp_path, capsys, monkeypatch):
    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "a.jpg").write_bytes(b"jpeg-data")
    db_path = tmp_path / "index.db"

    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "index-library",
            str(library_root),
            "--name",
            "Local photos",
            "--kind",
            "local",
            "--database-url",
            f"sqlite:///{db_path}",
        ],
    )

    exit_code = main()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "created=1" in output

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()

    assert session.query(Asset).count() == 1
