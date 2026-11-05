"""Reviewed, effective-dated food and medicine classification owned by Catalog."""

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from catalog.models.pricing import PricingRow


class ItemRegulatoryClassification(PricingRow):
    __tablename__ = "item_regulatory_classification"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_item_regulatory_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "item_id", "valid_from", name="uq_item_regulatory_start"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_item_regulatory_item",
        ),
        Index(
            "ix_item_regulatory_effective", "tenant_id", "company_id", "item_id", "valid_from", "id"
        ),
        CheckConstraint("row_version >= 1", name=conv("ck_item_regulatory_version")),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name=conv("ck_item_regulatory_dates")
        ),
        CheckConstraint(
            "product_kind IN ('NON_DRUG','MEDICINE','FOOD')", name=conv("ck_item_regulatory_kind")
        ),
        CheckConstraint(
            "(product_kind = 'NON_DRUG' AND licence_class IS NULL "
            "AND prescription_schedule IS NULL AND food_category_code IS NULL) "
            "OR (product_kind = 'FOOD' AND licence_class IS NULL "
            "AND prescription_schedule IS NULL AND food_category_code IS NOT NULL) "
            "OR (product_kind = 'MEDICINE' AND licence_class IN "
            "('OTHER_THAN_C_C1_X','C_C1_EXCLUDING_X','SCHEDULE_X') AND "
            "prescription_schedule IN ('NONE','H','H1','X') AND food_category_code IS NULL)",
            name=conv("ck_item_regulatory_class_shape"),
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    product_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    licence_class: Mapped[str | None] = mapped_column(String(24), nullable=True)
    prescription_schedule: Mapped[str | None] = mapped_column(String(4), nullable=True)
    food_category_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    review_reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    reviewed_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    reviewed_by: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
