from pathlib import Path

from pims_v1.services.scan_service import ScanService


def test_scan_discovers_new_files(tmp_path):
    library_root = tmp_path / "library"
    library_root.mkdir()
    sample_file = library_root / "a.jpg"
    sample_file.write_bytes(b"jpeg-data")

    service = ScanService()
    discovered = service.discover_paths(Path(library_root))

    assert [path.name for path in discovered] == ["a.jpg"]
