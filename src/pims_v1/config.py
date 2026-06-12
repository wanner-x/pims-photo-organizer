from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PIMS_",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/pims.db"
    cache_root: str = "./data/.cache"
    quarantine_root: str = "./data/.quarantine"
    api_token: str | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    wechat_webhook_url: str | None = None


settings = Settings()
