from pims_v1.services.delete_service import archive_and_quarantine_if_verified


def test_archive_then_quarantine_flow(tmp_path):
    source = tmp_path / "incoming" / "a.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"one")

    archive_target = tmp_path / "archive" / "series1" / "a.jpg"
    result = archive_and_quarantine_if_verified(
        source=source,
        archive_target=archive_target,
        quarantine_root=tmp_path / ".quarantine",
    )

    assert result["archived"].exists()
    assert result["quarantined"].exists()
    assert result["quarantined"].read_bytes() == b"one"
