"""Fence projected party endpoints by their owning company."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE recipient_endpoint ADD COLUMN company_id BINARY(16) NULL AFTER subject_id")
    op.execute(
        "UPDATE recipient_endpoint SET company_id = UNHEX(REPEAT('0', 32)) "
        "WHERE company_id IS NULL"
    )
    op.execute("""
        ALTER TABLE recipient_endpoint
        MODIFY COLUMN company_id BINARY(16) NOT NULL,
        DROP INDEX uq_recipient_endpoint_subject_channel_destination,
        ADD UNIQUE KEY uq_recipient_endpoint_subject_channel_destination
            (tenant_id, subject_type, subject_id, company_id, channel, destination_hmac),
        ADD KEY ix_recipient_endpoint_tenant_company_subject
            (tenant_id, company_id, subject_type, subject_id)
    """)


def downgrade() -> None:
    collision = op.get_bind().execute(text("""
        SELECT 1 FROM recipient_endpoint
        GROUP BY tenant_id, subject_type, subject_id, channel, destination_hmac
        HAVING COUNT(*) > 1 LIMIT 1
    """)).first()
    if collision is not None:
        raise RuntimeError(
            "cannot remove company scope while two companies share a destination"
        )
    op.execute("""
        ALTER TABLE recipient_endpoint
        DROP INDEX ix_recipient_endpoint_tenant_company_subject,
        DROP INDEX uq_recipient_endpoint_subject_channel_destination,
        ADD UNIQUE KEY uq_recipient_endpoint_subject_channel_destination
            (tenant_id, subject_type, subject_id, channel, destination_hmac),
        DROP COLUMN company_id
    """)
