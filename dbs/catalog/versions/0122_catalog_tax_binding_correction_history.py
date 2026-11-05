"""Allow retained withdrawn revisions; live overlap remains company-locked.

Downgrade can restore the old unique key only if retained corrected revisions do not
share a start date. Never delete correction evidence to force a downgrade.
"""
from alembic import op

revision = "0122"
down_revision = "0121"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE catalog_tax_binding DROP INDEX uq_catalog_tax_binding_start"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("ALTER TABLE catalog_tax_binding ADD CONSTRAINT uq_catalog_tax_binding_start UNIQUE (tenant_id, company_id, scope_id, direction, bundle, valid_from)")
