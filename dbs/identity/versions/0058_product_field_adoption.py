"""Require Catalog review before product field definitions become effective."""

from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE custom_field_definition
    ADD COLUMN requires_adoption TINYINT(1) NOT NULL DEFAULT 0""")


def downgrade() -> None:
    # Removing the gate could publish unreviewed definitions to old consumers.
    raise RuntimeError(
        "retain product definition adoption state; downgrade requires operator review"
    )
