"""Global commercial catalog; immutable revisions retain every quoted price definition."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class PlatformPrice(IdMixin, AuditMixin, DeactivableMixin, Base):
    __tablename__ = "platform_price"
    __table_args__ = (
        UniqueConstraint("code", name="uq_platform_price_code"),
        Index("ix_platform_price_deleted_code", "deleted_at", "code", "id"),
        CheckConstraint(
            "monthly_fee >= 0 AND unit_price >= 0 AND output_unit_price >= 0",
            name="nonnegative_prices",
        ),
        CheckConstraint(
            "fx_inr_per_usd > 0 AND tax_percent >= 0 AND tax_percent <= 100",
            name="valid_conversion",
        ),
        CheckConstraint("term_months IN (1, 12, 36) AND version > 0", name="valid_term_version"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR", server_default="INR"
    )
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    output_unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    fx_inr_per_usd: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class PlatformPriceRevision(IdMixin, Base):
    __tablename__ = "platform_price_revision"
    __table_args__ = (
        UniqueConstraint("price_id", "version", name="uq_platform_price_revision_version"),
        MARIADB_TABLE_ARGS,
    )
    price_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("platform_price.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
