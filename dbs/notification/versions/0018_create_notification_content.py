"""Create notification_content; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE notification_content (
    delivery_id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    subject_ciphertext BLOB NULL,
    body_text_ciphertext MEDIUMBLOB NULL,
    body_html_ciphertext MEDIUMBLOB NULL,
    payload_ciphertext MEDIUMBLOB NULL,
    content_sha256 BINARY(32) NOT NULL,
    encryption_key_ref VARCHAR(500) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    purged_at DATETIME(6) NULL,
    CONSTRAINT pk_notification_content PRIMARY KEY (delivery_id),
    CONSTRAINT fk_notification_content_delivery_id FOREIGN KEY (delivery_id) REFERENCES notification_delivery (id),
    KEY ix_notification_content_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE notification_content")

