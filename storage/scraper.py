"""Pure HTML extractors for archive lists and article pages.

These helpers take a BeautifulSoup document and return plain dicts. They
do not touch the network, Selenium, PostgreSQL or ZenML, so they can be
unit-tested against saved Filmzi HTML fixtures and reused for every
Zoomit-family domain.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from storage.identity import domain_from_url
from storage.selectors import (
    ARCHIVE_ARTICLE_CARD_FALLBACK_SELECTOR,
    ARCHIVE_ARTICLE_CARD_SELECTOR,
    ARCHIVE_ARTICLE_LIST_SELECTOR,
    ARCHIVE_CARD_DESCRIPTION_SELECTOR,
    ARCHIVE_CARD_IMAGE_SELECTOR,
    ARCHIVE_CARD_META_SELECTOR,
    ARCHIVE_CARD_TITLE_SELECTOR,
    ARTICLE_AUTHOR_LINK_SELECTOR,
    ARTICLE_AUTHOR_SELECTOR,
    ARTICLE_BREADCRUMB_SELECTOR,
    ARTICLE_COVER_SELECTOR,
    ARTICLE_FIGURE_IMAGE_SELECTOR,
    ARTICLE_LEAD_SELECTOR,
    ARTICLE_PARAGRAPH_SELECTOR,
    ARTICLE_PATH_RE,
    ARTICLE_PUBLISHED_TIME_SELECTOR,
    ARTICLE_ROOT_SELECTOR,
    ARTICLE_TIME_META_SELECTOR,
    ARTICLE_TITLE_SELECTOR,
)

BASE_DOMAINS = {
    "zoomit": "https://www.zoomit.ir",
    "zoomg": "https://www.zoomg.ir",
    "pedal": "https://www.pedal.ir",
    "kojaro": "https://www.kojaro.com",
    "filmzi": "https://www.filmzi.com",
    "zoomon": "https://www.zoomon.ir",
}


def parse_html(html: str) -> BeautifulSoup:
    """Parse a saved or live HTML document, ignoring notebook dump prefixes."""
    start = html.find("<html")
    if start == -1:
        start = html.find("<HTML")
    cleaned = html[start:] if start != -1 else html
    end = cleaned.rfind("</html>")
    if end != -1:
        cleaned = cleaned[: end + len("</html>")]
    return BeautifulSoup(cleaned, "lxml")


def full_article_url(href: str, domain: str) -> str:
    """Convert a relative article href into an absolute URL."""
    href = (href or "").strip()
    if href.startswith(("http://", "https://")):
        return href
    try:
        base = BASE_DOMAINS[domain]
    except KeyError as exc:
        raise ValueError(f"Unsupported domain: {domain!r}") from exc
    return urljoin(base.rstrip("/") + "/", href.lstrip("/"))


def extract_token_metadata(href: str) -> tuple[str, str, str]:
    """Return ``(category, token, title_en)`` from an article path or URL."""
    path = href.strip()
    parsed = urlparse(path)
    if parsed.scheme:
        path = parsed.path
    match = ARTICLE_PATH_RE.match(path)
    if not match:
        return "", "", ""
    category, token, slug = match.group(1), match.group(2), match.group(3)
    return category, token, slug.replace("-", " ")


def is_article_href(href: str | None) -> bool:
    """True when href looks like ``/{category}/{id}-{slug}/``."""
    if not href:
        return False
    path = href.strip()
    parsed = urlparse(path)
    if parsed.scheme:
        path = parsed.path
    return ARTICLE_PATH_RE.match(path) is not None


def best_image_url(img: Tag | None, base_url: str = "") -> str:
    """Pick the largest ``srcset`` candidate, otherwise ``src``."""
    if img is None:
        return ""

    candidates: list[tuple[int, str]] = []
    srcset = img.get("srcset") or ""
    for part in srcset.split(","):
        piece = part.strip()
        if not piece:
            continue
        bits = piece.split()
        url = bits[0]
        width = 0
        if len(bits) > 1 and bits[1].endswith("w"):
            try:
                width = int(bits[1][:-1])
            except ValueError:
                width = 0
        candidates.append((width, url))

    if candidates:
        candidates.sort()
        url = candidates[-1][1]
    else:
        url = (img.get("src") or "").strip()

    if url.startswith("//"):
        url = "https:" + url
    if url and base_url and not url.startswith(("http://", "https://", "data:")):
        url = urljoin(base_url, url)
    return url


def _text(node: Tag | None) -> str:
    return node.get_text(" ", strip=True) if node is not None else ""


def _article_cards(soup: BeautifulSoup) -> list[Tag]:
    article_list = soup.select_one(ARCHIVE_ARTICLE_LIST_SELECTOR)
    if article_list is not None:
        cards = article_list.select(ARCHIVE_ARTICLE_CARD_SELECTOR)
        if cards:
            return cards
        cards = article_list.select("a[href]")
        if cards:
            return cards
    return soup.select(ARCHIVE_ARTICLE_CARD_FALLBACK_SELECTOR)


def extract_anchor_metadata(
    page_url: str,
    domain: str,
    soup: BeautifulSoup,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Extract article candidates from an archive listing page."""
    candidates: list[dict[str, Any]] = []

    for index, anchor in enumerate(_article_cards(soup), start=1):
        href = (anchor.get("href") or "").strip()
        if not is_article_href(href):
            continue

        if limit is not None and len(candidates) >= limit:
            break

        description_tag = anchor.select_one(ARCHIVE_CARD_DESCRIPTION_SELECTOR)
        title_tag = None
        if description_tag is not None:
            title_tag = description_tag.find_previous("span")
        if title_tag is None:
            title_tag = anchor.select_one(ARCHIVE_CARD_TITLE_SELECTOR)

        image_tag = anchor.select_one(ARCHIVE_CARD_IMAGE_SELECTOR)
        meta_tags = anchor.select(ARCHIVE_CARD_META_SELECTOR)
        time_created = (
            _text(meta_tags[1]) if len(meta_tags) >= 2 else _text(meta_tags[0])
            if meta_tags
            else ""
        )

        category, token, title_en = extract_token_metadata(href)
        article_url = full_article_url(href, domain)

        candidates.append(
            {
                "title": _text(title_tag),
                "title_en": title_en,
                "time_created_from_archive": time_created,
                "url": article_url,
                "token": token,
                "category": category,
                "description": _text(description_tag),
                "image_url": best_image_url(image_tag, page_url),
                "image_alt": (image_tag.get("alt") or "").strip() if image_tag else "",
                "source_page_url": page_url,
                "card_index": index,
            }
        )

    return candidates


def _article_root(soup: BeautifulSoup) -> Tag:
    return soup.select_one(ARTICLE_ROOT_SELECTOR) or soup


def extract_article(
    soup: BeautifulSoup,
    article: dict[str, Any] | None = None,
    *,
    page_url: str = "",
) -> dict[str, Any]:
    """Extract the fields of a single article page."""
    seed = dict(article or {})
    url = page_url or seed.get("url") or ""
    root = _article_root(soup)

    title_tag = root.select_one(ARTICLE_TITLE_SELECTOR) or soup.select_one("h1")
    title = _text(title_tag) or seed.get("title", "")

    lead = _text(root.select_one(ARTICLE_LEAD_SELECTOR))

    author_tag = root.select_one(ARTICLE_AUTHOR_SELECTOR)
    author = _text(author_tag)
    if not author:
        author_link = root.select_one(ARTICLE_AUTHOR_LINK_SELECTOR)
        author = _text(author_link)

    time_tag = root.select_one(ARTICLE_PUBLISHED_TIME_SELECTOR)
    time_created = _text(time_tag)
    reading_time = ""
    time_metas = root.select(ARTICLE_TIME_META_SELECTOR)
    if not time_created and time_metas:
        time_created = _text(time_metas[0])
    if len(time_metas) >= 2:
        reading_time = _text(time_metas[1])
    elif time_metas and time_created and _text(time_metas[0]) != time_created:
        reading_time = _text(time_metas[0])

    tags: list[str] = []
    for crumb in root.select(ARTICLE_BREADCRUMB_SELECTOR):
        label = _text(crumb)
        href = crumb.get("href") or ""
        if not label or href in {"/", ""}:
            continue
        if label == title:
            continue
        if label not in tags:
            tags.append(label)

    paragraphs = root.select(ARTICLE_PARAGRAPH_SELECTOR)
    content = "\n".join(text for text in (_text(p) for p in paragraphs) if text)

    cover_tag = soup.select_one(ARTICLE_COVER_SELECTOR)
    cover_url = best_image_url(cover_tag, url)

    images: list[dict[str, str]] = []
    seen: set[str] = set()
    if cover_url:
        images.append(
            {
                "url": cover_url,
                "alt": (cover_tag.get("alt") or "").strip() if cover_tag else "",
                "kind": "cover",
            }
        )
        seen.add(cover_url)

    for img in soup.select(ARTICLE_FIGURE_IMAGE_SELECTOR):
        img_url = best_image_url(img, url)
        if not img_url or img_url in seen:
            continue
        if img_url.startswith("data:"):
            continue
        seen.add(img_url)
        images.append(
            {
                "url": img_url,
                "alt": (img.get("alt") or "").strip(),
                "kind": "figure",
            }
        )

    if not seed.get("category") and url:
        category, token, title_en = extract_token_metadata(url)
        seed.setdefault("category", category)
        seed.setdefault("token", token)
        seed.setdefault("title_en", title_en)

    domain = seed.get("domain") or (domain_from_url(url) if url else "")

    return {
        **seed,
        "title": title,
        "lead": lead,
        "tags": tags,
        "time_created": time_created,
        "reading_time": reading_time,
        "author": author,
        "content": content,
        "cover_image": cover_url,
        "images": images,
        "image_urls": [item["url"] for item in images],
        "image_path": seed.get("image_path", ""),
        "image_paths": list(seed.get("image_paths") or []),
        "cover_image_path": seed.get("cover_image_path", ""),
        "domain": domain,
        "url": url or seed.get("url", ""),
    }
