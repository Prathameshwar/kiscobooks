"""``company_document`` — a stored statutory or corporate document reference.

docs/identity-schema.md §3.11. ``file_url`` is an object-storage key served through a
signed, expiring URL (CLAUDE.md §5.14), never a public path. ``expires_on`` drives a
renewal reminder sweep.
"""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import BigInteger, Date, ForeignKeyConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column


class CompanyDocument(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    """docs/identity-schema.md §3.11."""

    __tablename__ = "company_document"
    __table_args__ = (
        Index("ix_company_document_company_id_type", "company_id", "type"),
        Index("ix_company_document_expires_on", "expires_on"),
        Index(
            "ix_company_document_pending",
            "tenant_id",
            "company_id",
            "storage_state",
            "upload_expires_at",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["company.tenant_id", "company.id"],
            name="fk_company_document_owner",
        ),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issued_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    storage_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="legacy", server_default=text("'legacy'")
    )
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    blob_snapshot: Mapped[str | None] = mapped_column(String(80), nullable=True)
    upload_expires_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finalized_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
