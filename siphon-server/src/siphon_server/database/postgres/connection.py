from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dbclients.discovery.host import get_network_context, NetworkContext
import os
import json
import time
from pathlib import Path

# SQLAlchemy Base class
Base = declarative_base()


def get_cached_network_context(cache_ttl: int = 300) -> NetworkContext:
    """
    Get network context with caching to avoid slow network discovery on every CLI invocation.

    Args:
        cache_ttl: Cache time-to-live in seconds (default: 5 minutes)

    Returns:
        NetworkContext object
    """
    cache_dir = Path.home() / ".cache" / "siphon"
    cache_file = cache_dir / "network_context.json"

    # Check if cache exists and is fresh
    if cache_file.exists():
        cache_age = time.time() - cache_file.stat().st_mtime
        if cache_age < cache_ttl:
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    return NetworkContext(**data)
            except Exception:
                pass  # Fall through to refresh cache

    # Cache miss or stale - do expensive network discovery
    context = get_network_context()

    # Save to cache
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w") as f:
            # Convert dataclass to dict for JSON serialization
            data = {
                "local_hostname": context.local_hostname,
                "is_on_vpn": context.is_on_vpn,
                "is_local": context.is_local,
                "is_database_server": context.is_database_server,
                "is_siphon_server": context.is_siphon_server,
                "preferred_host": context.preferred_host,
                "siphon_server": context.siphon_server,
                "vpn_ip": context.vpn_ip,
                "public_ip": context.public_ip,
                "local_ip": context.local_ip,
            }
            json.dump(data, f)
    except Exception:
        pass  # Don't fail if we can't cache

    return context


# Get network context for DB connection (with caching!)
network_context = get_cached_network_context()

# Constants for DB connection
SERVER_IP = network_context.preferred_host
DBNAME = "siphon2"
USER = "user"
PASSWORD = os.getenv("POSTGRES_PASSWORD")
USERNAME = os.getenv("POSTGRES_USERNAME")
PORT = 5432

if any(v is None for v in [PASSWORD, USERNAME]):
    raise ValueError(
        "POSTGRES_PASSWORD and POSTGRES_USERNAME environment variables must be set"
    )

POSTGRES_URL = f"postgresql://{USERNAME}:{PASSWORD}@{SERVER_IP}:{PORT}/{DBNAME}"


engine = create_engine(
    POSTGRES_URL,
    echo=False,
)


SessionLocal = sessionmaker(bind=engine)


def get_db():
    """FastAPI dependency for routes"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
