"""Company-owned, dated India GST definitions and immutable activation evidence."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Quantity, Uuid7
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.pricing import PricingRow


def scope(name: str) -> tuple[Any, ...]:
    return (
        UniqueConstraint("tenant_id", "company_id", "id", name=f"uq_{name}_scope"),
        CheckConstraint("row_version >= 1", name="version"),
    )


def reference(name: str, field: str, target: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "company_id", field],
        [f"{target}.tenant_id", f"{target}.company_id", f"{target}.id"],
        name=f"fk_{name}_{field}",
    )


def dated(name: str, *keys: str) -> tuple[Any, ...]:
    return (
        CheckConstraint("valid_from >= '1000-01-01'", name="start"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="dates"),
        Index(f"ix_{name}_date", "tenant_id", "company_id", *keys, "valid_from", "id"),
    )


class TaxClassification(PricingRow):
    __tablename__ = "tax_classification"
    __table_args__ = (
        *scope("tax_classification"),
        *dated("tax_classification", "code_system", "code"),
        CheckConstraint("jurisdiction = 'IN'", name="jurisdiction"),
        CheckConstraint(
            "(code_system = 'HSN' AND item_kind = 'GOODS') OR (code_system = 'SAC' AND "
            "item_kind = 'SERVICE')",
            name="kind",
        ),
        Index("ix_tax_classification_code", "tenant_id", "company_id", "code", "id"),
        MARIADB_TABLE_ARGS,
    )
    jurisdiction: Mapped[str] = mapped_column(String(2), nullable=False)
    code_system: Mapped[str] = mapped_column(String(3), nullable=False)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    item_kind: Mapped[str] = mapped_column(String(7), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class TaxCategory(PricingRow):
    __tablename__ = "tax_category"
    __table_args__ = (
        *scope("tax_category"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_tax_category_code"),
        Index("ix_tax_category_name", "tenant_id", "company_id", "name", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class TaxRule(PricingRow):
    __tablename__ = "tax_rule"
    __table_args__ = (
        *scope("tax_rule"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_tax_rule_code"),
        reference("tax_rule", "tax_category_id", "tax_category"),
        CheckConstraint("tax_system = 'gst_in' AND jurisdiction = 'IN'", name="jurisdiction"),
        CheckConstraint("item_kind IN ('GOODS','SERVICE')", name="kind"),
        CheckConstraint(
            "treatment IN ('TAXABLE','NIL_RATED','EXEMPT','NON_GST')", name="treatment"
        ),
        CheckConstraint("classification_scope IN ('SPECIFIC','ANY')", name="classification_scope"),
        Index("ix_tax_rule_name", "tenant_id", "company_id", "name", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tax_system: Mapped[str] = mapped_column(String(10), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(2), nullable=False)
    item_kind: Mapped[str] = mapped_column(String(7), nullable=False)
    treatment: Mapped[str] = mapped_column(String(10), nullable=False)
    classification_scope: Mapped[str] = mapped_column(
        String(8), nullable=False, default="SPECIFIC", server_default="SPECIFIC"
    )
    tax_category_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class TaxRateSeries(PricingRow):
    __tablename__ = "tax_rate_series"
    __table_args__ = (
        *scope("tax_rate_series"),
        reference("tax_rate_series", "rule_id", "tax_rule"),
        UniqueConstraint(
            "tenant_id", "company_id", "rule_id", "applicability", name="uq_tax_rate_series_context"
        ),
        CheckConstraint(
            "applicability IN ('INTRA_STATE','INTRA_UT','INTER_STATE')", name="applicability"
        ),
        MARIADB_TABLE_ARGS,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    applicability: Mapped[str] = mapped_column(String(12), nullable=False)


class TaxRate(PricingRow):
    __tablename__ = "tax_rate"
    __table_args__ = (
        *scope("tax_rate"),
        *dated("tax_rate", "series_id"),
        reference("tax_rate", "series_id", "tax_rate_series"),
        reference("tax_rate", "supersedes_id", "tax_rate"),
        MARIADB_TABLE_ARGS,
    )
    series_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class TaxRateComponent(PricingRow):
    __tablename__ = "tax_rate_component"
    __table_args__ = (
        *scope("tax_rate_component"),
        reference("tax_component", "rate_id", "tax_rate"),
        reference("tax_component", "unit_id", "unit_of_measure"),
        UniqueConstraint(
            "tenant_id", "company_id", "rate_id", "component_key", name="uq_tax_component_key"
        ),
        CheckConstraint("component IN ('CGST','SGST','UTGST','IGST','CESS')", name="component"),
        CheckConstraint(
            "(kind = 'PERCENT' AND percentage IS NOT NULL AND percentage >= 0 "
            "AND (component = 'CESS' OR percentage <= 100) AND "
            "amount IS NULL AND currency IS NULL AND unit_id IS NULL AND basis_quantity IS "
            "NULL) OR (kind = 'FIXED_PER_UNIT' AND component = 'CESS' AND percentage IS NULL "
            "AND amount IS NOT NULL AND amount > 0 AND currency IS NOT NULL AND unit_id IS NOT "
            "NULL AND basis_quantity IS NOT NULL AND basis_quantity > 0)",
            name="shape",
        ),
        CheckConstraint("rounding_mode IN ('HALF_UP','UP','DOWN')", name="rounding"),
        CheckConstraint("position BETWEEN 0 AND 15", name="position"),
        Index("ix_tax_component_order", "tenant_id", "company_id", "rate_id", "position", "id"),
        MARIADB_TABLE_ARGS,
    )
    rate_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    component_key: Mapped[str] = mapped_column(String(30), nullable=False)
    component: Mapped[str] = mapped_column(String(5), nullable=False)
    kind: Mapped[str] = mapped_column(String(14), nullable=False)
    percentage: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    basis_quantity: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    rounding_mode: Mapped[str] = mapped_column(String(7), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class CatalogTaxScope(PricingRow):
    __tablename__ = "catalog_tax_scope"
    __table_args__ = (
        *scope("catalog_tax_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "owner_kind", "owner_id", name="uq_catalog_tax_scope_owner"
        ),
        reference("tax_scope", "group_id", "item_group"),
        reference("tax_scope", "family_id", "product_family"),
        reference("tax_scope", "item_id", "item"),
        CheckConstraint(
            "(owner_kind = 'COMPANY' AND owner_id = company_id AND group_id IS NULL AND "
            "family_id IS NULL AND item_id IS NULL) OR (owner_kind = 'GROUP' AND owner_id = "
            "group_id AND group_id IS NOT NULL AND family_id IS NULL AND item_id IS NULL) OR "
            "(owner_kind = 'FAMILY' AND owner_id = family_id AND family_id IS NOT NULL AND "
            "group_id IS NULL AND item_id IS NULL) OR (owner_kind = 'SKU' AND owner_id = "
            "item_id AND item_id IS NOT NULL AND group_id IS NULL AND family_id IS NULL)",
            name="owner",
        ),
        MARIADB_TABLE_ARGS,
    )
    owner_kind: Mapped[str] = mapped_column(String(7), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    family_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class CatalogTaxBinding(PricingRow):
    __tablename__ = "catalog_tax_binding"
    __table_args__ = (
        *scope("catalog_tax_binding"),
        *dated("catalog_tax_binding", "scope_id", "direction", "bundle"),
        reference("tax_binding", "scope_id", "catalog_tax_scope"),
        reference("tax_binding", "classification_id", "tax_classification"),
        reference("tax_binding", "tax_category_id", "tax_category"),
        reference("tax_binding", "rule_id", "tax_rule"),
        CheckConstraint("jurisdiction = 'IN'", name="jurisdiction"),
        CheckConstraint("direction IN ('SALE','PURCHASE')", name="direction"),
        CheckConstraint("bundle IN ('CLASSIFICATION','TREATMENT','RULE')", name="bundle"),
        CheckConstraint("item_kind IS NULL OR item_kind IN ('GOODS','SERVICE')", name="item_kind"),
        CheckConstraint(
            "treatment IS NULL OR treatment IN ('TAXABLE','NIL_RATED','EXEMPT','NON_GST')",
            name="treatment",
        ),
        CheckConstraint(
            "(mode IN ('INHERIT','REQUIRE_EXPLICIT') AND classification_id IS NULL AND "
            "treatment IS NULL AND exemption_reason IS NULL AND tax_category_id IS NULL AND "
            "rule_id IS NULL) OR (mode = 'OVERRIDE' AND ((bundle = 'CLASSIFICATION' AND "
            "classification_id IS NOT NULL AND treatment IS NULL AND exemption_reason IS NULL "
            "AND tax_category_id IS NULL AND rule_id IS NULL) OR (bundle = 'TREATMENT' AND "
            "classification_id IS NULL AND rule_id IS NULL AND treatment IS NOT NULL AND "
            "tax_category_id IS NOT NULL AND ((treatment IN ('EXEMPT','NON_GST') AND "
            "exemption_reason IS NOT NULL) OR (treatment IN ('TAXABLE','NIL_RATED') AND "
            "exemption_reason IS NULL))) OR (bundle = 'RULE' AND rule_id IS NOT NULL AND "
            "classification_id IS NULL AND treatment IS NULL AND exemption_reason IS NULL AND "
            "tax_category_id IS NULL)))",
            name="shape",
        ),
        MARIADB_TABLE_ARGS,
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(2), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    bundle: Mapped[str] = mapped_column(String(14), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    classification_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    treatment: Mapped[str | None] = mapped_column(String(10), nullable=True)
    exemption_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tax_category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    # NULL: every kind the scope admits. Set: a company/BOTH-group default for one kind.
    item_kind: Mapped[str | None] = mapped_column(String(7), nullable=True)


class ItemActivation(PricingRow):
    __tablename__ = "item_activation"
    __table_args__ = (
        *scope("item_activation"),
        UniqueConstraint("tenant_id", "company_id", "item_id", name="uq_item_activation_item"),
        reference("item_activation", "item_id", "item"),
        reference("item_activation", "adoption_id", "product_configuration_adoption"),
        CheckConstraint("source_version >= 1 AND policy_generation >= 1", name="versions"),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    adoption_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    activated_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    policy_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    preview_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ItemActivationSource(PricingRow):
    __tablename__ = "item_activation_source"
    __table_args__ = (
        *scope("item_activation_source"),
        reference("activation_source", "activation_id", "item_activation"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "activation_id",
            "entity_type",
            "entity_id",
            name="uq_activation_source_entity",
        ),
        CheckConstraint("entity_version >= 1", name="entity_version"),
        MARIADB_TABLE_ARGS,
    )
    activation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_version: Mapped[int] = mapped_column(Integer, nullable=False)


class ItemInventoryProfile(PricingRow):
    __tablename__ = "item_inventory_profile"
    __table_args__ = (
        *scope("item_inventory_profile"),
        UniqueConstraint(
            "tenant_id", "company_id", "item_id", name="uq_item_inventory_profile_item"
        ),
        reference("inventory_profile", "item_id", "item"),
        reference("inventory_profile", "base_unit_id", "unit_of_measure"),
        reference(
            "inventory_profile", "template_revision_id", "inventory_profile_template_revision"
        ),
        reference("inventory_profile", "identifier_profile_id", "identifier_profile"),
        CheckConstraint(
            "issue_strategy IN ('FIFO','FEFO') AND valuation_method IN "
            "('FIFO','MOVING_AVERAGE','SPECIFIC')",
            name="methods",
        ),
        CheckConstraint(
            "lot_tracking = 1 OR (expiry_required = 0 AND manufacture_date_required = 0 AND "
            "shelf_life_days IS NULL AND minimum_remaining_life_days IS NULL)",
            name="dates",
        ),
        CheckConstraint(
            "expiry_required = 1 OR (issue_strategy <> 'FEFO' AND minimum_remaining_life_days "
            "IS NULL)",
            name="expiry",
        ),
        CheckConstraint(
            "serial_tracking = 1 OR (identifier_profile_id IS NULL AND valuation_method <> "
            "'SPECIFIC')",
            name="serial",
        ),
        CheckConstraint(
            "shelf_life_days IS NULL OR shelf_life_days BETWEEN 1 AND 36500", name="shelf"
        ),
        CheckConstraint(
            "minimum_remaining_life_days IS NULL OR (minimum_remaining_life_days BETWEEN 0 AND "
            "36500 AND (shelf_life_days IS NULL OR minimum_remaining_life_days <= "
            "shelf_life_days))",
            name="remaining",
        ),
        CheckConstraint(
            "negative_stock_policy IN ('BLOCK','WARN','ALLOW')",
            name="negative_stock",
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    base_unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    template_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    identifier_profile_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    lot_tracking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    serial_tracking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expiry_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    manufacture_date_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_remaining_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issue_strategy: Mapped[str] = mapped_column(String(10), nullable=False)
    valuation_method: Mapped[str] = mapped_column(String(20), nullable=False)
    negative_stock_policy: Mapped[str] = mapped_column(
        String(10), nullable=False, default="BLOCK", server_default="BLOCK"
    )


# Imported after the native tax parents so governance foreign keys share these definitions.
from catalog.models.tax_governance import TaxHistoryAction as TaxHistoryAction  # noqa: E402
from catalog.models.tax_governance import TaxRelease as TaxRelease  # noqa: E402
from catalog.models.tax_governance import TaxRuleApplicability as TaxRuleApplicability  # noqa: E402

TAX_MODELS = (
    TaxClassification,
    TaxCategory,
    TaxRule,
    TaxRateSeries,
    TaxRate,
    TaxRateComponent,
    CatalogTaxScope,
    CatalogTaxBinding,
    TaxRuleApplicability,
    TaxRelease,
    TaxHistoryAction,
)
ACTIVATION_MODELS = (ItemActivation, ItemActivationSource, ItemInventoryProfile)
