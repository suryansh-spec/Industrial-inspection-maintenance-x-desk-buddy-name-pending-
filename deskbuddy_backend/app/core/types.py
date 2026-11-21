"""
Database column types that work on PostgreSQL and SQLite.

The models use these portable types so the same schema can be used with
PostgreSQL in production and SQLite in the test suite.
"""
from sqlalchemy import JSON, Uuid
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB


def UUID(as_uuid: bool = True, **kwargs):
    """Return a dialect-portable UUID column type."""
    return Uuid(as_uuid=as_uuid, **kwargs)


class JSONB(JSON):
    """JSONB on PostgreSQL, plain JSON on other dialects (e.g. SQLite)."""

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())
