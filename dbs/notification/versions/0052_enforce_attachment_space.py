"""enforce attachment space. One DDL statement per revision."""
from alembic import op
revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE attachment MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_attachment_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`),
    DROP INDEX uq_attachment_storage_key,
    ADD CONSTRAINT uq_attachment_storage_key UNIQUE (`tenant_id`,
    `space_id`,
    `storage_key`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE attachment MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_attachment_space_owner,
    DROP INDEX uq_attachment_storage_key,
    ADD CONSTRAINT uq_attachment_storage_key UNIQUE (`tenant_id`,
    `storage_key`)
""")
