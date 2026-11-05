"""enforce party endpoint checkpoint space. One DDL statement per revision."""
from alembic import op
revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE party_endpoint_checkpoint MODIFY COLUMN space_id BINARY(16) NOT NULL,
    DROP INDEX uq_party_endpoint_checkpoint_source,
    ADD CONSTRAINT uq_party_endpoint_checkpoint_source UNIQUE (`tenant_id`,
    `space_id`,
    `company_id`,
    `party_id`,
    `purpose`,
    `channel`),
    ADD CONSTRAINT uq_party_endpoint_checkpoint_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE party_endpoint_checkpoint MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_party_endpoint_checkpoint_source,
    ADD CONSTRAINT uq_party_endpoint_checkpoint_source UNIQUE (`tenant_id`,
    `company_id`,
    `party_id`,
    `purpose`,
    `channel`),
    DROP INDEX uq_party_endpoint_checkpoint_space_owner
""")
