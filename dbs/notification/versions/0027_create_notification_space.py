"""Create notification_space; indexes and constraints inline. One DDL."""
from alembic import op
revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
CREATE TABLE notification_space (
	kind VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    CONSTRAINT pk_notification_space PRIMARY KEY (id),
    CONSTRAINT uq_notification_space_owner_kind UNIQUE (tenant_id,
    kind),
    CONSTRAINT uq_notification_space_id_owner UNIQUE (id,
    tenant_id),
    KEY ix_notification_space_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
""")

def downgrade() -> None:
    op.execute("DROP TABLE notification_space")
