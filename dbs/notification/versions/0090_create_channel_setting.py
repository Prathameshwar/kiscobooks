"""Create channel_setting; indexes and constraints inline. One DDL."""
from alembic import op
revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
CREATE TABLE channel_setting (
	channel VARCHAR(20) NOT NULL,
    is_enabled BOOL NOT NULL,
    space_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16),
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16),
    CONSTRAINT pk_channel_setting PRIMARY KEY (id),
    CONSTRAINT uq_channel_setting_space_owner UNIQUE (id,
    tenant_id,
    space_id),
    CONSTRAINT uq_channel_setting_channel UNIQUE (tenant_id,
    space_id,
    channel),
    KEY ix_channel_setting_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
""")

def downgrade() -> None:
    op.execute("DROP TABLE channel_setting")
