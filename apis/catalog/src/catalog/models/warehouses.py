"""One location model for stores, godowns and internal transit; stock stays external.

Catalog owns what a location *is*. Quantities, availability, holds and transfers belong to
Billing (docs/catalog-inventory-integration.md §2), so nothing here counts stock.
"""

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog.domain.warehouse_resolution import ACTIVITY_DEFAULTS
from catalog.domain.warehouses import OPERATION_FLAGS
from catalog.models.classification import ClassificationMaster
from catalog.models.commercial import master_constraints
from catalog.models.pricing import PricingRow


class Warehouse(ClassificationMaster):
    """A store, godown or the company's internal transit custody scope.

    ``uq_warehouse_scope_code`` is what makes "exactly one Main per company" a schema fact
    rather than a code convention: the reserved codes are unique per company and the
    ``warehouse_system_code`` check ties them to ``is_system``.
    """

    __tablename__ = "warehouse"
    __table_args__ = (
        *master_constraints("warehouse"),
        ForeignKeyConstraint(["country_code"], ["country.code"], name="fk_warehouse_country"),
        ForeignKeyConstraint(
            ["country_code", "state_code"],
            ["state.country_code", "state.code"],
            name="fk_warehouse_state",
        ),
        CheckConstraint("kind IN ('STORE','GODOWN','INTERNAL_TRANSIT')", name="warehouse_kind"),
        CheckConstraint(
            "(is_system = 0 AND code NOT IN ('MAIN','TRANSIT')) OR "
            "(is_system = 1 AND code IN ('MAIN','TRANSIT'))",
            name="warehouse_system_code",
        ),
        CheckConstraint(
            "(kind <> 'INTERNAL_TRANSIT' OR code = 'TRANSIT') AND "
            "(code <> 'TRANSIT' OR kind = 'INTERNAL_TRANSIT')",
            name="warehouse_transit_code",
        ),
        CheckConstraint("state_code IS NULL OR country_code IS NOT NULL", name="warehouse_state"),
        Index("ix_warehouse_kind", "tenant_id", "company_id", "kind", "is_active", "id"),
        Index("ix_warehouse_country_state", "country_code", "state_code"),
        Index("ix_warehouse_tax_registration", "tenant_id", "company_id", "tax_registration_id"),
        MARIADB_TABLE_ARGS,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Provisioned by Catalog's bootstrap, never by a client. Reserved from create,
    #: identity change and deactivation (docs/catalog-warehouses.md §1).
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: An Identity department. Catalog holds no department projection, so this is an
    #: opaque reference for display and reporting; it is never resolved and never
    #: participates in authorization, exactly like ``brand.owner_party_id``.
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(60), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: Ship-from tax location. Resolution by a document's posting date is Billing's;
    #: Catalog only records the fact.
    country_code: Mapped[str | None] = mapped_column(CHAR(2), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    #: Authoritative Identity tax registration ID (e.g. GSTIN in India).
    #: Used by Vouchers/Accounting to determine issuing GSTIN and Place of Supply.
    tax_registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class WarehouseBin(ClassificationMaster):
    """A named subdivision inside one location: rack, shelf, cold room.

    Parent-scoped, so `A1` in one godown and `A1` in another are different bins and neither
    has to invent a globally unique code. A bin is subordinate to its location in every
    sense — it holds no operation policy of its own, and reaching it requires reaching the
    location (docs/catalog-warehouses.md §3). It is not a grouping dimension, and a group is
    not a place to put stock; the two are not substitutes.
    """

    __tablename__ = "warehouse_bin"
    __table_args__ = (
        *master_constraints("warehouse_bin", parent="warehouse_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "warehouse_id"],
            ["warehouse.tenant_id", "warehouse.company_id", "warehouse.id"],
            name="fk_warehouse_bin_warehouse",
        ),
        Index("ix_warehouse_bin_parent", "tenant_id", "company_id", "warehouse_id", "is_active"),
        MARIADB_TABLE_ARGS,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class CompanyWarehouseConfiguration(PricingRow):
    """The company's location singleton: built-in Main, transit custody, activity defaults.

    Activity defaults are current-state pointers with audited history, not dated rows: a
    default is resolution convenience evaluated when an operation happens, never a term that
    prices or posts (docs/catalog-warehouses.md §6).
    """

    __tablename__ = "company_warehouse_configuration"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", name="uq_company_warehouse_configuration_company"
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_company_warehouse_configuration_scope_id"
        ),
        *(
            ForeignKeyConstraint(
                ["tenant_id", "company_id", column],
                ["warehouse.tenant_id", "warehouse.company_id", "warehouse.id"],
                name="fk_company_warehouse_configuration_" + label,
            )
            for column, label in (
                ("main_warehouse_id", "main"),
                ("transit_warehouse_id", "transit"),
                ("default_sale_warehouse_id", "sale"),
                ("default_purchase_warehouse_id", "purchase"),
                ("default_customer_return_warehouse_id", "customer_return"),
                ("default_opening_warehouse_id", "opening"),
            )
        ),
        # Short local names: the convention prefixes the table, and this one is long
        # enough that the usual "<table>_<rule>" form exceeds MySQL's 64-character limit.
        CheckConstraint("row_version >= 1", name="row_version"),
        CheckConstraint("source_version > 0", name="source_version"),
        CheckConstraint("main_warehouse_id <> transit_warehouse_id", name="custody"),
        MARIADB_TABLE_ARGS,
    )
    #: Immutable after insert. Rewriting it would re-point every document that resolved to
    #: the built-in location without the resolver being able to tell.
    main_warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: Reached only by typed transfer handlers; never selectable, never a default.
    transit_warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    default_sale_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    default_purchase_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    default_customer_return_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7, nullable=True
    )
    default_opening_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    #: The Identity projection checkpoint the built-in set was derived from, so a later
    #: defaults change can refuse to act on a stale company/feature picture.
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)


class WarehouseOperationPolicyRevision(PricingRow):
    """What one location is allowed to do, as a numbered revision with a UTC window.

    Typed columns, never a JSON operation map: an operation whose flag is a JSON key is an
    operation nothing can index, constrain or migrate, and a typo in it reads as "denied"
    on one release and "allowed" on the next (docs/catalog-warehouses.md §6).

    Rows are immutable once written except for ``effective_to``, which the next revision
    closes. The window is server-assigned: these are live controls resolved at operation
    time, so a caller-supplied start date would be a backdated permission change (§5).
    """

    __tablename__ = "warehouse_operation_policy_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_warehouse_policy_rev_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "warehouse_id",
            "revision",
            name="uq_warehouse_policy_rev_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "warehouse_id"],
            ["warehouse.tenant_id", "warehouse.company_id", "warehouse.id"],
            name="fk_warehouse_policy_rev_parent",
        ),
        Index(
            "ix_warehouse_policy_rev_window",
            "tenant_id",
            "company_id",
            "warehouse_id",
            "effective_to",
            "revision",
            "id",
        ),
        # Short local names: the convention prefixes the table, and this one is long
        # enough that the usual "<table>_<rule>" form exceeds MySQL's 64-character limit.
        CheckConstraint("revision >= 1 AND row_version >= 1", name="version"),
        CheckConstraint(" AND ".join(flag + " IN (0,1)" for flag in OPERATION_FLAGS), name="flags"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="window"),
        MARIADB_TABLE_ARGS,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    #: When this revision took force. Equal to its publication instant; there are no
    #: drafts, so a stored revision is always a published one.
    effective_from: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    #: Closed by the successor revision. NULL is the one in force.
    effective_to: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    allow_sale_issue: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_purchase_receipt: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_transfer_in: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_transfer_out: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_customer_return_receipt: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_supplier_return_issue: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_opening_stock: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_adjustment: Mapped[bool] = mapped_column(Boolean, nullable=False)


WAREHOUSE_MODELS = (
    Warehouse,
    WarehouseBin,
    CompanyWarehouseConfiguration,
    WarehouseOperationPolicyRevision,
)
#: The four activity-default columns, taken from the resolver's own map rather than restated:
#: a fifth default added there without a matching column here — or a column this list forgot —
#: would leave the retirement fence checking three pointers out of four.
DEFAULT_POINTERS = tuple(ACTIVITY_DEFAULTS)
