"""Preserve historical adoption semantics while new Company pins use version two."""

from alembic import context, op
from sqlalchemy import text

revision = "0214"
down_revision = "0213"
branch_labels = None
depends_on = None

_ALTER = (
    "ALTER TABLE product_configuration_adoption "
    "ADD COLUMN resolution_version INTEGER NOT NULL DEFAULT 1"
)


def upgrade() -> None:
    # One additive DDL statement; existing rows retain v1 without rewriting their history.
    op.execute(_ALTER)


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError(
            "adoption resolution rollback requires online validation of retained pins"
        )
    # A read guard keeps rollback from silently changing adopted product semantics.
    newer = (
        op.get_bind()
        .execute(
            text(
                "SELECT 1 FROM product_configuration_adoption WHERE resolution_version <> 1 LIMIT 1"
            )
        )
        .first()
    )
    if newer is not None:
        raise RuntimeError("cannot downgrade Catalog after Company-only configuration adoption")
    op.execute("ALTER TABLE product_configuration_adoption DROP COLUMN resolution_version")
