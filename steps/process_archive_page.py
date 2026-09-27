"""Process one archive page as one ZenML batch without ZenML map().

The page is the scalability boundary: one page -> at most 20 article
candidates → one browser session → multiple short DB transactions → one
bronze Parquet shard. Selectors are Filmzi-derived and apply to every
Zoomit-family domain.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Annotated, Any

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from zenml import step
from zenml.logger import get_logger

from storage.browser import create_driver
from storage.config import settings
from storage.identity import domain_from_url
from storage.images import download_images, media_root
from storage.parquet import write_page_batch
from storage.postgres import (
    article_exists,
    claim_article,
    connect,
    mark_done,
    mark_failed,
    upsert_article,
)
from storage.scraper import extract_anchor_metadata, extract_article, parse_html
from storage.selectors import ARCHIVE_READY_SELECTOR, ARTICLE_READY_SELECTOR

logger = get_logger(__name__)


def _wait_for(driver: Any, css: str) -> None:
    wait = WebDriverWait(driver, settings.request_timeout_seconds)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))


def _parse_driver(driver: Any) -> BeautifulSoup:
    return parse_html(driver.page_source)


def _download_candidate_image(candidate: dict[str, Any], domain: str) -> None:
    image_url = candidate.get("image_url") or ""
    if not image_url:
        candidate["image_path"] = ""
        return
    dest = media_root(settings.media_root) / domain / "anchor_list"
    saved = download_images([{"url": image_url, "alt": candidate.get("image_alt", ""), "kind": "card"}], dest)
    candidate["image_path"] = saved[0]["path"] if saved else ""


def _download_article_images(extracted: dict[str, Any], domain: str) -> None:
    token = extracted.get("token") or "unknown"
    dest = media_root(settings.media_root) / domain / "article_page" / str(token)
    saved = download_images(extracted.get("images") or [], dest)
    extracted["images"] = saved
    extracted["image_paths"] = [item["path"] for item in saved if item.get("path")]
    cover = next((item["path"] for item in saved if item.get("kind") == "cover" and item.get("path")), "")
    if cover:
        extracted["cover_image_path"] = cover
    else:
        extracted["cover_image_path"] = extracted.get("cover_image_path", "")


def _extract_article_from_driver(driver: Any, article: dict[str, Any]) -> dict[str, Any]:
    """Scrape one article using the already-running page-level driver."""
    url = article["url"]
    started = time.perf_counter()

    driver.get(url)
    _wait_for(driver, ARTICLE_READY_SELECTOR)

    soup = _parse_driver(driver)
    extracted = extract_article(soup, article, page_url=url)
    scraped_at = dt.datetime.now(dt.timezone.utc)
    extracted.update(
        {
            "scraped_at": scraped_at,
            "first_seen_at": scraped_at,
            "updated_at": scraped_at,
        }
    )

    if settings.download_images:
        _download_article_images(extracted, extracted.get("domain") or domain_from_url(url))

    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "article_extracted status=success domain=%s url=%s title=%r "
        "words=%d tags=%d images=%d duration_ms=%.1f",
        extracted.get("domain"),
        url,
        extracted.get("title"),
        len((extracted.get("content") or "").split()),
        len(extracted.get("tags") or []),
        len(extracted.get("image_urls") or []),
        duration_ms,
    )
    return extracted


@step(enable_cache=False)
def process_archive_page(
    page_url: str,
    database_ready: str,
) -> Annotated[dict[str, Any], "page_batch_metrics"]:
    """Process one archive page and return compact monitoring metrics."""
    del database_ready  # dependency token; the database step already ran.

    batch_started = time.perf_counter()
    domain = domain_from_url(page_url)
    parquet_path: str | None = None

    logger.info(
        "page_batch_started domain=%s page=%s batch_limit=%d",
        domain,
        page_url,
        settings.max_articles_per_page,
    )

    driver = None
    discovered = skipped_existing = claimed = scraped = persisted = failed = 0
    articles_to_persist: list[dict[str, Any]] = []
    article_errors: list[str] = []

    try:
        driver = create_driver(settings.request_timeout_seconds)
        driver.get(page_url)
        _wait_for(driver, ARCHIVE_READY_SELECTOR)

        page_soup = _parse_driver(driver)
        candidates = extract_anchor_metadata(
            page_url,
            domain,
            page_soup,
            limit=settings.max_articles_per_page,
        )
        discovered = len(candidates)

        logger.info(
            "page_batch_discovered domain=%s page=%s articles=%d",
            domain,
            page_url,
            discovered,
        )

        if settings.download_images:
            for candidate in candidates:
                _download_candidate_image(candidate, domain)

        candidates_to_scrape: list[dict[str, Any]] = []
        with connect() as conn:
            with conn.cursor() as cur:
                for index, candidate in enumerate(candidates, start=1):
                    url = candidate["url"]
                    token = candidate.get("token", "")

                    if article_exists(cur, url, domain, token):
                        skipped_existing += 1
                        logger.info(
                            "article_skipped status=already_ingested index=%d "
                            "domain=%s url=%s",
                            index,
                            domain,
                            url,
                        )
                        continue

                    if not claim_article(
                        cur,
                        url=url,
                        domain=domain,
                        token=token,
                    ):
                        skipped_existing += 1
                        logger.info(
                            "article_skipped status=claimed_or_duplicate index=%d "
                            "domain=%s url=%s",
                            index,
                            domain,
                            url,
                        )
                        continue

                    claimed += 1
                    candidates_to_scrape.append(candidate)

            conn.commit()

        for index, candidate in enumerate(candidates_to_scrape, start=1):
            url = candidate["url"]
            try:
                extracted = _extract_article_from_driver(driver, candidate)
                if not extracted["title"]:
                    raise ValueError("article title is empty")

                if not extracted["content"]:
                    logger.warning(
                        "article_validation status=warning domain=%s url=%s reason=empty_content",
                        domain,
                        url,
                    )

                articles_to_persist.append(extracted)
                scraped += 1
            except Exception as exc:
                failed += 1
                article_errors.append(f"{url}: {exc}")

                with connect() as conn:
                    with conn.cursor() as cur:
                        mark_failed(cur, url, str(exc))
                    conn.commit()

                logger.exception(
                    "article_extracted status=failed index=%d domain=%s url=%s",
                    index,
                    domain,
                    url,
                )

        if articles_to_persist:
            try:
                with connect() as conn:
                    with conn.cursor() as cur:
                        for article in articles_to_persist:
                            upsert_article(cur, article)
                            mark_done(cur, article["url"])
                            persisted += 1
                    conn.commit()
            except Exception as exc:
                logger.exception(
                    "batch_persistence_failed domain=%s page=%s",
                    domain,
                    page_url,
                )

                with connect() as recovery_conn:
                    with recovery_conn.cursor() as recovery_cur:
                        for article in articles_to_persist:
                            mark_failed(recovery_cur, article["url"], str(exc))
                    recovery_conn.commit()

                raise

        parquet_path = write_page_batch(
            domain=domain,
            page_url=page_url,
            articles=articles_to_persist,
        )

    except Exception:
        logger.exception(
            "page_batch_failed domain=%s page=%s",
            domain,
            page_url,
        )
        raise
    finally:
        if driver is not None:
            try:
                driver.quit()
            except BaseException:
                logger.warning("webdriver_close_failed domain=%s page=%s", domain, page_url)

    duration_ms = (time.perf_counter() - batch_started) * 1000

    metrics = {
        "domain": domain,
        "page_url": page_url,
        "discovered": discovered,
        "skipped_existing": skipped_existing,
        "claimed": claimed,
        "scraped": scraped,
        "persisted": persisted,
        "failed": failed,
        "duration_ms": round(duration_ms, 2),
        "parquet_path": parquet_path or "",
        "media_root": str(Path(settings.media_root) / domain),
    }

    from zenml import get_step_context

    ctx = get_step_context()
    ctx.add_output_metadata(
        output_name="page_batch_metrics",
        metadata={
            **metrics,
            "error_count": len(article_errors),
        },
    )

    logger.info(
        "page_batch_finished domain=%s page=%s discovered=%d skipped=%d "
        "scraped=%d persisted=%d failed=%d duration_ms=%.1f",
        domain,
        page_url,
        discovered,
        skipped_existing,
        scraped,
        persisted,
        failed,
        duration_ms,
    )

    if article_errors:
        logger.warning(
            "page_batch_article_errors domain=%s page=%s error_count=%d",
            domain,
            page_url,
            len(article_errors),
        )

    return metrics
