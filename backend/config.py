from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./tracker.db"
    DEFAULT_CHECK_INTERVAL_MIN: int = 60
    PROBE_REQUEST_TIMEOUT: float = 10.0
    PROBE_DELAY_SECONDS: float = 0.5
    # Coarse step size for the two-phase chapter probe (probe N+STEP, N+2*STEP…
    # until miss, then refine with step-1 to find the exact last chapter)
    PROBE_COARSE_STEP: int = 5
    # Safety cap: maximum number of coarse steps per check run.
    # Total look-ahead = PROBE_COARSE_STEP * MAX_COARSE_STEPS chapters.
    MAX_COARSE_STEPS: int = 100
    # Hard wall-clock timeout for a single probe run (seconds).
    MAX_PROBE_DURATION_SECONDS: float = 60.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
