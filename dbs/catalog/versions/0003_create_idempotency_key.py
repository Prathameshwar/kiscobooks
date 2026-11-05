"""Catalog idempotency_key: one reviewed literal DDL per direction; content is seeded separately.

Matches the shared platform model. No cross-service foreign key or runtime domain write.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE idempotency_key (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    key_value VARCHAR(255) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    state VARCHAR(20) NOT NULL,
    response_status SMALLINT NULL,
    response_body JSON NULL,
    locked_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    expires_at DATETIME(6) NOT NULL,
    attempt_count INT NOT NULL,
    CONSTRAINT pk_idempotency_key PRIMARY KEY (id),
    CONSTRAINT uq_idempotency_key_tenant_id_endpoint_key_value
        UNIQUE (tenant_id, endpoint, key_value),
    KEY ix_idempotency_key_tenant_id (tenant_id),
    KEY ix_idempotency_key_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE idempotency_key")
