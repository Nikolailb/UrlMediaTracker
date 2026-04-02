from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./tracker.db"
    DEFAULT_CHECK_INTERVAL_MIN: int = 60
    PROBE_REQUEST_TIMEOUT: float = 10.0
    PROBE_DELAY_SECONDS: float = 1.0
    # Maximum number of chapters to probe ahead during a single check run
    MAX_PROBE_AHEAD: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
