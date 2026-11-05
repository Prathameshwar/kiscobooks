"""Index delivery_attempt keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE delivery_attempt ADD KEY ix_delivery_attempt_scoped_list_1 (`tenant_id`,
    `space_id`,
    `delivery_id`,
    `id`)
""")

def downgrade() -> None:
    op.execute('ALTER TABLE delivery_attempt DROP INDEX ix_delivery_attempt_scoped_list_1')
