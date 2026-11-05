"""add ck tax rate replica source action; one DDL statement per direction.

Rows replicated before this revision default to PUBLISH: a WITHDRAW applied earlier is
indistinguishable afterwards and needs a Catalog republication to be recorded.
"""
from alembic import op

revision = '0107'
down_revision = '0106'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE tax_rate_replica ADD CONSTRAINT ck_tax_rate_replica_source_action CHECK (source_action IN ('PUBLISH','UPDATE','WITHDRAW'))"
DOWNGRADE = 'ALTER TABLE tax_rate_replica DROP CHECK ck_tax_rate_replica_source_action'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
