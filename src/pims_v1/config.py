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
    max_image_pixels: int = 300_000_000
    # How to remove redundant byte-identical (exact MD5) duplicates:
    # "quarantine" keeps a reversible copy in quarantine_root; "delete" removes
    # the redundant copy outright (only ever the copies that are not the kept one).
    duplicate_action: str = "quarantine"
    # When rule/AI planners disagree but no R18/content risk is flagged, auto-apply
    # the AI plan if the AI confidence is at least this high (gives AI more authority).
    ai_auto_apply_min_confidence: float = 0.85
    # Number of concurrent workers used to read+hash images during pHash processing.
    # pHash is NAS-I/O bound, so concurrency hides read latency. DB writes stay
    # single-threaded. 1 disables concurrency (original sequential behaviour).
    phash_concurrency: int = 1
    api_token: str | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_reasoning_effort: str = "low"
    deepseek_thinking_enabled: bool = False
    deepseek_max_tokens: int = 600
    ai_suggest_limit: int = 0
    auto_quarantine_limit: int = 0
    r18_provider: str = "auto"
    r18_sample_limit: int = 7
    r18_high_threshold: float = 0.82
    r18_review_threshold: float = 0.55
    r18_scan_limit: int = 0
    # NSFW detection backend for the R18 scan chain: "heuristic" (default,
    # unchanged behaviour) or "onnx" (local NudeNet classifier inference).
    # Only consulted while r18_provider stays "auto".
    nsfw_backend: str = "heuristic"
    nsfw_onnx_model_path: str = "./data/models/nudenet_classifier_model.onnx"
    wechat_webhook_url: str | None = None
    # Max WeChat webhook messages per rolling hour; sends beyond the budget are
    # deferred (records marked "throttled" are retried by a later workflow run).
    wechat_hourly_limit: int = 3
    # When enabled, per-batch approval notifications are queued and flushed as
    # one daily digest message at the end of the safe workflow.
    wechat_digest: bool = False
    review_url: str = "http://127.0.0.1:8000/review-ui"


settings = Settings()
