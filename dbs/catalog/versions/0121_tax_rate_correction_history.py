"""Allow retained withdrawn revisions; live overlap remains company-locked.

Downgrade can restore the old unique key only if retained corrected revisions do not
share a start date. Never delete correction evidence to force a downgrade.
"""
from alembic import op

revision = "0121"
down_revision = "0120"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE tax_rate DROP INDEX uq_tax_rate_start"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("ALTER TABLE tax_rate ADD CONSTRAINT uq_tax_rate_start UNIQUE (tenant_id, company_id, series_id, valid_from)")
