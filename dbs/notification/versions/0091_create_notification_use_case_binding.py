"""Create notification_use_case_binding; indexes and constraints inline. One DDL."""
from alembic import op
revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
CREATE TABLE notification_use_case_binding (
	company_id BINARY(16) NOT NULL,
    event_key VARCHAR(120) NOT NULL,
    trigger_key VARCHAR(120) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    template_id BINARY(16) NOT NULL,
    valid_from DATETIME(6) NOT NULL,
    valid_to DATETIME(6),
    space_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16),
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16),
    CONSTRAINT pk_notification_use_case_binding PRIMARY KEY (id),
    CONSTRAINT fk_notification_use_case_binding_template_id_space FOREIGN KEY(template_id,
    tenant_id,
    space_id) REFERENCES notification_template (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    CONSTRAINT fk_notification_use_case_binding_template_id FOREIGN KEY(template_id) REFERENCES notification_template (id),
    CONSTRAINT uq_notification_use_case_binding_start UNIQUE (tenant_id,
    space_id,
    company_id,
    event_key,
    trigger_key,
    channel,
    valid_from),
    CONSTRAINT uq_notification_use_case_binding_space_owner UNIQUE (id,
    tenant_id,
    space_id),
    KEY ix_notification_use_case_binding_resolve (tenant_id,
    space_id,
    company_id,
    event_key,
    channel,
    valid_from),
    KEY ix_notification_use_case_binding_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
""")

def downgrade() -> None:
    op.execute("DROP TABLE notification_use_case_binding")
