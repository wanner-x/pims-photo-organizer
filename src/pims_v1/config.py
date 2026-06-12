from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
        env_prefix="PIMS_",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/pims.db"
    cache_root: str = "./data/.cache"
    quarantine_root: str = "./data/.quarantine"
    logs_root: str = "./data/logs"
    keep_root: str | None = None
    api_token: str | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    wechat_webhook_url: str | None = None
    review_url: str = "http://127.0.0.1:8000/review-ui"


settings = Settings()
