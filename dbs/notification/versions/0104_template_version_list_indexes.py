"""Index template_version keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE template_version ADD KEY ix_template_version_scoped_list_1 (`tenant_id`,
    `space_id`,
    `template_variant_id`,
    `id`)
""")

def downgrade() -> None:
    op.execute('ALTER TABLE template_version DROP INDEX ix_template_version_scoped_list_1')
