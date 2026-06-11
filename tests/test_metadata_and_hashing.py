import hashlib

from pims_v1.services.hash_service import md5_file_bytes
from pims_v1.services.metadata_service import stat_metadata


def test_md5_file_bytes_matches_hashlib(tmp_path):
    sample = tmp_path / "sample.jpg"
    sample.write_bytes(b"abc123")

    digest = md5_file_bytes(sample)

    assert digest == hashlib.md5(b"abc123").hexdigest()


def test_stat_metadata_returns_file_facts(tmp_path):
    sample = tmp_path / "sample.JPG"
    sample.write_bytes(b"abc123")

    metadata = stat_metadata(sample)

    assert metadata["file_name"] == "sample.JPG"
    assert metadata["file_size"] == 6
    assert metadata["suffix"] == ".jpg"
