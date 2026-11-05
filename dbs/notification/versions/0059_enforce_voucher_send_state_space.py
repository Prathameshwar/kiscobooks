"""enforce voucher send state space. One DDL statement per revision."""
from alembic import op
revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE voucher_send_state MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_voucher_send_state_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`),
    DROP INDEX uq_voucher_send_state_source,
    ADD CONSTRAINT uq_voucher_send_state_source UNIQUE (`tenant_id`,
    `space_id`,
    `company_id`,
    `voucher_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE voucher_send_state MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_voucher_send_state_space_owner,
    DROP INDEX uq_voucher_send_state_source,
    ADD CONSTRAINT uq_voucher_send_state_source UNIQUE (`tenant_id`,
    `company_id`,
    `voucher_id`)
""")
