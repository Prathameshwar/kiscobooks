"""enforce template variant space. One DDL statement per revision."""
from alembic import op
revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE template_variant MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_template_variant_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE template_variant MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_template_variant_space_owner
""")
