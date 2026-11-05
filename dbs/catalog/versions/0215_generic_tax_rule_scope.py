"""Explicit generic templates; existing rules keep their specific classifications."""

from alembic import context, op
from sqlalchemy import text

revision = "0215"
down_revision = "0214"
branch_labels = None
depends_on = None

_ALTER = (
    "ALTER TABLE tax_rule ADD COLUMN classification_scope VARCHAR(8) NOT NULL "
    "DEFAULT 'SPECIFIC', ADD CONSTRAINT ck_tax_rule_classification_scope "
    "CHECK (classification_scope IN ('SPECIFIC','ANY'))"
)


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("generic tax scope rollback requires online validation")
    generic = (
        op.get_bind()
        .execute(
            text(
                "SELECT 1 FROM tax_rule WHERE classification_scope <> 'SPECIFIC' LIMIT 1"
            )
        )
        .first()
    )
    if generic is not None:
        raise RuntimeError("cannot downgrade Catalog while generic tax templates exist")
    op.execute(
        "ALTER TABLE tax_rule DROP CHECK ck_tax_rule_classification_scope, "
        "DROP COLUMN classification_scope"
    )
