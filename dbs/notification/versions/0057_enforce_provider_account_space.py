"""enforce provider account space. One DDL statement per revision."""
from alembic import op
revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE provider_account MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_provider_account_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`),
    DROP INDEX uq_provider_account_tenant_id_key,
    ADD CONSTRAINT uq_provider_account_tenant_id_key UNIQUE (`tenant_id`,
    `space_id`,
    `key`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE provider_account MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_provider_account_space_owner,
    DROP INDEX uq_provider_account_tenant_id_key,
    ADD CONSTRAINT uq_provider_account_tenant_id_key UNIQUE (`tenant_id`,
    `key`)
""")
