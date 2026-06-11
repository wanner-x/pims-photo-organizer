from pims_v1.config import Settings


def test_settings_use_local_defaults(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'pims.db'}",
        cache_root=str(tmp_path / ".cache"),
        quarantine_root=str(tmp_path / ".quarantine"),
    )

    assert settings.database_url.startswith("sqlite:///")
    assert settings.cache_root.endswith(".cache")
    assert settings.quarantine_root.endswith(".quarantine")
