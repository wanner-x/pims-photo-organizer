from pims_v1.cli import main


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
