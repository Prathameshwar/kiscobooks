"""enforce provider template binding space. One DDL statement per revision."""
from alembic import op
revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE provider_template_binding MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_provider_template_binding_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE provider_template_binding MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_provider_template_binding_space_owner
""")
