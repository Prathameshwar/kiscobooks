"""Index suppression keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE suppression ADD KEY ix_suppression_scoped_list_1 (`tenant_id`,
    `space_id`,
    `valid_from`,
    `id`)
""")

def downgrade() -> None:
    op.execute('ALTER TABLE suppression DROP INDEX ix_suppression_scoped_list_1')
