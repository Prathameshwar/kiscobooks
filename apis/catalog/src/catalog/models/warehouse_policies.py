"""Per-product location policy and replenishment bands. Definitions only; no balances.

docs/catalog-warehouses.md §2, §3. Catalog owns *where a product may be kept and how much
of it to keep there*; Billing owns what is actually in the location. Nothing here counts,
holds or moves stock, and no rule in ``domain/warehouse_policy_composition`` is satisfied by
inferring a quantity from these rows.

The three tables split along what each one *is*, not along convenience:

* ``item_warehouse_policy`` — the product's selection mode and its optional activity
  defaults. One row per product; its absence means the documented baseline.
* ``item_warehouse_permission`` — one row per permitted location, carrying the eight typed
  operation flags. A restriction cannot exist without its mode row: the foreign key points
  at ``item_warehouse_policy``'s scoped item key, so that is a schema fact.
* ``item_replenishment_policy`` — the reviewed stock band, per location or for the product
  as a whole.
"""

import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Quantity, Uuid7
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog.domain.warehouse_policy_composition import MAX_LEAD_TIME_DAYS
from catalog.domain.warehouses import OPERATION_FLAGS
from catalog.models.pricing import PricingRow

#: The scope key of a band that applies to the product everywhere rather than at one
#: location. A sentinel rather than ``NULL`` because MySQL treats NULLs in a unique index as
#: distinct, so "one product-wide band per product" would not be a constraint at all — two
#: rows with a NULL location would both be accepted. ``warehouse_id`` stays nullable and
#: carries the real reference; the check below keeps the two columns in agreement.
ITEM_WIDE_SCOPE: uuid.UUID = uuid.UUID(int=0)
_ITEM_WIDE_SQL = "X'00000000000000000000000000000000'"


class ItemWarehousePolicy(PricingRow):
    """One product's location selection mode and its optional activity defaults.

    A missing row is meaningful: it is the ``ALLOW_ALL_ACTIVE`` baseline, so the product
    reaches wherever the *location's* own reviewed policy allows. That is why there is no
    ``is_active`` here — a product either has a stored policy or has the baseline, and a
    retired policy row would be a third state with no defined meaning.
    """

    __tablename__ = "item_warehouse_policy"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "item_id", name="uq_item_warehouse_policy_item"
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_item_warehouse_policy_scope_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_item_warehouse_policy_item",
        ),
        *(
            ForeignKeyConstraint(
                ["tenant_id", "company_id", column],
                ["warehouse.tenant_id", "warehouse.company_id", "warehouse.id"],
                name="fk_item_warehouse_policy_" + label,
            )
            for column, label in (
                ("default_sale_warehouse_id", "sale"),
                ("default_purchase_warehouse_id", "purchase"),
                ("default_customer_return_warehouse_id", "customer_return"),
                ("default_opening_warehouse_id", "opening"),
            )
        ),
        # Short local names: the convention prefixes the table, and these tables are long
        # enough that the usual "<table>_<rule>" form crowds MySQL's 64-character limit.
        CheckConstraint("row_version >= 1", name="row_version"),
        CheckConstraint(
            "selection_mode IN ('ALLOW_ALL_ACTIVE','ALLOW_LIST')", name="selection_mode"
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    selection_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The product's own activity defaults, outranking the company's and outranked by an
    #: explicit choice on the document (docs/catalog-warehouses.md §3). ``NULL`` means *not
    #: configured*, so resolution falls through to the company default — it never means
    #: "no location", which would be a fourth precedence level nothing documents.
    default_sale_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    default_purchase_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    default_customer_return_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7, nullable=True
    )
    default_opening_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class ItemWarehousePermission(PricingRow):
    """One product at one location: whether it may be kept there, and for which operations.

    Typed columns, never a JSON operation map, for the reason the location's own revision
    gives: a flag that lived in a JSON key could not be constrained, indexed or migrated,
    and a typo in it would read as "denied" on one release and "allowed" on the next.

    The flags are a **ceiling narrowed by the location's own policy**, never an addition to
    it: composition intersects the two, and a write that names an operation the location
    does not allow is refused rather than trimmed
    (``domain/warehouse_policy_composition.assert_narrows``).
    """

    __tablename__ = "item_warehouse_permission"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "item_id",
            "warehouse_id",
            name="uq_item_warehouse_perm_scope",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_item_warehouse_perm_scope_id"),
        # The parent is the *policy*, not the item: a restriction with no selection mode
        # would be a stored authorization claim with nothing saying how to read it.
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            [
                "item_warehouse_policy.tenant_id",
                "item_warehouse_policy.company_id",
                "item_warehouse_policy.item_id",
            ],
            name="fk_item_warehouse_perm_policy",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "warehouse_id"],
            ["warehouse.tenant_id", "warehouse.company_id", "warehouse.id"],
            name="fk_item_warehouse_perm_location",
        ),
        # Answers "does anything still permit this product at that location" for the
        # deactivation fence without a scan (docs/catalog-warehouses.md §5).
        Index(
            "ix_item_warehouse_perm_location",
            "tenant_id",
            "company_id",
            "warehouse_id",
            "is_active",
        ),
        CheckConstraint("row_version >= 1", name="row_version"),
        CheckConstraint(" AND ".join(flag + " IN (0,1)" for flag in OPERATION_FLAGS), name="flags"),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: Retirement rather than deletion: the row is referenced by the location deactivation
    #: fence and by audit history, and a hard delete would erase the record of a product
    #: having been stocked somewhere.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_sale_issue: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_purchase_receipt: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_transfer_in: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_transfer_out: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_customer_return_receipt: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_supplier_return_issue: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_opening_stock: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_adjustment: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ItemReplenishmentPolicy(PricingRow):
    """The reviewed stock band for one product, at one location or across all of them.

    Quantities are ``DECIMAL(19,4)`` with the product's own unit grid validated on top: the
    stored scale is fixed platform-wide, and the grid is what makes ``0.5`` of a
    whole-number unit a rejection rather than a silently rounded band.

    Catalog stores the band and the unit it is ordered in. Comparing it against an on-hand
    quantity, and raising anything from it, is Billing's — this row is a definition.
    """

    __tablename__ = "item_replenishment_policy"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "item_id",
            "scope_warehouse_id",
            name="uq_item_replenishment_scope",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_item_replenishment_scope_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_item_replenishment_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "warehouse_id"],
            ["warehouse.tenant_id", "warehouse.company_id", "warehouse.id"],
            name="fk_item_replenishment_location",
        ),
        # Four columns, so "the ordering unit belongs to *this* product" is a schema fact
        # rather than a check somebody has to remember to write.
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id", "purchase_binding_id"],
            [
                "item_unit_binding.tenant_id",
                "item_unit_binding.company_id",
                "item_unit_binding.item_id",
                "item_unit_binding.id",
            ],
            name="fk_item_replenishment_unit",
        ),
        Index(
            "ix_item_replenishment_location",
            "tenant_id",
            "company_id",
            "warehouse_id",
            "is_active",
        ),
        CheckConstraint(
            f"row_version >= 1 AND lead_time_days BETWEEN 0 AND {MAX_LEAD_TIME_DAYS}",
            name="version",
        ),
        CheckConstraint(
            "safety_quantity >= 0 AND reorder_quantity >= safety_quantity "
            "AND target_quantity >= reorder_quantity AND target_quantity > 0 "
            "AND min_order_quantity > 0 AND order_multiple > 0 "
            "AND (max_order_quantity IS NULL OR max_order_quantity >= min_order_quantity)",
            name="quantities",
        ),
        CheckConstraint(
            f"(warehouse_id IS NULL AND scope_warehouse_id = {_ITEM_WIDE_SQL}) "
            "OR (warehouse_id IS NOT NULL AND scope_warehouse_id = warehouse_id)",
            name="scope",
        ),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: The unique key's location component: the location id, or ``ITEM_WIDE_SCOPE`` for the
    #: product-wide band. Never a reference — it is a key, and the check above ties it to
    #: ``warehouse_id``, which is the reference.
    scope_warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    #: The unit the band is expressed and ordered in, as one of the product's own unit
    #: bindings. Storing the binding rather than the unit keeps the conversion the product
    #: already declared: a band in cartons means *this product's* carton.
    purchase_binding_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    safety_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    reorder_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    target_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    min_order_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    max_order_quantity: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    order_multiple: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


WAREHOUSE_POLICY_MODELS = (
    ItemWarehousePolicy,
    ItemWarehousePermission,
    ItemReplenishmentPolicy,
)
