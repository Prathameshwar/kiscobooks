"""processed_message; one atomic DDL statement."""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE processed_message (\n\tconsumer_name VARCHAR(120) NOT NULL, \n\tmessage_id BINARY(16) NOT NULL, \n\tprocessed_at DATETIME(6) NOT NULL, \n\tCONSTRAINT pk_processed_message PRIMARY KEY (consumer_name, message_id),\n\tINDEX ix_processed_message_processed_at (processed_at)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE processed_message")
