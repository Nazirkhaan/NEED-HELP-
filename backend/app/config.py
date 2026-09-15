"""Application configuration loaded from environment variables / .env file."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), extra="ignore"
    )

    database_url: str = "postgresql://sih:sih@localhost:5433/sih26044"
    jwt_secret: str = "change-me-in-production"
    jwt_expires_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:3000"
    # auto | fastembed | tfidf
    embedding_provider: str = "auto"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
