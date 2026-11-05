"""Create delivery_attachment; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE delivery_attachment (
    delivery_id BINARY(16) NOT NULL,
    attachment_id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    disposition VARCHAR(20) NOT NULL,
    content_id VARCHAR(255) NULL,
    display_order SMALLINT UNSIGNED NOT NULL,
    CONSTRAINT pk_delivery_attachment PRIMARY KEY (delivery_id, attachment_id),
    CONSTRAINT uq_delivery_attachment_order UNIQUE (delivery_id, display_order),
    CONSTRAINT fk_delivery_attachment_delivery_id FOREIGN KEY (delivery_id) REFERENCES notification_delivery (id),
    CONSTRAINT fk_delivery_attachment_attachment_id FOREIGN KEY (attachment_id) REFERENCES attachment (id),
    KEY ix_delivery_attachment_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE delivery_attachment")

