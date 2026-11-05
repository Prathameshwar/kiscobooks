"""Indexed dated Catalog unit evidence, never authored by voucher users."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.types import Uuid7
from sqlalchemy import JSON, BigInteger, CheckConstraint, Date, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from vouchers.models.core import Record


class VoucherItemUnitProjection(Record, Base):
    __tablename__ = "voucher_item_unit_projection"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_item_unit_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "source_id", name="uq_voucher_item_unit_source"
        ),
        Index(
            "ix_voucher_item_unit_date",
            "tenant_id",
            "company_id",
            "item_id",
            "unit_id",
            "valid_from",
            "id",
        ),
        CheckConstraint("source_version > 0", name="item_unit_source_version"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="item_unit_dates"),
        MARIADB_TABLE_ARGS,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    facts: Mapped[Any] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
