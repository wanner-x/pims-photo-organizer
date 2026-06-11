from pims_v1.services.delete_service import move_to_quarantine


def test_move_to_quarantine_preserves_file(tmp_path):
    source = tmp_path / "delete-me.jpg"
    source.write_bytes(b"content")
    quarantine_root = tmp_path / ".quarantine"

    quarantined = move_to_quarantine(source, quarantine_root)

    assert quarantined.exists()
    assert quarantined.read_bytes() == b"content"
    assert not source.exists()
