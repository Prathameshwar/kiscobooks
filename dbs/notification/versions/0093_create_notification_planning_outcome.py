"""Create notification_planning_outcome; indexes and constraints inline. One DDL."""
from alembic import op
revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
CREATE TABLE notification_planning_outcome (
	request_id BINARY(16) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    decision VARCHAR(20) NOT NULL,
    reason_code VARCHAR(120) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    space_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    CONSTRAINT pk_notification_planning_outcome PRIMARY KEY (id),
    CONSTRAINT fk_notification_planning_outcome_request_id FOREIGN KEY(request_id) REFERENCES notification_request (id),
    CONSTRAINT uq_notification_planning_outcome_channel UNIQUE (request_id,
    channel),
    CONSTRAINT fk_notification_planning_outcome_request_id_space FOREIGN KEY(request_id,
    tenant_id,
    space_id) REFERENCES notification_request (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    CONSTRAINT uq_notification_planning_outcome_space_owner UNIQUE (id,
    tenant_id,
    space_id),
    KEY ix_notification_planning_outcome_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
""")

def downgrade() -> None:
    op.execute("DROP TABLE notification_planning_outcome")
