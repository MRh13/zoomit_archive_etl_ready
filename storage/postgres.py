"""PostgreSQL persistence, idempotent deduplication and ingestion claims."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from zenml.logger import get_logger

from storage.config import settings

logger = get_logger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS archive_articles (
    url TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    token TEXT,
    title TEXT,
    title_en TEXT,
    category TEXT,
    description TEXT,
    lead TEXT,
    time_created_from_archive TEXT,
    time_created TEXT,
    reading_time TEXT,
    author TEXT,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    content TEXT,
    image_url TEXT,
    image_alt TEXT,
    cover_image TEXT,
    images JSONB NOT NULL DEFAULT '[]'::jsonb,
    scraped_at TIMESTAMPTZ NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_archive_articles_domain_token
    ON archive_articles (domain, token)
    WHERE token IS NOT NULL AND token <> '';

CREATE INDEX IF NOT EXISTS ix_archive_articles_domain
    ON archive_articles (domain);

ALTER TABLE archive_articles ADD COLUMN IF NOT EXISTS lead TEXT;
ALTER TABLE archive_articles ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE archive_articles ADD COLUMN IF NOT EXISTS image_alt TEXT;
ALTER TABLE archive_articles ADD COLUMN IF NOT EXISTS cover_image TEXT;
ALTER TABLE archive_articles ADD COLUMN IF NOT EXISTS images JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS article_ingestion (
    url TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    token TEXT,
    status TEXT NOT NULL CHECK (status IN ('claimed', 'done', 'failed')),
    claimed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    last_error TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_article_ingestion_status
    ON article_ingestion (status, claimed_at);

CREATE UNIQUE INDEX IF NOT EXISTS ux_article_ingestion_domain_token
    ON article_ingestion (domain, token)
    WHERE token IS NOT NULL AND token <> '';
"""


def postgres_dsn() -> str:
    """Return the PostgreSQL DSN loaded from the environment."""
    dsn = os.getenv("POSTGRES_DSN")
    if dsn is None or not dsn.strip():
        raise RuntimeError(
            "POSTGRES_DSN is not configured. "
            "Example: postgresql://archive_user:archive_password@127.0.0.1:15432/archive"
        )
    return dsn.strip()


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Open a PostgreSQL connection for one transaction scope."""
    with psycopg.connect(postgres_dsn(), row_factory=dict_row) as connection:
        yield connection


def ensure_schema() -> None:
    """Create application tables and indexes if they do not already exist."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
    logger.info("postgres_schema_ready")


def article_exists(cur: psycopg.Cursor, url: str, domain: str, token: str) -> bool:
    """Return whether an article is already persisted by URL or token."""
    cur.execute(
        """
        SELECT 1
        FROM archive_articles
        WHERE url = %s
           OR (%s <> '' AND domain = %s AND token = %s)
        LIMIT 1
        """,
        (url, token or "", domain, token or ""),
    )
    return cur.fetchone() is not None


def claim_article(
    cur: psycopg.Cursor,
    *,
    url: str,
    domain: str,
    token: str,
) -> bool:
    """Atomically claim one URL for scraping.

    The caller should commit the transaction immediately after a group of
    claims so other workers can see the claims before network scraping starts.
    """
    stale_after = settings.claim_stale_after_seconds

    cur.execute(
        """
        INSERT INTO article_ingestion (
            url, domain, token, status, claimed_at, attempt_count
        )
        VALUES (%s, %s, NULLIF(%s, ''), 'claimed', NOW(), 1)
        ON CONFLICT DO NOTHING
        RETURNING url
        """,
        (url, domain, token or ""),
    )
    if cur.fetchone() is not None:
        return True

    cur.execute(
        """
        UPDATE article_ingestion
        SET
            domain = %s,
            token = NULLIF(%s, ''),
            status = 'claimed',
            claimed_at = NOW(),
            completed_at = NULL,
            last_error = NULL,
            attempt_count = article_ingestion.attempt_count + 1,
            updated_at = NOW()
        WHERE url = %s
          AND status <> 'done'
          AND (
              claimed_at IS NULL
              OR claimed_at < NOW() - make_interval(secs => %s)
          )
        RETURNING url
        """,
        (domain, token or "", url, stale_after),
    )
    return cur.fetchone() is not None


def mark_done(cur: psycopg.Cursor, url: str) -> None:
    """Mark an article ingestion claim as successfully completed."""
    cur.execute(
        """
        UPDATE article_ingestion
        SET status = 'done',
            completed_at = NOW(),
            updated_at = NOW(),
            last_error = NULL
        WHERE url = %s
        """,
        (url,),
    )


def mark_failed(cur: psycopg.Cursor, url: str, error: str) -> None:
    """Mark an article ingestion claim as failed and retryable."""
    cur.execute(
        """
        UPDATE article_ingestion
        SET status = 'failed',
            last_error = %s,
            updated_at = NOW()
        WHERE url = %s
        """,
        (error[:4000], url),
    )


def upsert_article(cur: psycopg.Cursor, article: dict[str, Any]) -> None:
    """Insert or update a fully scraped article idempotently."""
    now = datetime.now(timezone.utc)

    cur.execute(
        """
        INSERT INTO archive_articles (
            url,
            domain,
            token,
            title,
            title_en,
            category,
            description,
            lead,
            time_created_from_archive,
            time_created,
            reading_time,
            author,
            tags,
            content,
            image_url,
            image_alt,
            cover_image,
            images,
            scraped_at,
            first_seen_at,
            updated_at
        )
        VALUES (
            %(url)s,
            %(domain)s,
            NULLIF(%(token)s, ''),
            %(title)s,
            %(title_en)s,
            %(category)s,
            %(description)s,
            %(lead)s,
            %(time_created_from_archive)s,
            %(time_created)s,
            %(reading_time)s,
            %(author)s,
            %(tags)s,
            %(content)s,
            %(image_url)s,
            %(image_alt)s,
            %(cover_image)s,
            %(images)s,
            %(scraped_at)s,
            %(first_seen_at)s,
            %(updated_at)s
        )
        ON CONFLICT (url) DO UPDATE SET
            domain = EXCLUDED.domain,
            token = EXCLUDED.token,
            title = EXCLUDED.title,
            title_en = EXCLUDED.title_en,
            category = EXCLUDED.category,
            description = EXCLUDED.description,
            lead = EXCLUDED.lead,
            time_created_from_archive = EXCLUDED.time_created_from_archive,
            time_created = EXCLUDED.time_created,
            reading_time = EXCLUDED.reading_time,
            author = EXCLUDED.author,
            tags = EXCLUDED.tags,
            content = EXCLUDED.content,
            image_url = EXCLUDED.image_url,
            image_alt = EXCLUDED.image_alt,
            cover_image = EXCLUDED.cover_image,
            images = EXCLUDED.images,
            scraped_at = EXCLUDED.scraped_at,
            updated_at = EXCLUDED.updated_at
        """,
        {
            **article,
            "lead": article.get("lead", ""),
            "image_url": article.get("image_url", ""),
            "image_alt": article.get("image_alt", ""),
            "cover_image": article.get("cover_image", ""),
            "tags": Jsonb(article.get("tags", [])),
            "images": Jsonb(article.get("images", [])),
            "scraped_at": article.get("scraped_at", now),
            "first_seen_at": article.get("first_seen_at", now),
            "updated_at": article.get("updated_at", now),
        },
    )
