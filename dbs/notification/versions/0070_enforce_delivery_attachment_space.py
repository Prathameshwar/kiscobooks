"""enforce delivery attachment space. One DDL statement per revision."""
from alembic import op
revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE delivery_attachment MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_delivery_attachment_space_owner UNIQUE (`delivery_id`,
    `attachment_id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE delivery_attachment MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_delivery_attachment_space_owner
""")
