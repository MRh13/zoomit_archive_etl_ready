"""Check the application-level PostgreSQL TCP connection."""

from __future__ import annotations

import psycopg
from zenml.logger import get_logger

from storage.postgres import postgres_dsn

logger = get_logger(__name__)


if __name__ == "__main__":
    dsn = postgres_dsn()
    logger.info("postgres_connection_check_started")

    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT current_user, current_database(), version()"
        ).fetchone()

    logger.info(
        "postgres_connection_check_ok user=%s database=%s",
        row[0],
        row[1],
    )
    print(row[2])
