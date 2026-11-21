"""
Database configuration and session management.
"""
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData, text
from sqlalchemy.exc import SQLAlchemyError
from typing import AsyncGenerator
from app.core.config import settings

logger = logging.getLogger(__name__)

# Naming convention for constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    metadata = metadata


def _prepare_database_url(url: str) -> tuple[str, dict]:
    """Normalize the database URL and translate options for asyncpg.

    * Plain ``postgresql://`` / ``postgres://`` / ``postgresql+psycopg2://``
      URLs are switched to the ``asyncpg`` driver (required by the async engine).
    * asyncpg rejects ``sslmode=...`` as a connection keyword, so it is removed
      from the URL and converted into an ``ssl`` connect argument.
    """
    if url.startswith("postgresql+psycopg2://"):
        url = "postgresql+asyncpg://" + url[len("postgresql+psycopg2://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]

    if not url.startswith("postgresql+asyncpg"):
        return url, {}

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    connect_args: dict = {}

    sslmode = query.pop("sslmode", None)
    ssl_value = query.pop("ssl", None)
    if sslmode not in (None, "disable") or ssl_value not in (None, "false", "0"):
        connect_args["ssl"] = True

    # Supabase's shared pooler runs PgBouncer in transaction mode, which does
    # not support server-side prepared statements. Disable SQLAlchemy's and
    # asyncpg's caches so a connection does not reference a prepared statement
    # created on a different pooled backend.
    connect_args["statement_cache_size"] = 0
    # Use unnamed prepared statements. Named statements live on the PgBouncer
    # backend and can collide when SQLAlchemy later reuses a pooled connection.
    connect_args["prepared_statement_name_func"] = lambda: ""
    query["prepared_statement_cache_size"] = "0"

    cleaned = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
    return cleaned, connect_args


_database_url, _connect_args = _prepare_database_url(settings.database_url)

_engine_kwargs = {
    "echo": settings.debug,
    "pool_pre_ping": True,
}
if "sqlite" not in _database_url:
    _engine_kwargs["pool_size"] = settings.database_pool_size
    _engine_kwargs["max_overflow"] = settings.database_max_overflow

# Async engine
engine = create_async_engine(
    _database_url,
    connect_args=_connect_args,
    **_engine_kwargs,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


_METRICS_BIGINT_COLUMNS = (
    "memory_used_bytes",
    "memory_total_bytes",
    "memory_available_bytes",
    "swap_used_bytes",
    "swap_total_bytes",
    "disk_used_bytes",
    "disk_total_bytes",
    "disk_free_bytes",
    "disk_read_bytes_sec",
    "disk_write_bytes_sec",
    "network_sent_bytes_sec",
    "network_recv_bytes_sec",
    "network_sent_total",
    "network_recv_total",
    "gpu_memory_used_bytes",
    "gpu_memory_total_bytes",
)


async def init_db() -> None:
    """Initialize database tables and widen legacy metrics columns."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Existing deployments created these columns as 32-bit INTEGER. A 16 GB
    # machine or a multi-terabyte disk overflows that range, so widen them to
    # BIGINT. Each ALTER runs in its own transaction so one permission failure
    # does not abort the rest of startup.
    if engine.dialect.name == "postgresql":
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT column_name, data_type "
                        "FROM information_schema.columns "
                        "WHERE table_name = 'system_metrics'"
                    )
                )
            ).fetchall()
        column_types = {row[0]: row[1] for row in rows}

        for column in _METRICS_BIGINT_COLUMNS:
            if column_types.get(column) == "bigint":
                continue
            try:
                async with engine.begin() as conn:
                    await conn.execute(
                        text(
                            f"ALTER TABLE system_metrics "
                            f"ALTER COLUMN {column} TYPE BIGINT"
                        )
                    )
            except SQLAlchemyError as exc:  # pragma: no cover - schema dependent
                logger.warning(
                    "Could not widen system_metrics.%s to BIGINT: %s", column, exc
                )


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()