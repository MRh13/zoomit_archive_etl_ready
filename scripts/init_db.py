"""Initialize the PostgreSQL schema outside a ZenML pipeline."""

from storage.postgres import ensure_schema
from zenml.logger import get_logger

logger = get_logger(__name__)


if __name__ == "__main__":
    logger.info("init_db_started")
    ensure_schema()
    logger.info("init_db_finished")
