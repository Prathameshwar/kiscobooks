"""add tax rate replica source action; one DDL statement per direction.

Rows replicated before this revision default to PUBLISH: a WITHDRAW applied earlier is
indistinguishable afterwards and needs a Catalog republication to be recorded.
"""
from alembic import op

revision = '0106'
down_revision = '0105'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE tax_rate_replica ADD COLUMN source_action VARCHAR(8) NOT NULL DEFAULT 'PUBLISH'"
DOWNGRADE = 'ALTER TABLE tax_rate_replica DROP COLUMN source_action'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
