"""idempotency_key; one atomic DDL statement."""
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE idempotency_key (\n\tkey_value VARCHAR(255) NOT NULL, \n\tendpoint VARCHAR(200) NOT NULL, \n\trequest_hash VARCHAR(64) NOT NULL, \n\tstate VARCHAR(20) NOT NULL, \n\tresponse_status SMALLINT, \n\tresponse_body JSON, \n\tlocked_at DATETIME(6), \n\tcompleted_at DATETIME(6), \n\texpires_at DATETIME(6) NOT NULL, \n\tattempt_count INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tCONSTRAINT pk_idempotency_key PRIMARY KEY (id), \n\tCONSTRAINT uq_idempotency_key_tenant_id_endpoint_key_value UNIQUE (tenant_id, endpoint, key_value),\n\tINDEX ix_idempotency_key_expires_at (expires_at),\n\tINDEX ix_idempotency_key_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE idempotency_key")
