from pims_v1.services.delete_service import move_to_quarantine


def test_move_to_quarantine_preserves_file(tmp_path):
    source = tmp_path / "delete-me.jpg"
    source.write_bytes(b"content")
    quarantine_root = tmp_path / ".quarantine"

    quarantined = move_to_quarantine(source, quarantine_root)

    assert quarantined.exists()
    assert quarantined.read_bytes() == b"content"
    assert not source.exists()


def test_move_to_quarantine_does_not_overwrite_existing_file(tmp_path):
    first = tmp_path / "first" / "same.jpg"
    second = tmp_path / "second" / "same.jpg"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    quarantine_root = tmp_path / ".quarantine"

    first_quarantined = move_to_quarantine(first, quarantine_root)
    second_quarantined = move_to_quarantine(second, quarantine_root)

    assert first_quarantined.read_bytes() == b"first"
    assert second_quarantined.read_bytes() == b"second"
    assert first_quarantined != second_quarantined
