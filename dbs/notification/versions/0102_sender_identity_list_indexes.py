"""Index sender_identity keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE sender_identity ADD KEY ix_sender_identity_scoped_list_1 (`tenant_id`,
    `space_id`,
    `provider_account_id`,
    `id`)
""")

def downgrade() -> None:
    op.execute('ALTER TABLE sender_identity DROP INDEX ix_sender_identity_scoped_list_1')
