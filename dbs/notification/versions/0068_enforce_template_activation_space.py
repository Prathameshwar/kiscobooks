"""enforce template activation space. One DDL statement per revision."""
from alembic import op
revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE template_activation MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_template_activation_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE template_activation MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_template_activation_space_owner
""")
