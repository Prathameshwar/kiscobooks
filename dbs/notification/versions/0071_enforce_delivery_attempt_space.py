"""enforce delivery attempt space. One DDL statement per revision."""
from alembic import op
revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE delivery_attempt MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_delivery_attempt_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE delivery_attempt MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_delivery_attempt_space_owner
""")
