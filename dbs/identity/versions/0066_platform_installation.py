"""Persistent first-run completion and first operator identity; no seed data in DDL."""

from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE platform_installation (
    id BINARY(16) NOT NULL,
    `key` VARCHAR(16) NOT NULL,
    name VARCHAR(200) NULL,
    public_url VARCHAR(2048) NULL,
    completed_at DATETIME(6) NULL,
    tenant_id BINARY(16) NULL,
    administrator_id BINARY(16) NULL,
    administrator_subject VARCHAR(64) NULL,
    request_hash VARCHAR(64) NULL,
    CONSTRAINT pk_platform_installation PRIMARY KEY (id),
    CONSTRAINT uq_platform_installation_key UNIQUE (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE=utf8mb4_unicode_ci
""")


def downgrade() -> None:
    # Explicit operator downgrade removes completion evidence; never used by setup HTTP routes.
    op.execute("DROP TABLE platform_installation")
