"""Dated, evidenced GSTR-1 reporting profile owned by Identity."""

import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, EffectiveMixin, IdMixin, TenantMixin
from billing_platform.db.types import Money, Uuid7
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CompanyGstOutwardProfile(IdMixin, TenantMixin, EffectiveMixin, AuditMixin, Base):
    __tablename__ = "company_gst_outward_profile"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "registration_id",
            "valid_from",
            name="uq_gst_outward_profile_start",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("company.id", name="fk_gst_outward_company"), nullable=False
    )
    registration_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey("company_tax_registration.id", name="fk_gst_outward_registration"),
        nullable=False,
    )
    annual_turnover: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rule_14a: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reference: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
