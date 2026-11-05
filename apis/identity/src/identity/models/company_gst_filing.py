"""Dated GSTIN filing frequency, owned by Identity."""

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, EffectiveMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CompanyGstFilingPreference(IdMixin, TenantMixin, EffectiveMixin, AuditMixin, Base):
    __tablename__ = "company_gst_filing_preference"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "registration_id", "valid_from", name="uq_gst_filing_start"
        ),
        CheckConstraint("frequency IN ('MONTHLY','QRMP')", name="gst_filing_frequency"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("company.id", name="fk_gst_filing_company"), nullable=False
    )
    registration_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey("company_tax_registration.id", name="fk_gst_filing_registration"),
        nullable=False,
    )
    frequency: Mapped[str] = mapped_column(String(10), nullable=False)
