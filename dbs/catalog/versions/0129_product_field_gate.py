"""Carry product definition adoption requirements."""

from alembic import op

revision = "0129"
down_revision = "0128"
branch_labels = None
depends_on = None
_ALTER = """ALTER TABLE custom_field_definition_projection
ADD COLUMN requires_adoption BOOL NOT NULL DEFAULT 0"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    raise RuntimeError("Retain adoption gates; downgrade requires operator review")
