from pims_v1.services.archive_service import copy_to_archive, verify_archive_copy


def test_copy_to_archive_writes_destination_file(tmp_path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"archive-me")
    archive_root = tmp_path / "archive"

    destination = copy_to_archive(source, archive_root / "set1" / source.name)

    assert destination.exists()
    assert destination.read_bytes() == b"archive-me"
    assert verify_archive_copy(source, destination) is True
