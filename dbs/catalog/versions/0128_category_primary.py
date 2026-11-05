"""Retain primary memberships on different effective dates.

Downgrade preserves rows and refuses incompatible retained dated data.
"""
from alembic import op

revision = "0128"
down_revision = "0127"
branch_labels = None
depends_on = None

_ALTER = 'ALTER TABLE family_category DROP INDEX uq_p72_2, ADD CONSTRAINT uq_p72_dated_primary UNIQUE (tenant_id, company_id, family_id, scheme_id, primary_slot, valid_from)'


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute('ALTER TABLE family_category DROP INDEX uq_p72_dated_primary, ADD CONSTRAINT uq_p72_2 UNIQUE (tenant_id, company_id, family_id, scheme_id, primary_slot)')
