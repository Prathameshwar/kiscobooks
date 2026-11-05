"""Retain repeated categories on different effective dates.

Downgrade preserves rows and refuses incompatible retained dated data.
"""
from alembic import op

revision = "0127"
down_revision = "0126"
branch_labels = None
depends_on = None

_ALTER = 'ALTER TABLE family_category DROP INDEX uq_p72_1, ADD CONSTRAINT uq_p72_dated_category UNIQUE (tenant_id, company_id, family_id, category_id, valid_from)'


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute('ALTER TABLE family_category DROP INDEX uq_p72_dated_category, ADD CONSTRAINT uq_p72_1 UNIQUE (tenant_id, company_id, family_id, category_id)')
