"""``company_contact`` — a named point of contact on a company.

docs/identity-schema.md §3.9. Distinct from ``user``: a contact is a person to reach for
a purpose (finance, statutory), not a principal who logs in.
"""

from __future__ import annotations

import uuid
from typing import Final

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

#: Validated in ``domain``/schema, never a MySQL ``ENUM`` (CLAUDE.md §4).
CONTACT_TYPES: Final[frozenset[str]] = frozenset({"primary", "finance", "support", "statutory"})


class CompanyContact(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    """docs/identity-schema.md §3.9."""

    __tablename__ = "company_contact"
    __table_args__ = (
        # Leads with `company_id` (§1.7 second exception: it determines tenant_id) and
        # supports the FK.
        Index("ix_company_contact_company_id_type", "company_id", "type"),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("company.id", name="fk_company_contact_company_id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone_country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
