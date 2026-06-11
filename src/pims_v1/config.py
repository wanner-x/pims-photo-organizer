from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PIMS_", extra="ignore")

    database_url: str = "sqlite:///./data/pims.db"
    cache_root: str = "./data/.cache"
    quarantine_root: str = "./data/.quarantine"


settings = Settings()
