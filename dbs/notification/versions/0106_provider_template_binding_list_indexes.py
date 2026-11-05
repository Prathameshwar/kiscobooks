"""Index provider_template_binding keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0106"
down_revision = "0105"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE provider_template_binding ADD KEY ix_provider_template_binding_scoped_list_1 (`tenant_id`,
    `space_id`,
    `template_version_id`,
    `id`)
""")

def downgrade() -> None:
    op.execute('ALTER TABLE provider_template_binding DROP INDEX ix_provider_template_binding_scoped_list_1')
