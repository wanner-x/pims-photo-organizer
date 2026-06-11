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


def test_settings_accept_deepseek_api_key():
    settings = Settings(deepseek_api_key="test-key")

    assert settings.deepseek_api_key == "test-key"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.deepseek_model == "deepseek-chat"
