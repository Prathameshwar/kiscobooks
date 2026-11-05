"""Allow retained withdrawn revisions; live overlap remains company-locked.

Downgrade can restore the old unique key only if retained corrected revisions do not
share a start date. Never delete correction evidence to force a downgrade.
"""
from alembic import op

revision = "0120"
down_revision = "0119"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE tax_classification DROP INDEX uq_tax_classification_start"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("ALTER TABLE tax_classification ADD CONSTRAINT uq_tax_classification_start UNIQUE (tenant_id, company_id, code_system, code, valid_from)")
