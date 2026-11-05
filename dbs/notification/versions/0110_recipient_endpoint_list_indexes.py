"""Index recipient_endpoint keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0110"
down_revision = "0109"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE recipient_endpoint ADD KEY ix_recipient_endpoint_scoped_list_1 (`tenant_id`,
    `space_id`,
    `subject_id`,
    `id`)
""")

def downgrade() -> None:
    op.execute('ALTER TABLE recipient_endpoint DROP INDEX ix_recipient_endpoint_scoped_list_1')
