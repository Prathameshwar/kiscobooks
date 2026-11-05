"""fence provider template binding references. One DDL statement per revision."""
from alembic import op
revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE provider_template_binding ADD CONSTRAINT fk_provider_template_binding_provider_account_id_space FOREIGN KEY(provider_account_id,
    tenant_id,
    space_id) REFERENCES provider_account (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_provider_template_binding_template_version_id_space FOREIGN KEY(template_version_id,
    tenant_id,
    space_id) REFERENCES template_version (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE provider_template_binding DROP FOREIGN KEY fk_provider_template_binding_provider_account_id_space,
    DROP FOREIGN KEY fk_provider_template_binding_template_version_id_space
""")
