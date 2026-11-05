"""Create processed_message; exactly one DDL statement in each direction."""
from alembic import op

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE processed_message (\n\tconsumer_name VARCHAR(120) NOT NULL, \n\tmessage_id BINARY(16) NOT NULL, \n\tprocessed_at DATETIME(6) NOT NULL, \n\tCONSTRAINT pk_processed_message PRIMARY KEY (consumer_name, message_id),\n\tKEY ix_processed_message_processed_at (processed_at)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE processed_message")
