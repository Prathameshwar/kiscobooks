"""Native company-owned price definitions; no transactions, parties or physical stock."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Quantity, Uuid7
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv


class PricingRow(IdMixin, TenantMixin, AuditMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PriceLevel(PricingRow):
    __tablename__ = "price_level"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v83_0"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_v83_1"),
        UniqueConstraint("tenant_id", "company_id", "ordinal", name="uq_v83_2"),
        CheckConstraint("row_version >= 1", name="v83_0"),
        CheckConstraint("ordinal BETWEEN 1 AND 64", name="v83_1"),
        Index("ix_v83_0", "tenant_id", "company_id", "name", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PricePlan(PricingRow):
    __tablename__ = "price_plan"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v84_0"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_v84_1"),
        UniqueConstraint("tenant_id", "company_id", "price_level_id", "currency", name="uq_v84_2"),
        UniqueConstraint("tenant_id", "company_id", "id", "currency", name="uq_v84_3"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "price_level_id"],
            ["price_level.tenant_id", "price_level.company_id", "price_level.id"],
            name="fk_v84_0",
        ),
        CheckConstraint("row_version >= 1", name="v84_0"),
        CheckConstraint("purpose IN ('SALE','PURCHASE','REFERENCE_RETAIL')", name="v84_1"),
        CheckConstraint(
            "(purpose = 'SALE' AND price_level_id IS NOT NULL) OR (purpose <> 'SALE' AND "
            "price_level_id IS NULL)",
            name="v84_2",
        ),
        CheckConstraint("tax_basis IN ('EXCLUSIVE','INCLUSIVE')", name="v84_3"),
        Index("ix_v84_0", "tenant_id", "company_id", "purpose", "currency", "id"),
        Index("ix_v84_1", "tenant_id", "company_id", "name", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    price_level_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    tax_basis: Mapped[str] = mapped_column(String(12), nullable=False)

    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class CompanyPricingPolicy(PricingRow):
    __tablename__ = "company_pricing_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v85_0"),
        UniqueConstraint("tenant_id", "company_id", "valid_from", name="uq_v85_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "default_level_id"],
            ["price_level.tenant_id", "price_level.company_id", "price_level.id"],
            name="fk_v85_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "fallback_level_id"],
            ["price_level.tenant_id", "price_level.company_id", "price_level.id"],
            name="fk_v85_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "purchase_plan_id"],
            ["price_plan.tenant_id", "price_plan.company_id", "price_plan.id"],
            name="fk_v85_2",
        ),
        CheckConstraint("row_version >= 1", name="v85_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="v85_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="v85_2"),
        CheckConstraint(
            "(missing_price_policy = 'ERROR' AND fallback_level_id IS NULL) OR "
            "(missing_price_policy = 'FALLBACK' AND fallback_level_id IS NOT NULL AND "
            "fallback_level_id <> default_level_id)",
            name="v85_3",
        ),
        CheckConstraint(
            "sale_unit_mode IN ('EXPLICIT_ONLY','EXACT_BASE_DERIVATION')", name="v85_4"
        ),
        CheckConstraint(
            "purchase_unit_mode IN ('EXPLICIT_ONLY','EXACT_BASE_DERIVATION')", name="v85_5"
        ),
        Index("ix_v85_0", "tenant_id", "company_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    default_level_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    missing_price_policy: Mapped[str] = mapped_column(String(10), nullable=False)
    fallback_level_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    purchase_plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    sale_unit_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    purchase_unit_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class ItemPriceScope(PricingRow):
    __tablename__ = "item_price_scope"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v86_0"),
        UniqueConstraint("tenant_id", "company_id", "item_id", "lot_key", name="uq_v86_1"),
        UniqueConstraint("tenant_id", "company_id", "item_id", "id", name="uq_v86_2"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_v86_0",
        ),
        CheckConstraint("row_version >= 1", name="v86_0"),
        CheckConstraint(
            "(subject_kind = 'SKU' AND lot_id IS NULL) OR "
            "(subject_kind = 'LOT' AND lot_id IS NOT NULL)",
            name="v86_1",
        ),
        CheckConstraint(
            "(lot_mrp IS NULL AND lot_currency IS NULL AND lot_unit_id IS NULL) OR "
            "(subject_kind = 'LOT' AND lot_mrp > 0 AND lot_currency IS NOT NULL "
            "AND lot_unit_id IS NOT NULL)",
            name="batch_mrp_shape",
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(3), nullable=False)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    lot_key: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        Computed("COALESCE(lot_id, X'00000000000000000000000000000000')", persisted=True),
        nullable=False,
    )
    lot_mrp: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    lot_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    lot_unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class ItemPriceNumericRevision(PricingRow):
    __tablename__ = "item_price_numeric_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v87_0"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "item_id",
            "unit_revision_id",
            "currency",
            "valid_from",
            name="uq_v87_1",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "item_id",
            "unit_revision_id",
            "currency",
            "id",
            name="uq_v87_2",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_v87_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_revision_id"],
            [
                "item_unit_revision.tenant_id",
                "item_unit_revision.company_id",
                "item_unit_revision.id",
            ],
            name="fk_v87_1",
        ),
        CheckConstraint("row_version >= 1", name="v87_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="v87_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="v87_2"),
        CheckConstraint("price_decimal_places BETWEEN 0 AND 4", name="v87_3"),
        CheckConstraint("price_increment IS NULL OR price_increment > 0", name="v87_4"),
        Index(
            "ix_v87_0",
            "tenant_id",
            "company_id",
            "item_id",
            "unit_revision_id",
            "currency",
            "valid_from",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_decimal_places: Mapped[int] = mapped_column(Integer, nullable=False)
    price_increment: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class ItemPriceSeries(PricingRow):
    __tablename__ = "item_price_series"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v88_0"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "plan_id",
            "price_scope_id",
            "unit_revision_id",
            "channel_scope_key",
            name="uq_v88_1",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "item_id",
            "unit_revision_id",
            "currency",
            "id",
            name="uq_v88_2",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_v88_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_revision_id"],
            [
                "item_unit_revision.tenant_id",
                "item_unit_revision.company_id",
                "item_unit_revision.id",
            ],
            name="fk_v88_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "plan_id", "currency"],
            [
                "price_plan.tenant_id",
                "price_plan.company_id",
                "price_plan.id",
                "price_plan.currency",
            ],
            name="fk_v88_2",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id", "price_scope_id"],
            [
                "item_price_scope.tenant_id",
                "item_price_scope.company_id",
                "item_price_scope.item_id",
                "item_price_scope.id",
            ],
            name="fk_v88_3",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "channel_code"],
            ["sales_channel.tenant_id", "sales_channel.company_id", "sales_channel.code"],
            name="fk_item_price_series_channel",
        ),
        CheckConstraint("row_version >= 1", name="v88_0"),
        CheckConstraint("audience_kind = 'STANDARD'", name="v88_1"),
        Index("ix_v88_0", "tenant_id", "company_id", "item_id", "plan_id", "id"),
        Index("ix_item_price_series_channel", "tenant_id", "company_id", "channel_code"),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    price_scope_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    audience_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    channel_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    channel_scope_key: Mapped[str] = mapped_column(
        String(30), Computed("COALESCE(channel_code, '*')", persisted=True), nullable=False
    )


class ItemPriceDraft(PricingRow):
    __tablename__ = "item_price_draft"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "currency", "id", name="uq_v89_currency"),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v89_0"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_v89_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_revision_id"],
            [
                "item_unit_revision.tenant_id",
                "item_unit_revision.company_id",
                "item_unit_revision.id",
            ],
            name="fk_v89_1",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "company_id",
                "item_id",
                "unit_revision_id",
                "currency",
                "numeric_revision_id",
            ],
            [
                "item_price_numeric_revision.tenant_id",
                "item_price_numeric_revision.company_id",
                "item_price_numeric_revision.item_id",
                "item_price_numeric_revision.unit_revision_id",
                "item_price_numeric_revision.currency",
                "item_price_numeric_revision.id",
            ],
            name="fk_v89_2",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id", "unit_revision_id", "currency", "series_id"],
            [
                "item_price_series.tenant_id",
                "item_price_series.company_id",
                "item_price_series.item_id",
                "item_price_series.unit_revision_id",
                "item_price_series.currency",
                "item_price_series.id",
            ],
            name="fk_v89_3",
        ),
        CheckConstraint("row_version >= 1", name="v89_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="v89_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="v89_2"),
        CheckConstraint("price_basis_quantity > 0", name="v89_3"),
        CheckConstraint(
            "(price_method = 'FIXED' AND amount IS NOT NULL AND amount >= 0) OR "
            "(price_method IN ('TIERS','FORMULA') AND amount IS NULL)",
            name="v89_4",
        ),
        CheckConstraint("status IN ('DRAFT','PUBLISHED')", name="v89_5"),
        Index("ix_v89_0", "tenant_id", "company_id", "series_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    numeric_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    series_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    price_method: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    price_basis_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)


class ItemPrice(PricingRow):
    __tablename__ = "item_price"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "currency", "id", name="uq_v90_currency"),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v90_0"),
        UniqueConstraint("tenant_id", "company_id", "source_draft_id", name="uq_v90_1"),
        UniqueConstraint("tenant_id", "company_id", "series_id", "valid_from", name="uq_v90_2"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_v90_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_revision_id"],
            [
                "item_unit_revision.tenant_id",
                "item_unit_revision.company_id",
                "item_unit_revision.id",
            ],
            name="fk_v90_1",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "company_id",
                "item_id",
                "unit_revision_id",
                "currency",
                "numeric_revision_id",
            ],
            [
                "item_price_numeric_revision.tenant_id",
                "item_price_numeric_revision.company_id",
                "item_price_numeric_revision.item_id",
                "item_price_numeric_revision.unit_revision_id",
                "item_price_numeric_revision.currency",
                "item_price_numeric_revision.id",
            ],
            name="fk_v90_2",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id", "unit_revision_id", "currency", "series_id"],
            [
                "item_price_series.tenant_id",
                "item_price_series.company_id",
                "item_price_series.item_id",
                "item_price_series.unit_revision_id",
                "item_price_series.currency",
                "item_price_series.id",
            ],
            name="fk_v90_3",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "source_draft_id"],
            ["item_price_draft.tenant_id", "item_price_draft.company_id", "item_price_draft.id"],
            name="fk_v90_4",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "supersedes_id"],
            ["item_price.tenant_id", "item_price.company_id", "item_price.id"],
            name="fk_v90_5",
        ),
        CheckConstraint("row_version >= 1", name="v90_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="v90_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="v90_2"),
        CheckConstraint("price_basis_quantity > 0", name="v90_3"),
        CheckConstraint(
            "(price_method = 'FIXED' AND amount IS NOT NULL AND amount >= 0) OR "
            "(price_method IN ('TIERS','FORMULA') AND amount IS NULL)",
            name="v90_4",
        ),
        Index("ix_v90_0", "tenant_id", "company_id", "series_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    numeric_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    series_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    price_method: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    price_basis_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    source_draft_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class ItemPriceTier(PricingRow):
    __tablename__ = "item_price_tier"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v91_0"),
        UniqueConstraint("tenant_id", "company_id", "draft_id", "min_quantity", name="uq_v91_1"),
        UniqueConstraint("tenant_id", "company_id", "price_id", "min_quantity", name="uq_v91_2"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "currency", "draft_id"],
            [
                "item_price_draft.tenant_id",
                "item_price_draft.company_id",
                "item_price_draft.currency",
                "item_price_draft.id",
            ],
            name="fk_v91_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "currency", "price_id"],
            [
                "item_price.tenant_id",
                "item_price.company_id",
                "item_price.currency",
                "item_price.id",
            ],
            name="fk_v91_1",
        ),
        CheckConstraint("row_version >= 1", name="v91_0"),
        CheckConstraint(
            "(draft_id IS NOT NULL AND price_id IS NULL) OR (draft_id IS NULL AND price_id "
            "IS NOT NULL)",
            name="v91_1",
        ),
        CheckConstraint("min_quantity >= 0", name="v91_2"),
        CheckConstraint("max_quantity IS NULL OR max_quantity > min_quantity", name="v91_3"),
        CheckConstraint("amount >= 0", name="v91_4"),
        MARIADB_TABLE_ARGS,
    )
    draft_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    price_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    min_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    max_quantity: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


class PurchasePriceTerm(PricingRow):
    __tablename__ = "purchase_price_term"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v92_0"),
        UniqueConstraint("tenant_id", "company_id", "draft_id", name="uq_v92_1"),
        UniqueConstraint("tenant_id", "company_id", "price_id", name="uq_v92_2"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "currency", "draft_id"],
            [
                "item_price_draft.tenant_id",
                "item_price_draft.company_id",
                "item_price_draft.currency",
                "item_price_draft.id",
            ],
            name="fk_v92_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "currency", "price_id"],
            [
                "item_price.tenant_id",
                "item_price.company_id",
                "item_price.currency",
                "item_price.id",
            ],
            name="fk_v92_1",
        ),
        CheckConstraint("row_version >= 1", name="v92_0"),
        CheckConstraint(
            "(draft_id IS NOT NULL AND price_id IS NULL) OR (draft_id IS NULL AND price_id "
            "IS NOT NULL)",
            name="v92_1",
        ),
        CheckConstraint("gross_amount > 0", name="v92_2"),
        CheckConstraint("discount_value >= 0", name="v92_3"),
        CheckConstraint(
            "(discount_kind = 'NONE' AND discount_value = 0) OR (discount_kind = 'PERCENT' "
            "AND discount_value <= 100) OR (discount_kind = 'FIXED_PER_BASIS' AND "
            "discount_value <= gross_amount)",
            name="v92_4",
        ),
        MARIADB_TABLE_ARGS,
    )
    draft_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    price_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    gross_amount: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    discount_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    discount_value: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


class ItemReferenceCost(PricingRow):
    __tablename__ = "item_reference_cost"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v93_0"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "item_id",
            "unit_revision_id",
            "currency",
            "estimate_kind",
            "valid_from",
            name="uq_v93_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_v93_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_revision_id"],
            [
                "item_unit_revision.tenant_id",
                "item_unit_revision.company_id",
                "item_unit_revision.id",
            ],
            name="fk_v93_1",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "company_id",
                "item_id",
                "unit_revision_id",
                "currency",
                "numeric_revision_id",
            ],
            [
                "item_price_numeric_revision.tenant_id",
                "item_price_numeric_revision.company_id",
                "item_price_numeric_revision.item_id",
                "item_price_numeric_revision.unit_revision_id",
                "item_price_numeric_revision.currency",
                "item_price_numeric_revision.id",
            ],
            name="fk_v93_2",
        ),
        CheckConstraint("row_version >= 1", name="v93_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="v93_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="v93_2"),
        CheckConstraint("amount > 0", name="v93_3"),
        CheckConstraint("price_basis_quantity > 0", name="v93_4"),
        CheckConstraint("tax_basis IN ('EXCLUSIVE','INCLUSIVE')", name="v93_5"),
        CheckConstraint(
            "estimate_kind IN ('STANDARD_ESTIMATE','REPLACEMENT_ESTIMATE','SERVICE_ESTIMATE')",
            name="v93_6",
        ),
        CheckConstraint("tax_basis = 'EXCLUSIVE'", name="v93_7"),
        Index(
            "ix_v93_0",
            "tenant_id",
            "company_id",
            "item_id",
            "unit_revision_id",
            "currency",
            "estimate_kind",
            "valid_from",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    numeric_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    price_basis_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    tax_basis: Mapped[str] = mapped_column(String(12), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    estimate_kind: Mapped[str] = mapped_column(String(24), nullable=False)


class ItemMrp(PricingRow):
    __tablename__ = "item_mrp"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v94_0"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "item_id",
            "unit_revision_id",
            "currency",
            "jurisdiction",
            "valid_from",
            name="uq_v94_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_v94_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_revision_id"],
            [
                "item_unit_revision.tenant_id",
                "item_unit_revision.company_id",
                "item_unit_revision.id",
            ],
            name="fk_v94_1",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "company_id",
                "item_id",
                "unit_revision_id",
                "currency",
                "numeric_revision_id",
            ],
            [
                "item_price_numeric_revision.tenant_id",
                "item_price_numeric_revision.company_id",
                "item_price_numeric_revision.item_id",
                "item_price_numeric_revision.unit_revision_id",
                "item_price_numeric_revision.currency",
                "item_price_numeric_revision.id",
            ],
            name="fk_v94_2",
        ),
        CheckConstraint("row_version >= 1", name="v94_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="v94_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="v94_2"),
        CheckConstraint("amount > 0", name="v94_3"),
        CheckConstraint("price_basis_quantity > 0", name="v94_4"),
        CheckConstraint("tax_basis IN ('EXCLUSIVE','INCLUSIVE')", name="v94_5"),
        CheckConstraint("tax_basis = 'INCLUSIVE'", name="v94_6"),
        Index(
            "ix_v94_0",
            "tenant_id",
            "company_id",
            "item_id",
            "unit_revision_id",
            "currency",
            "jurisdiction",
            "valid_from",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    numeric_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    price_basis_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    tax_basis: Mapped[str] = mapped_column(String(12), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)


class ItemPriceFormula(PricingRow):
    __tablename__ = "item_price_formula"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v95_0"),
        UniqueConstraint("tenant_id", "company_id", "draft_id", name="uq_v95_1"),
        UniqueConstraint("tenant_id", "company_id", "price_id", name="uq_v95_2"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "draft_id"],
            ["item_price_draft.tenant_id", "item_price_draft.company_id", "item_price_draft.id"],
            name="fk_v95_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "price_id"],
            ["item_price.tenant_id", "item_price.company_id", "item_price.id"],
            name="fk_v95_1",
        ),
        CheckConstraint("row_version >= 1", name="v95_0"),
        CheckConstraint(
            "(draft_id IS NOT NULL AND price_id IS NULL) OR (draft_id IS NULL AND price_id "
            "IS NOT NULL)",
            name="v95_1",
        ),
        CheckConstraint("percentage >= 0", name="v95_2"),
        CheckConstraint(
            "(recipe = 'MRP_LESS_PERCENT' AND percentage <= 100 AND jurisdiction IS NOT "
            "NULL AND estimate_kind IS NULL) OR (recipe IN "
            "('REFERENCE_COST_PLUS_MARKUP','REFERENCE_COST_TARGET_MARGIN') AND "
            "estimate_kind IS NOT NULL AND jurisdiction IS NULL)",
            name="v95_3",
        ),
        CheckConstraint(
            "recipe <> 'REFERENCE_COST_TARGET_MARGIN' OR percentage < 100", name="v95_4"
        ),
        CheckConstraint("rounding_mode IN ('HALF_UP','UP','DOWN')", name="v95_5"),
        MARIADB_TABLE_ARGS,
    )
    draft_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    price_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    recipe: Mapped[str] = mapped_column(String(32), nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    estimate_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rounding_mode: Mapped[str] = mapped_column(String(10), nullable=False)


class CommercialPolicyScope(PricingRow):
    __tablename__ = "commercial_policy_scope"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v96_0"),
        UniqueConstraint("tenant_id", "company_id", "owner_kind", "owner_id", name="uq_v96_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "group_id"],
            ["item_group.tenant_id", "item_group.company_id", "item_group.id"],
            name="fk_v96_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "family_id"],
            ["product_family.tenant_id", "product_family.company_id", "product_family.id"],
            name="fk_v96_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_v96_2",
        ),
        CheckConstraint("row_version >= 1", name="v96_0"),
        CheckConstraint(
            "(owner_kind = 'COMPANY' AND owner_id = company_id AND group_id IS NULL AND "
            "family_id IS NULL AND item_id IS NULL) OR (owner_kind = 'GROUP' AND owner_id ="
            " group_id AND group_id IS NOT NULL AND family_id IS NULL AND item_id IS NULL) "
            "OR (owner_kind = 'FAMILY' AND owner_id = family_id AND family_id IS NOT NULL "
            "AND group_id IS NULL AND item_id IS NULL) OR (owner_kind = 'SKU' AND owner_id "
            "= item_id AND item_id IS NOT NULL AND group_id IS NULL AND family_id IS NULL)",
            name="v96_1",
        ),
        MARIADB_TABLE_ARGS,
    )
    owner_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    family_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class CommercialGuardRule(PricingRow):
    __tablename__ = "commercial_guard_rule"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v97_0"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "item_id",
            "unit_revision_id",
            "currency",
            "rule_kind",
            "valid_from",
            name="uq_v97_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_v97_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_revision_id"],
            [
                "item_unit_revision.tenant_id",
                "item_unit_revision.company_id",
                "item_unit_revision.id",
            ],
            name="fk_v97_1",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "company_id",
                "item_id",
                "unit_revision_id",
                "currency",
                "numeric_revision_id",
            ],
            [
                "item_price_numeric_revision.tenant_id",
                "item_price_numeric_revision.company_id",
                "item_price_numeric_revision.item_id",
                "item_price_numeric_revision.unit_revision_id",
                "item_price_numeric_revision.currency",
                "item_price_numeric_revision.id",
            ],
            name="fk_v97_2",
        ),
        CheckConstraint("row_version >= 1", name="v97_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="v97_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="v97_2"),
        CheckConstraint("price_basis_quantity > 0", name="v97_3"),
        CheckConstraint("tax_basis = 'EXCLUSIVE'", name="v97_4"),
        CheckConstraint("severity IN ('BLOCK','REQUIRE_APPROVAL')", name="v97_5"),
        CheckConstraint(
            "(rule_kind IN ('FIXED_MIN','FIXED_MAX') AND amount IS NOT NULL AND amount > 0 "
            "AND percentage IS NULL AND estimate_kind IS NULL) OR (rule_kind IN "
            "('MIN_MARGIN','MIN_MARKUP') AND amount IS NULL AND percentage IS NOT NULL AND "
            "percentage >= 0 AND estimate_kind IS NOT NULL)",
            name="v97_6",
        ),
        CheckConstraint("rule_kind <> 'MIN_MARGIN' OR percentage < 100", name="v97_7"),
        Index(
            "ix_v97_0",
            "tenant_id",
            "company_id",
            "item_id",
            "unit_revision_id",
            "currency",
            "valid_from",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    unit_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    numeric_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    rule_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    price_basis_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    tax_basis: Mapped[str] = mapped_column(String(12), nullable=False)
    estimate_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)


class DiscountCeiling(PricingRow):
    __tablename__ = "discount_ceiling"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v98_0"),
        UniqueConstraint("tenant_id", "company_id", "scope_id", "valid_from", name="uq_v98_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "scope_id"],
            [
                "commercial_policy_scope.tenant_id",
                "commercial_policy_scope.company_id",
                "commercial_policy_scope.id",
            ],
            name="fk_v98_0",
        ),
        CheckConstraint("row_version >= 1", name="v98_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="v98_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="v98_2"),
        CheckConstraint("max_discount_pct BETWEEN 0 AND 100", name="v98_3"),
        Index("ix_v98_0", "tenant_id", "company_id", "scope_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    max_discount_pct: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class ItemCommercialPolicy(PricingRow):
    __tablename__ = "item_commercial_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_v99_0"),
        UniqueConstraint("tenant_id", "company_id", "item_id", "valid_from", name="uq_v99_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_v99_0",
        ),
        CheckConstraint("row_version >= 1", name="v99_0"),
        CheckConstraint("valid_from >= '1000-01-01'", name="v99_1"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="v99_2"),
        Index("ix_v99_0", "tenant_id", "company_id", "item_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    free_sale_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class PriceLevelAssignmentScope(PricingRow):
    """Unique CUSTOMER or PRICING_TYPE subject.

    A subject appears at most once per company. Every dated assignment (see
    :class:`PriceLevelAssignment`) points at one scope row, so a subject's
    history is captured by adjacent dated bindings sharing the scope.
    """

    __tablename__ = "price_level_assignment_scope"
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_pla_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "subject_kind",
            "customer_ref",
            "pricing_type_ref",
            name="uq_pla_scope_subject",
        ),
        CheckConstraint(
            "(subject_kind = 'CUSTOMER' AND customer_ref IS NOT NULL AND pricing_type_ref IS NULL) "
            "OR (subject_kind = 'PRICING_TYPE' AND pricing_type_ref IS NOT NULL "
            "AND customer_ref IS NULL)",
            name=conv("ck_pla_scope_subject"),
        ),
        CheckConstraint("row_version >= 1", name=conv("ck_pla_scope_row_version")),
        Index("ix_pla_scope_tenant_id", "tenant_id"),
        MARIADB_TABLE_ARGS,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_ref: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    pricing_type_ref: Mapped[str | None] = mapped_column(String(40), nullable=True)


class PriceLevelAssignment(PricingRow):
    """Dated scope-to-price_level binding.

    Non-overlapping periods per scope are the business rule; the schema enforces
    date validity but non-overlap is checked in the domain layer during writes.
    """

    __tablename__ = "price_level_assignment"
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_pla_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "scope_id"],
            [
                "price_level_assignment_scope.tenant_id",
                "price_level_assignment_scope.company_id",
                "price_level_assignment_scope.id",
            ],
            name="fk_pla_scope",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "price_level_id"],
            ["price_level.tenant_id", "price_level.company_id", "price_level.id"],
            name="fk_pla_level",
        ),
        CheckConstraint("row_version >= 1", name=conv("ck_pla_row_version")),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name=conv("ck_pla_dates")),
        Index("ix_pla_tenant_id", "tenant_id"),
        Index("ix_pla_effective", "tenant_id", "company_id", "scope_id", "valid_from"),
        MARIADB_TABLE_ARGS,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    price_level_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


PRICING_MODELS = (
    PriceLevel,
    PricePlan,
    CompanyPricingPolicy,
    ItemPriceScope,
    ItemPriceNumericRevision,
    ItemPriceSeries,
    ItemPriceDraft,
    ItemPrice,
    ItemPriceTier,
    PurchasePriceTerm,
    ItemReferenceCost,
    ItemMrp,
    ItemPriceFormula,
    CommercialPolicyScope,
    CommercialGuardRule,
    DiscountCeiling,
    ItemCommercialPolicy,
    PriceLevelAssignmentScope,
    PriceLevelAssignment,
)
