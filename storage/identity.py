"""Pure helpers for deriving stable archive identities."""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse


def domain_from_url(url: str) -> str:
    """Return the short domain key used by the archive pipeline."""
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    # Known archive family domains.
    if host == "zoomit.ir" or host.endswith(".zoomit.ir"):
        return "zoomit"
    if host == "zoomg.ir" or host.endswith(".zoomg.ir"):
        return "zoomg"
    if host == "pedal.ir" or host.endswith(".pedal.ir"):
        return "pedal"
    if host == "kojaro.com" or host.endswith(".kojaro.com"):
        return "kojaro"
    if host == "filmzi.com" or host.endswith(".filmzi.com"):
        return "filmzi"
    if host == "zoomon.ir" or host.endswith(".zoomon.ir"):
        return "zoomon"

    raise ValueError(f"Unsupported archive domain: {host!r}")


def stable_fingerprint(values: list[str]) -> str:
    """Return a stable short SHA-256 fingerprint for an ordered list."""
    payload = "\n".join(values).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]
