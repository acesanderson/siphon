"""
Database initialization utility for the Siphon server persistence layer. This script provisions the PostgreSQL database schema by reflecting the declarative ORM model definitions and creating corresponding tables through SQLAlchemy's metadata API.

The script uses the centralized database connection engine and declarative base class defined in the connection module to ensure schema consistency across the application. It wraps the core `create_all()` operation with logging to provide visibility into the initialization process, making it suitable for both manual setup and automated deployment workflows.

This is typically invoked during server startup or development environment setup to prepare the database for storing ProcessedContent records. The repository layer and other data access components depend on this initialization step to ensure all required tables exist before the application begins processing and persisting ingested content.
"""

# database/postgres/setup.py
from siphon_server.database.postgres.connection import Base, engine
from siphon_server.database.postgres.models import (
    ProcessedContentORM,  # MUST import!
    QueryHistoryORM,  # MUST import!
)
import logging
import os

# Set up logging
log_level = int(os.getenv("PYTHON_LOG_LEVEL", "2"))
levels = {1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}
logging.basicConfig(
    level=levels.get(log_level, logging.INFO), format="%(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


def create_tables():
    """Create all database tables."""
    logger.info(f"Creating tables in database: {engine.url.database}")
    logger.info(f"Models registered: {Base.metadata.tables.keys()}")

    Base.metadata.create_all(engine)

    logger.info("Tables created successfully!")


def ensure_indexes():
    """Ensure all indexes exist on an already-provisioned database (idempotent)."""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_pc_metadata_gin "
            "ON processed_content USING gin (content_metadata)"
        ))
        conn.commit()
    logger.info("Indexes verified.")


if __name__ == "__main__":
    create_tables()
    ensure_indexes()
