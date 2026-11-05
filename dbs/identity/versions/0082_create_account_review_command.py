"""Durable review intent; one atomic CREATE TABLE, reversible."""
from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE account_review_command (
id BINARY(16) NOT NULL,
tenant_id BINARY(16) NOT NULL,
account_id BINARY(16) NOT NULL,
actor_id BINARY(16) NOT NULL,
request_key VARCHAR(128) NOT NULL,
request_hash VARCHAR(64) NOT NULL,
action VARCHAR(20) NOT NULL,
reason VARCHAR(500) NOT NULL,
attested BOOLEAN NOT NULL,
expected_fingerprint VARCHAR(64) NOT NULL,
status VARCHAR(20) NOT NULL,
attempts INTEGER NOT NULL,
completed_at DATETIME(6),
error_code VARCHAR(40),
created_at DATETIME(6) NOT NULL,
created_by BINARY(16),
updated_at DATETIME(6) NOT NULL,
updated_by BINARY(16),
PRIMARY KEY (id), UNIQUE KEY uq_account_review_command_key (tenant_id,actor_id,request_key),
KEY ix_account_review_command_tenant_id (tenant_id),
KEY ix_account_review_command_history (tenant_id,account_id,created_at,id),
KEY ix_account_review_command_pending (tenant_id,status,created_at,id),
CONSTRAINT fk_account_review_command_owner FOREIGN KEY (tenant_id,account_id) REFERENCES account_review (tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC""")


def downgrade() -> None:
    op.execute("DROP TABLE account_review_command")
