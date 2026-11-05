"""Create idempotency_key; exactly one DDL statement in each direction."""
from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE idempotency_key (\n\tkey_value VARCHAR(255) NOT NULL, \n\tendpoint VARCHAR(200) NOT NULL, \n\trequest_hash VARCHAR(64) NOT NULL, \n\tstate VARCHAR(20) NOT NULL, \n\tresponse_status SMALLINT, \n\tresponse_body JSON, \n\tlocked_at DATETIME(6), \n\tcompleted_at DATETIME(6), \n\texpires_at DATETIME(6) NOT NULL, \n\tattempt_count INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tCONSTRAINT pk_idempotency_key PRIMARY KEY (id), \n\tCONSTRAINT uq_idempotency_key_tenant_id_endpoint_key_value UNIQUE (tenant_id, endpoint, key_value),\n\tKEY ix_idempotency_key_expires_at (expires_at),\n\tKEY ix_idempotency_key_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE idempotency_key")
