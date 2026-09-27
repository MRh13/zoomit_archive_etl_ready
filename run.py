"""Command-line entry point for the archive ETL pipeline."""

from __future__ import annotations

import argparse

from zenml.logger import get_logger

from pipelines.archive_data_etl import archive_data_etl
from storage.config import settings

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description="Run the ZenML archive ETL.")
    parser.add_argument(
        "--domain",
        default="all",
        choices=["all", "zoomit", "kojaro", "zoomg", "pedal", "filmzi", "zoomon"],
        help="Archive domain to process.",
    )
    parser.add_argument(
        "--first-page",
        action="store_true",
        help="Process only the first archive page per selected domain.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    logger.info(
        "pipeline_start domain=%s first_page=%s batch_size=%d",
        args.domain,
        args.first_page,
        settings.max_articles_per_page,
    )

    archive_data_etl(
        domain=args.domain,
        first_page=args.first_page,
    )

    logger.info("pipeline_finished")
