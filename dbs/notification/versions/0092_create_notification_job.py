"""Create notification_job; indexes and constraints inline. One DDL."""
from alembic import op
revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
CREATE TABLE notification_job (
	request_key BINARY(32) NOT NULL,
    kind VARCHAR(40) NOT NULL,
    target_id BINARY(16) NOT NULL,
    actor_user_id BINARY(16),
    status VARCHAR(20) NOT NULL,
    reason_code VARCHAR(120),
    created_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6),
    space_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    CONSTRAINT pk_notification_job PRIMARY KEY (id),
    CONSTRAINT uq_notification_job_space_owner UNIQUE (id,
    tenant_id,
    space_id),
    CONSTRAINT uq_notification_job_request UNIQUE (tenant_id,
    space_id,
    request_key),
    KEY ix_notification_job_due (status,
    created_at),
    KEY ix_notification_job_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
""")

def downgrade() -> None:
    op.execute("DROP TABLE notification_job")
