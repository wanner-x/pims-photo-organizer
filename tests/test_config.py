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
    assert settings.deepseek_model == "deepseek-v4-pro"
    assert settings.deepseek_reasoning_effort == "high"
    assert settings.deepseek_thinking_enabled is True


def test_settings_accept_wechat_webhook_url():
    settings = Settings(wechat_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test")

    assert settings.wechat_webhook_url.endswith("key=test")


def test_settings_accept_review_url():
    settings = Settings(review_url="http://192.168.31.98:8000/review-ui")

    assert settings.review_url == "http://192.168.31.98:8000/review-ui"


def test_settings_accept_keep_root():
    settings = Settings(keep_root="\\\\192.168.31.10\\personal_folder\\网络写真集")

    assert settings.keep_root.endswith("网络写真集")


def test_settings_load_bom_env_file_keep_root(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "PIMS_KEEP_ROOT=\\\\192.168.31.10\\personal_folder\\网络写真集\n",
        encoding="utf-8-sig",
    )

    settings = Settings(_env_file=env_file)

    assert settings.keep_root == "\\\\192.168.31.10\\personal_folder\\网络写真集"
