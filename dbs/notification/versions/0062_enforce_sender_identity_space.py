"""enforce sender identity space. One DDL statement per revision."""
from alembic import op
revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE sender_identity MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_sender_identity_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE sender_identity MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_sender_identity_space_owner
""")
