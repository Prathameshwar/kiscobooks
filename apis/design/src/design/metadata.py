"""Only this service's migrated tables belong in its metadata and readiness checks.

Listed literally rather than discovered from the models: the readiness probe compares
this set against the live schema, and a set derived from whatever happens to be imported
would shrink silently when an import moves.
"""

from billing_platform.db.base import NAMING_CONVENTION, Base
from sqlalchemy import MetaData

from design import models  # noqa: F401  registers the mapped tables on Base.metadata

#: The alembic revision this build expects. Readiness fails if the database is elsewhere.
MIGRATION_HEAD = "0009"

TABLES: frozenset[str] = frozenset(
    {
        # The outbox is this service's own table, not a shared one: audit events commit
        # with the row they describe (CLAUDE.md §6.8) and a publisher drains them.
        "outbox",
        "invoice_template",
        "invoice_template_version",
        "invoice_template_assignment",
        "invoice_template_asset",
        "invoice_template_component",
        "invoice_render_snapshot",
    }
)


def service_metadata() -> MetaData:
    """Metadata containing only design's tables, for alembic autogenerate."""
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    for name in sorted(TABLES):
        Base.metadata.tables[name].to_metadata(metadata)
    return metadata
