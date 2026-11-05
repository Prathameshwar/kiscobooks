"""enforce consent state space. One DDL statement per revision."""
from alembic import op
revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE consent_state MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_consent_state_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE consent_state MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_consent_state_space_owner
""")
