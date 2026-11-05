"""fence template activation references. One DDL statement per revision."""
from alembic import op
revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE template_activation ADD CONSTRAINT fk_template_activation_template_version_id_space FOREIGN KEY(template_version_id,
    tenant_id,
    space_id) REFERENCES template_version (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_template_activation_template_variant_id_space FOREIGN KEY(template_variant_id,
    tenant_id,
    space_id) REFERENCES template_variant (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE template_activation DROP FOREIGN KEY fk_template_activation_template_version_id_space,
    DROP FOREIGN KEY fk_template_activation_template_variant_id_space
""")
