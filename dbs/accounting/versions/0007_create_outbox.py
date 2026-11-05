"""Create outbox; exactly one DDL statement in each direction."""
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE outbox (\n\ttenant_id BINARY(16), \n\taggregate_type VARCHAR(80) NOT NULL, \n\taggregate_id BINARY(16) NOT NULL, \n\tevent_type VARCHAR(120) NOT NULL, \n\tpayload JSON NOT NULL, \n\tschema_version SMALLINT NOT NULL, \n\tmessage_id BINARY(16) NOT NULL, \n\ttrace_id VARCHAR(32), \n\toccurred_at DATETIME(6) NOT NULL, \n\tavailable_at DATETIME(6) NOT NULL, \n\tpublished_at DATETIME(6), \n\tattempt_count SMALLINT NOT NULL, \n\tlast_error TEXT, \n\tid BINARY(16) NOT NULL, \n\tCONSTRAINT pk_outbox PRIMARY KEY (id), \n\tCONSTRAINT uq_outbox_message_id UNIQUE (message_id),\n\tKEY ix_outbox_aggregate_type_aggregate_id (aggregate_type, aggregate_id),\n\tKEY ix_outbox_published_at_available_at (published_at, available_at)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE outbox")
