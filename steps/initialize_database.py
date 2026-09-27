"""ZenML step that ensures the PostgreSQL schema exists before mapping."""

from __future__ import annotations

from typing import Annotated

from zenml import step
from zenml.logger import get_logger

from storage.postgres import ensure_schema

logger = get_logger(__name__)


@step(enable_cache=False)
def initialize_database() -> Annotated[str, "database_ready"]:
    """Create the application schema and return a small dependency token."""
    ensure_schema()
    logger.info("database_initialized")
    return "ready"
