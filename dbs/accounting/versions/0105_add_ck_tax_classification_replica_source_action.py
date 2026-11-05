"""add ck tax classification replica source action; one DDL statement per direction.

Rows replicated before this revision default to PUBLISH: a WITHDRAW applied earlier is
indistinguishable afterwards and needs a Catalog republication to be recorded.
"""
from alembic import op

revision = '0105'
down_revision = '0104'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE tax_classification_replica ADD CONSTRAINT ck_tax_classification_replica_source_action CHECK (source_action IN ('PUBLISH','UPDATE','WITHDRAW'))"
DOWNGRADE = 'ALTER TABLE tax_classification_replica DROP CHECK ck_tax_classification_replica_source_action'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
