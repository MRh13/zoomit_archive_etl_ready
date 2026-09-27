"""Download article and archive-card images into domain folders."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def media_root(override: str | Path | None = None) -> Path:
    """Return the directory that stores downloaded media files."""
    if override:
        return Path(override)
    return PROJECT_ROOT / "data" / "media"


def _extension_from_url(url: str, content_type: str = "") -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
    if guessed == ".jpe":
        return ".jpg"
    return guessed or ".jpg"


def filename_for(url: str, *, prefix: str = "", content_type: str = "") -> str:
    """Build a stable filename from the URL path plus a short hash."""
    parsed = urlparse(url)
    stem = Path(parsed.path).stem or "image"
    stem = SAFE_NAME_RE.sub("-", stem).strip("-")[:80] or "image"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    ext = _extension_from_url(url, content_type)
    name = f"{stem}-{digest}{ext}"
    if prefix:
        name = f"{prefix}-{name}"
    return name


def download_image(
    url: str,
    dest_dir: Path,
    *,
    timeout: int = 20,
    prefix: str = "",
) -> Path | None:
    """Download one image and return the local path, or None on failure."""
    if not url or url.startswith("data:"):
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    tentative = dest_dir / filename_for(url, prefix=prefix)
    if tentative.exists() and tentative.stat().st_size > 0:
        return tentative

    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
            content_type = response.headers.get("Content-Type", "")
    except Exception:
        return None

    if not payload:
        return None

    target = dest_dir / filename_for(url, prefix=prefix, content_type=content_type)
    target.write_bytes(payload)
    return target


def download_images(
    items: list[dict[str, Any]] | list[str],
    dest_dir: Path,
    *,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    """Download a list of image dicts (or URLs) into ``dest_dir``.

    Each returned dict contains ``url``, ``alt``, ``kind`` and ``path``.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for index, item in enumerate(items, start=1):
        if isinstance(item, str):
            record: dict[str, Any] = {"url": item, "alt": "", "kind": "image"}
        else:
            record = dict(item)

        url = record.get("url") or ""
        path = download_image(
            url,
            dest_dir,
            timeout=timeout,
            prefix=f"{index:02d}",
        )
        record["path"] = str(path) if path else ""
        results.append(record)

    return results
