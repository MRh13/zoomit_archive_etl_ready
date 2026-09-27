"""Application configuration for the archive ETL project."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from zenml.logger import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"

# Load .env once when the module is imported.
load_dotenv(ENV_FILE)


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration loaded from environment variables."""

    postgres_dsn: str
    parquet_root: str
    media_root: str
    max_articles_per_page: int
    claim_stale_after_seconds: int
    request_timeout_seconds: int
    download_images: bool
    zenml_logging_verbosity: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Build application settings from environment variables."""
        postgres_dsn = os.getenv("POSTGRES_DSN", "").strip()
        if not postgres_dsn:
            raise RuntimeError(
                "POSTGRES_DSN is not configured. "
                "Copy .env.example to .env and update the credentials."
            )

        download_raw = os.getenv("DOWNLOAD_IMAGES", "true").strip().lower()
        return cls(
            postgres_dsn=postgres_dsn,
            parquet_root=os.getenv(
                "PARQUET_ROOT",
                str(PROJECT_ROOT / "data" / "bronze" / "archive_articles"),
            ),
            media_root=os.getenv(
                "MEDIA_ROOT",
                str(PROJECT_ROOT / "data" / "media"),
            ),
            max_articles_per_page=int(os.getenv("MAX_ARTICLES_PER_PAGE", "20")),
            claim_stale_after_seconds=int(
                os.getenv("CLAIM_STALE_AFTER_SECONDS", "3600")
            ),
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
            download_images=download_raw not in {"0", "false", "no"},
            zenml_logging_verbosity=os.getenv(
                "ZENML_LOGGING_VERBOSITY", "INFO"
            ),
        )


settings = Settings.from_env()
logger.info(
    "configuration_loaded parquet_root=%s media_root=%s max_articles_per_page=%d",
    settings.parquet_root,
    settings.media_root,
    settings.max_articles_per_page,
)
