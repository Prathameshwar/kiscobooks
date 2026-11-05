"""fence template variant references. One DDL statement per revision."""
from alembic import op
revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE template_variant ADD CONSTRAINT fk_template_variant_template_id_space FOREIGN KEY(template_id,
    tenant_id,
    space_id) REFERENCES notification_template (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute('ALTER TABLE template_variant DROP FOREIGN KEY fk_template_variant_template_id_space')
