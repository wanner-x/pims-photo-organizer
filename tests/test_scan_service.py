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


def test_scan_can_filter_and_limit_files(tmp_path):
    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "a.jpg").write_bytes(b"jpeg-data")
    (library_root / "b.txt").write_bytes(b"text-data")
    (library_root / "c.png").write_bytes(b"png-data")

    service = ScanService()
    discovered = service.discover_paths(library_root, limit=1, suffixes={".jpg", ".png"})

    assert [path.name for path in discovered] == ["a.jpg"]


def test_scan_limit_stops_before_later_files(tmp_path):
    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "a.jpg").write_bytes(b"jpeg-data")
    (library_root / "b.jpg").write_bytes(b"jpeg-data")

    service = ScanService()
    discovered = service.discover_paths(library_root, limit=1, suffixes={".jpg"})

    assert len(discovered) == 1
