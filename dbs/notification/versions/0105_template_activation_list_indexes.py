"""Index template_activation keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE template_activation ADD KEY ix_template_activation_scoped_list_1 (`tenant_id`,
    `space_id`,
    `template_variant_id`,
    `id`)
""")

def downgrade() -> None:
    op.execute('ALTER TABLE template_activation DROP INDEX ix_template_activation_scoped_list_1')
