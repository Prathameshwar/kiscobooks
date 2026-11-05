"""fence template version references. One DDL statement per revision."""
from alembic import op
revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE template_version ADD CONSTRAINT fk_template_version_template_variant_id_space FOREIGN KEY(template_variant_id,
    tenant_id,
    space_id) REFERENCES template_variant (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute('ALTER TABLE template_version DROP FOREIGN KEY fk_template_version_template_variant_id_space')
