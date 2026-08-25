"""Application-owned Alembic bootstrap helpers.

The API and workers share one persistent schema.  Keeping migration invocation
here prevents command-line processing scripts from silently creating a schema
that has not been versioned by Alembic.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .config import settings
from .database import engine


# Versions before Alembic used SQLAlchemy's ``Base.metadata.create_all``.  The
# local dataset database may therefore have a complete, unversioned schema.
# Stamp only that known complete shape; any partial/unrecognised schema is left
# untouched rather than risking a destructive or ambiguous migration.
_CALLRADAR_TABLES = frozenset(
    {
        "agents",
        "attention_contributions",
        "call_analyses",
        "calls",
        "customers",
        "evidence",
        "mood_events",
        "topics",
        "transcript_segments",
    }
)


def _alembic_config() -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    # Keep paths absolute because this helper is intentionally usable from the
    # repository root, backend/, or the standalone scripts directory.
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def upgrade_database() -> None:
    """Apply the schema through Alembic, preserving a complete legacy schema.

    A database created by the old metadata bootstrap has no ``alembic_version``
    row.  If—and only if—it already contains every Call-Centre Radar table, it
    is stamped at the initial migration before normal future upgrades run.
    """
    config = _alembic_config()
    with engine.connect() as connection:
        table_names = set(inspect(connection).get_table_names())

    if "alembic_version" not in table_names:
        existing_callradar_tables = _CALLRADAR_TABLES & table_names
        if _CALLRADAR_TABLES.issubset(table_names):
            # This is specifically the pre-Alembic initial schema. Stamp that
            # baseline, then apply any migrations introduced after it. Stamping
            # ``head`` here would silently skip a future 0002 migration.
            command.stamp(config, "0001_initial_schema")
        elif existing_callradar_tables:
            raise RuntimeError(
                "Database has an unversioned partial Call-Centre Radar schema. "
                "Refusing to infer a migration; start with an empty database or migrate it explicitly."
            )

    command.upgrade(config, "head")
