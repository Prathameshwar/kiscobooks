"""Index delivery_event keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE delivery_event ADD KEY ix_delivery_event_scoped_list_1 (`tenant_id`,
    `space_id`,
    `delivery_id`,
    `id`)
""")

def downgrade() -> None:
    op.execute('ALTER TABLE delivery_event DROP INDEX ix_delivery_event_scoped_list_1')
