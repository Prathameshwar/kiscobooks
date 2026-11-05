"""Index template_variant keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE template_variant ADD KEY ix_template_variant_scoped_list_1 (`tenant_id`,
    `space_id`,
    `template_id`,
    `id`)
""")

def downgrade() -> None:
    op.execute('ALTER TABLE template_variant DROP INDEX ix_template_variant_scoped_list_1')
