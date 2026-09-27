"""Parquet bronze persistence using fsspec-compatible paths."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fsspec
import pyarrow as pa
import pyarrow.parquet as pq
from zenml.logger import get_logger

from storage.config import settings
from storage.identity import stable_fingerprint

logger = get_logger(__name__)


def _json_ready(article: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested lists so every shard has a scalar-friendly schema."""
    row = dict(article)
    for key in ("images", "image_urls", "image_paths", "tags"):
        value = row.get(key)
        if isinstance(value, list):
            row[key] = json.dumps(value, ensure_ascii=False)
    return row


def write_page_batch(
    *,
    domain: str,
    page_url: str,
    articles: list[dict[str, Any]],
) -> str | None:
    """Write newly scraped articles for one archive page as one Parquet shard.

    Returns the path of the written object, or ``None`` when the batch
    contains no new articles.
    """
    if not articles:
        logger.info(
            "parquet_skip domain=%s reason=no_new_articles page=%s",
            domain,
            page_url,
        )
        return None

    rows = [_json_ready(article) for article in articles]
    urls = [str(article["url"]) for article in articles]
    fingerprint = stable_fingerprint(urls)
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    base = settings.parquet_root.rstrip("/")
    output = f"{base}/domain={domain}/run_date={run_date}/page_{fingerprint}.parquet"

    table = pa.Table.from_pylist(rows)

    fs, path = fsspec.core.url_to_fs(output)
    parent = str(Path(path).parent).replace("\\", "/")
    if hasattr(fs, "makedirs"):
        fs.makedirs(parent, exist_ok=True)

    if fs.exists(path):
        logger.info(
            "parquet_exists domain=%s path=%s rows=%d",
            domain,
            output,
            len(articles),
        )
        return output

    with fs.open(path, "wb") as handle:
        pq.write_table(table, handle, compression="zstd")

    logger.info(
        "parquet_written domain=%s path=%s rows=%d",
        domain,
        output,
        len(articles),
    )
    return output
