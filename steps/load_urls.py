"""Build the runtime collection of archive pages."""

from __future__ import annotations

from typing import Annotated

from zenml import get_step_context, step
from zenml.logger import get_logger

logger = get_logger(__name__)

URL_DOMAINS = {
    "zoomit": "https://www.zoomit.ir",
    "kojaro": "https://www.kojaro.com",
    "zoomg": "https://www.zoomg.ir",
    "pedal": "https://www.pedal.ir",
    "filmzi": "https://www.filmzi.com",
    "zoomon": "https://www.zoomon.ir",
}


@step
def load_urls(
    domain: str = "all",
    first_page: bool = False,
) -> Annotated[list[str], "archive_page_urls"]:
    """Return archive page URLs as one sequence artifact.

    Each archive page is the unit of parallel work. A page is expected to
    contain approximately 20 articles.
    """
    if domain != "all" and domain not in URL_DOMAINS:
        raise ValueError(
            f"Unknown domain {domain!r}. Supported values: {', '.join(sorted(URL_DOMAINS))}"
        )

    selected = list(URL_DOMAINS) if domain == "all" else [domain]
    page_numbers = [1] if first_page else range(1, 501)

    pages: list[str] = []
    for dom in selected:
        base = URL_DOMAINS[dom]
        for page in page_numbers:
            pages.append(
                f"{base}/archive?sort=Newest&publishDate=All&readingTime=All&pageNumber={page}"
            )

    ctx = get_step_context()
    ctx.add_output_metadata(
        output_name="archive_page_urls",
        metadata={
            "domain": domain,
            "first_page": first_page,
            "domains": selected,
            "page_count": len(pages),
        },
    )

    logger.info(
        "archive_pages_loaded domain=%s first_page=%s page_count=%d",
        domain,
        first_page,
        len(pages),
    )
    return pages
