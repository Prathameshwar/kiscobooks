"""Native accounting tables. No subtype owns a separate posting identity."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Money, UtcDateTime, Uuid7
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv


class Record(IdMixin, TenantMixin, AuditMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AccountHead(Record):
    __tablename__ = "account_head"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_head_scope"),
        Index("ix_account_head_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_head_version"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_account_head_0"),
        CheckConstraint(
            "nature IN ('ASSET', 'LIABILITY', 'EQUITY', 'INCOME', 'EXPENSE')",
            name="account_head_nature",
        ),
        Index("ix_account_head_name", "tenant_id", "company_id", "name", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    nature: Mapped[str] = mapped_column(String(40), nullable=False)


class AccountingSetup(Record):
    __tablename__ = "accounting_setup"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_accounting_setup_scope"),
        Index("ix_accounting_setup_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="accounting_setup_version"),
        UniqueConstraint("tenant_id", "company_id", name="uq_accounting_setup_0"),
        MARIADB_TABLE_ARGS,
    )
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    template_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    metadata_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="0"
    )


class AccountGroup(Record):
    __tablename__ = "account_group"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_group_scope"),
        Index("ix_account_group_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_group_version"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_account_group_0"),
        UniqueConstraint("tenant_id", "company_id", "system_key", name="uq_account_group_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "head_id"],
            ["account_head.tenant_id", "account_head.company_id", "account_head.id"],
            name="fk_account_group_head_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "parent_id"],
            ["account_group.tenant_id", "account_group.company_id", "account_group.id"],
            name="fk_account_group_parent_id",
        ),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="account_group_status"),
        Index("ix_account_group_name", "tenant_id", "company_id", "name", "id"),
        Index("ix_account_group_ref0", "tenant_id", "company_id", "head_id"),
        Index("ix_account_group_ref1", "tenant_id", "company_id", "parent_id"),
        CheckConstraint(
            "sort_order >= 0 AND sort_order <= 1000000", name="account_group_sort_order"
        ),
        CheckConstraint(
            "allocation_method IN ('NOT_APPLICABLE', 'BY_QTY', 'BY_VALUE')",
            name="account_group_allocation",
        ),
        Index("ix_account_group_sort", "tenant_id", "company_id", "sort_order", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    head_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    system_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    is_reserved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    is_revenue: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    is_deemed_positive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    affects_gross_profit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    sub_ledger_behaviour: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    nett_balances: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    used_for_calculation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    allocation_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NOT_APPLICABLE", server_default="NOT_APPLICABLE"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class AccountGroupClosure(Record):
    __tablename__ = "account_group_closure"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_group_closure_scope"),
        Index("ix_account_group_closure_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_group_closure_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "ancestor_id",
            "descendant_id",
            name="uq_account_group_closure_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "ancestor_id"],
            ["account_group.tenant_id", "account_group.company_id", "account_group.id"],
            name="fk_account_group_closure_ancestor_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "descendant_id"],
            ["account_group.tenant_id", "account_group.company_id", "account_group.id"],
            name="fk_account_group_closure_descendant_id",
        ),
        Index("ix_account_group_closure_ref1", "tenant_id", "company_id", "descendant_id"),
        MARIADB_TABLE_ARGS,
    )
    ancestor_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    descendant_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Party(Record):
    __tablename__ = "party"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_scope"),
        Index("ix_party_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_version"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_party_0"),
        CheckConstraint("party_type IN ('ORGANISATION', 'PERSON')", name="party_party_type"),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="party_status"),
        Index("ix_party_name", "tenant_id", "company_id", "name", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    party_type: Mapped[str] = mapped_column(String(40), nullable=False, default="ORGANISATION")
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class PartyRole(Record):
    __tablename__ = "party_role"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_role_scope"),
        Index("ix_party_role_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_role_version"),
        UniqueConstraint("tenant_id", "company_id", "party_id", "role", name="uq_party_role_0"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_role_party_id",
        ),
        CheckConstraint(
            "role IN ('CUSTOMER', 'SUPPLIER', 'OTHER', 'BROKER')", name="party_role_role"
        ),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="party_role_status"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class PaymentTerm(Record):
    __tablename__ = "payment_term"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_payment_term_scope"),
        Index("ix_payment_term_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="payment_term_version"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_payment_term_0"),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="payment_term_status"),
        Index("ix_payment_term_name", "tenant_id", "company_id", "name", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class PaymentTermLine(Record):
    __tablename__ = "payment_term_line"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_payment_term_line_scope"),
        Index("ix_payment_term_line_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="payment_term_line_version"),
        UniqueConstraint(
            "tenant_id", "company_id", "payment_term_id", "sequence", name="uq_payment_term_line_0"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "payment_term_id"],
            ["payment_term.tenant_id", "payment_term.company_id", "payment_term.id"],
            name="fk_payment_term_line_payment_term_id",
        ),
        CheckConstraint("basis IN ('INVOICE_DATE', 'MONTH_END')", name="payment_term_line_basis"),
        MARIADB_TABLE_ARGS,
    )
    payment_term_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    basis: Mapped[str] = mapped_column(String(40), nullable=False, default="INVOICE_DATE")
    days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Account(Record):
    __tablename__ = "account"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_scope"),
        Index("ix_account_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_version"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_account_0"),
        UniqueConstraint("tenant_id", "company_id", "system_key", name="uq_account_1"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "group_id"],
            ["account_group.tenant_id", "account_group.company_id", "account_group.id"],
            name="fk_account_group_id",
        ),
        CheckConstraint(
            "kind IN ('GENERAL', 'CASH', 'BANK', 'PARTY', 'TAX', 'INVENTORY_CONTROL', "
            "'ASSET_CONTROL')",
            name="account_kind",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_account_party_id",
        ),
        CheckConstraint(
            "party_role IN ('CUSTOMER', 'SUPPLIER', 'OTHER')", name="account_party_role"
        ),
        CheckConstraint(
            "currency_mode IN ('BASE', 'FIXED', 'MULTI')", name="account_currency_mode"
        ),
        CheckConstraint(
            "posting_policy IN ('MANUAL_ALLOWED', 'SOURCE_ONLY')", name="account_posting_policy"
        ),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="account_status"),
        Index("ix_account_name", "tenant_id", "company_id", "name", "id"),
        Index("ix_account_status", "tenant_id", "company_id", "status", "code", "id"),
        Index("ix_account_kind", "tenant_id", "company_id", "kind", "code", "id"),
        Index("ix_account_currency", "tenant_id", "company_id", "currency", "code", "id"),
        Index("ix_account_currency_mode", "tenant_id", "company_id", "currency_mode", "code", "id"),
        Index("ix_account_ref0", "tenant_id", "company_id", "group_id"),
        Index("ix_account_group_code", "tenant_id", "company_id", "group_id", "code", "id"),
        Index("ix_account_ref1", "tenant_id", "company_id", "party_id"),
        CheckConstraint("sort_order >= 0 AND sort_order <= 1000000", name="account_sort_order"),
        CheckConstraint(
            "rounding_method IN ('NONE', 'NORMAL', 'UP', 'DOWN')", name="account_rounding_method"
        ),
        CheckConstraint(
            "(rounding_method = 'NONE' AND rounding_limit IS NULL) OR "
            "(rounding_method <> 'NONE' AND rounding_limit IS NOT NULL "
            "AND rounding_limit > 0 AND currency_mode <> 'MULTI')",
            name="account_rounding_pair",
        ),
        Index("ix_account_sort", "tenant_id", "company_id", "sort_order", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="GENERAL")
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    party_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    currency_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="BASE")
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    posting_policy: Mapped[str] = mapped_column(
        String(40), nullable=False, default="MANUAL_ALLOWED"
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    system_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    used_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")
    inventory_affected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    rounding_method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NONE", server_default="NONE"
    )
    rounding_limit: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class AccountAlias(Record):
    __tablename__ = "account_alias"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_alias_scope"),
        Index("ix_account_alias_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_alias_version"),
        UniqueConstraint("tenant_id", "company_id", "alias", name="uq_account_alias_0"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_account_alias_account_id",
        ),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="account_alias_status"),
        Index("ix_account_alias_ref0", "tenant_id", "company_id", "account_id"),
        MARIADB_TABLE_ARGS,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    alias: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class AccountGroupAlias(Record):
    __tablename__ = "account_group_alias"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_group_alias_scope"),
        Index("ix_account_group_alias_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_group_alias_version"),
        UniqueConstraint("tenant_id", "company_id", "alias", name="uq_account_group_alias_0"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "group_id"],
            ["account_group.tenant_id", "account_group.company_id", "account_group.id"],
            name="fk_account_group_alias_group_id",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="account_group_alias_status"
        ),
        Index("ix_account_group_alias_ref0", "tenant_id", "company_id", "group_id"),
        MARIADB_TABLE_ARGS,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    alias: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class AccountExternalKey(Record):
    __tablename__ = "account_external_key"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_external_key_scope"),
        Index("ix_account_external_key_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_external_key_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "source_namespace",
            "external_key",
            name="uq_account_external_key_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_account_external_key_account_id",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="account_external_key_status"
        ),
        Index("ix_account_external_key_ref0", "tenant_id", "company_id", "account_id"),
        MARIADB_TABLE_ARGS,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_namespace: Mapped[str] = mapped_column(String(80), nullable=False)
    external_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class PartyAddress(Record):
    __tablename__ = "party_address"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_address_scope"),
        Index("ix_party_address_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_address_version"),
        UniqueConstraint("tenant_id", "company_id", "party_id", "label", name="uq_party_address_0"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_address_party_id",
        ),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="party_address_status"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    mailing_name: Mapped[str] = mapped_column(String(200), nullable=False)
    line1: Mapped[str] = mapped_column(String(200), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    locality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    delivery_instructions: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class PartyTaxRegistration(Record):
    __tablename__ = "party_tax_registration"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_tax_registration_scope"),
        Index("ix_party_tax_registration_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_tax_registration_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "party_id",
            "scheme",
            "registration_number",
            "valid_from",
            name="uq_party_tax_registration_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_tax_registration_party_id",
        ),
        CheckConstraint(
            "scheme IN ('GST_IN', 'VAT', 'OTHER')", name="party_tax_registration_scheme"
        ),
        CheckConstraint(
            "registration_type IN ('REGULAR', 'COMPOSITION', 'UNREGISTERED', 'SEZ_UNIT', "
            "'SEZ_DEVELOPER', 'UIN', 'OVERSEAS', 'CASUAL', 'NRTP', 'OTHER')",
            name="party_tax_registration_registration_type",
        ),
        # UNREGISTERED records a buyer's state without a number; OVERSEAS may hold a
        # foreign identifier or none; every other type is a numbered registration.
        CheckConstraint(
            "(registration_type = 'UNREGISTERED' AND registration_number IS NULL) "
            "OR registration_type = 'OVERSEAS' "
            "OR (registration_type <> 'UNREGISTERED' AND registration_number IS NOT NULL)",
            name="party_tax_registration_number",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="party_tax_registration_dates"
        ),
        Index("ix_party_tax_registration_asof", "tenant_id", "company_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    scheme: Mapped[str] = mapped_column(String(40), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    registration_type: Mapped[str] = mapped_column(String(40), nullable=False, default="REGULAR")
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    state_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    valid_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class PartyDrugLicence(Record):
    """Reviewed India counterparty licence for one exact trading premises."""

    __tablename__ = "party_drug_licence"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_drug_licence_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "address_id",
            "licence_number",
            "valid_from",
            name="uq_party_drug_licence_start",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_drug_licence_party",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "address_id"],
            ["party_address.tenant_id", "party_address.company_id", "party_address.id"],
            name="fk_party_drug_licence_address",
        ),
        Index(
            "ix_party_drug_licence_asof",
            "tenant_id",
            "company_id",
            "party_id",
            "address_id",
            "valid_from",
            "id",
        ),
        CheckConstraint("row_version >= 1", name=conv("ck_party_drug_licence_version")),
        CheckConstraint(
            "licence_form IN ('20','20B','21','21B')", name=conv("ck_party_drug_licence_form")
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name=conv("ck_party_drug_licence_dates")
        ),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    address_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    licence_form: Mapped[str] = mapped_column(String(4), nullable=False)
    licence_number: Mapped[str] = mapped_column(String(80), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    reviewed_by: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    closure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PartyAddressUse(Record):
    __tablename__ = "party_address_use"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_address_use_scope"),
        Index("ix_party_address_use_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_address_use_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "address_id",
            "purpose",
            "registration_id",
            name="uq_party_address_use_registration",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_address_use_party_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "address_id"],
            ["party_address.tenant_id", "party_address.company_id", "party_address.id"],
            name="fk_party_address_use_address_id",
        ),
        CheckConstraint(
            "purpose IN ('REGISTERED', 'BILLING', 'SHIPPING', 'CORRESPONDENCE', 'DISPATCH', "
            "'REMITTANCE')",
            name="party_address_use_purpose",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "registration_id"],
            [
                "party_tax_registration.tenant_id",
                "party_tax_registration.company_id",
                "party_tax_registration.id",
            ],
            name="fk_party_address_use_registration_id",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="party_address_use_status"
        ),
        Index("ix_party_address_use_ref1", "tenant_id", "company_id", "party_id"),
        Index("ix_party_address_use_ref2", "tenant_id", "company_id", "registration_id"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    address_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class PartyContact(Record):
    __tablename__ = "party_contact"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_contact_scope"),
        Index("ix_party_contact_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_contact_version"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_contact_party_id",
        ),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="party_contact_status"),
        Index("ix_party_contact_name", "tenant_id", "company_id", "name", "id"),
        Index("ix_party_contact_ref0", "tenant_id", "company_id", "party_id"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class PartyContactUse(Record):
    __tablename__ = "party_contact_use"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_contact_use_scope"),
        Index("ix_party_contact_use_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_contact_use_version"),
        UniqueConstraint(
            "tenant_id", "company_id", "contact_id", "purpose", name="uq_party_contact_use_0"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_contact_use_party_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "contact_id"],
            ["party_contact.tenant_id", "party_contact.company_id", "party_contact.id"],
            name="fk_party_contact_use_contact_id",
        ),
        CheckConstraint(
            "purpose IN ('GENERAL', 'INVOICING', 'PAYMENTS', 'DELIVERY')",
            name="party_contact_use_purpose",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="party_contact_use_status"
        ),
        Index("ix_party_contact_use_ref1", "tenant_id", "company_id", "party_id"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class PartyIdentifier(Record):
    __tablename__ = "party_identifier"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_identifier_scope"),
        Index("ix_party_identifier_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_identifier_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "party_id",
            "scheme",
            "valid_from",
            name="uq_party_identifier_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_identifier_party_id",
        ),
        CheckConstraint(
            "scheme IN ('PAN', 'TAN', 'CIN', 'EIN', 'UDYAM', 'BUSINESS_REGISTRATION')",
            name="party_identifier_scheme",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="party_identifier_dates"
        ),
        Index("ix_party_identifier_asof", "tenant_id", "company_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    scheme: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[str] = mapped_column(String(80), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    verification_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class PartyRegistrationAddress(Record):
    __tablename__ = "party_registration_address"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_party_registration_address_scope"
        ),
        Index("ix_party_registration_address_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_registration_address_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "registration_id",
            "address_id",
            "valid_from",
            name="uq_party_registration_address_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_registration_address_party_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "registration_id"],
            [
                "party_tax_registration.tenant_id",
                "party_tax_registration.company_id",
                "party_tax_registration.id",
            ],
            name="fk_party_registration_address_registration_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "address_id"],
            ["party_address.tenant_id", "party_address.company_id", "party_address.id"],
            name="fk_party_registration_address_address_id",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="party_registration_address_dates"
        ),
        Index("ix_party_registration_address_ref0", "tenant_id", "company_id", "address_id"),
        Index("ix_party_registration_address_ref1", "tenant_id", "company_id", "party_id"),
        Index("ix_party_registration_address_asof", "tenant_id", "company_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    registration_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    address_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class PartyBankAccount(Record):
    __tablename__ = "party_bank_account"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_bank_account_scope"),
        Index("ix_party_bank_account_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_bank_account_version"),
        UniqueConstraint(
            "tenant_id", "company_id", "party_id", "label", name="uq_party_bank_account_0"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_bank_account_party_id",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="party_bank_account_status"
        ),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    beneficiary_name: Mapped[str] = mapped_column(String(200), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(160), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    routing_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    account_number_ciphertext: Mapped[bytes] = mapped_column(LargeBinary(1024), nullable=False)
    account_number_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    verification_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class PartyCommercialType(Record):
    __tablename__ = "party_commercial_type"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_commercial_type_scope"),
        Index("ix_party_commercial_type_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_commercial_type_version"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_party_commercial_type_0"),
        CheckConstraint("role IN ('CUSTOMER', 'SUPPLIER')", name="party_commercial_type_role"),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="party_commercial_type_status"
        ),
        Index("ix_party_commercial_type_name", "tenant_id", "company_id", "name", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class PartyCommercialTypeMembership(Record):
    __tablename__ = "party_commercial_type_membership"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_party_commercial_type_membership_scope"
        ),
        Index("ix_party_commercial_type_membership_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_commercial_type_membership_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "party_id",
            "commercial_type_id",
            "valid_from",
            name="uq_party_commercial_type_membership_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_commercial_type_membership_party_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "commercial_type_id"],
            [
                "party_commercial_type.tenant_id",
                "party_commercial_type.company_id",
                "party_commercial_type.id",
            ],
            name="fk_party_commercial_type_membership_commercial_type_id",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="party_commercial_type_membership_dates",
        ),
        Index(
            "ix_party_commercial_type_membership_ref0",
            "tenant_id",
            "company_id",
            "commercial_type_id",
        ),
        Index(
            "ix_party_commercial_type_membership_asof",
            "tenant_id",
            "company_id",
            "valid_from",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    commercial_type_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class PartyAccountingPolicy(Record):
    __tablename__ = "party_accounting_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_accounting_policy_scope"),
        Index("ix_party_accounting_policy_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_accounting_policy_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "party_id",
            "role",
            "valid_from",
            name="uq_party_accounting_policy_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_accounting_policy_party_id",
        ),
        CheckConstraint("role IN ('CUSTOMER', 'SUPPLIER')", name="party_accounting_policy_role"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "payment_term_id"],
            ["payment_term.tenant_id", "payment_term.company_id", "payment_term.id"],
            name="fk_party_accounting_policy_payment_term_id",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="party_accounting_policy_dates"
        ),
        Index("ix_party_accounting_policy_ref1", "tenant_id", "company_id", "payment_term_id"),
        Index("ix_party_accounting_policy_asof", "tenant_id", "company_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    payment_term_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    bill_wise: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    settlement_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    transaction_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payment_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class PartyCreditPolicy(Record):
    __tablename__ = "party_credit_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_party_credit_policy_scope"),
        Index("ix_party_credit_policy_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_credit_policy_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "party_id",
            "role",
            "valid_from",
            name="uq_party_credit_policy_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "party_id"],
            ["party.tenant_id", "party.company_id", "party.id"],
            name="fk_party_credit_policy_party_id",
        ),
        CheckConstraint("role IN ('CUSTOMER', 'SUPPLIER')", name="party_credit_policy_role"),
        CheckConstraint(
            "limit_mode IN ('INHERIT', 'UNLIMITED', 'LIMITED')",
            name="party_credit_policy_limit_mode",
        ),
        CheckConstraint(
            "enforcement IN ('WARN', 'BLOCK', 'OVERRIDE')", name="party_credit_policy_enforcement"
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="party_credit_policy_dates"
        ),
        Index("ix_party_credit_policy_asof", "tenant_id", "company_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="CUSTOMER")
    limit_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="LIMITED")
    limit_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    enforcement: Mapped[str] = mapped_column(String(40), nullable=False, default="BLOCK")
    overdue_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overdue_tolerance: Mapped[Decimal] = mapped_column(Money, nullable=False, default="0")
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class AccountTaxProfile(Record):
    __tablename__ = "account_tax_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_tax_profile_scope"),
        Index("ix_account_tax_profile_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_tax_profile_version"),
        UniqueConstraint("tenant_id", "company_id", "account_id", name="uq_account_tax_profile_0"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_account_tax_profile_account_id",
        ),
        CheckConstraint("scheme IN ('GST_IN', 'VAT', 'OTHER')", name="account_tax_profile_scheme"),
        CheckConstraint(
            "component IN ('CGST', 'SGST', 'UTGST', 'IGST', 'CESS', 'VAT', 'OTHER')",
            name="account_tax_profile_component",
        ),
        CheckConstraint(
            "purpose IN ('INPUT_RECOVERABLE', 'INPUT_PENDING', 'OUTPUT_PAYABLE', 'RCM_PAYABLE', "
            "'DEPOSIT', 'ADJUSTMENT')",
            name="account_tax_profile_purpose",
        ),
        CheckConstraint(
            "duty_type IN ('GST', 'VAT', 'TDS', 'TCS', 'CESS', 'EXCISE', 'OTHER')",
            name="account_tax_profile_duty_type",
        ),
        MARIADB_TABLE_ARGS,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    company_registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    scheme: Mapped[str] = mapped_column(String(40), nullable=False)
    component: Mapped[str] = mapped_column(String(40), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    duty_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="OTHER", server_default="OTHER"
    )


class AccountBankProfile(Record):
    __tablename__ = "account_bank_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_bank_profile_scope"),
        Index("ix_account_bank_profile_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_bank_profile_version"),
        UniqueConstraint("tenant_id", "company_id", "account_id", name="uq_account_bank_profile_0"),
        UniqueConstraint(
            "tenant_id", "company_id", "company_bank_id", name="uq_account_bank_profile_1"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_account_bank_profile_account_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    company_bank_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    reconciliation_start_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class AccountTemplateInstallation(Record):
    __tablename__ = "account_template_installation"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_account_template_installation_scope"
        ),
        Index("ix_account_template_installation_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_template_installation_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "template_key",
            "template_version",
            name="uq_account_template_installation_0",
        ),
        MARIADB_TABLE_ARGS,
    )
    template_key: Mapped[str] = mapped_column(String(60), nullable=False)
    template_version: Mapped[str] = mapped_column(String(30), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AccountTemplateBinding(Record):
    __tablename__ = "account_template_binding"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_template_binding_scope"),
        Index("ix_account_template_binding_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_template_binding_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "installation_id",
            "system_key",
            name="uq_account_template_binding_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "installation_id"],
            [
                "account_template_installation.tenant_id",
                "account_template_installation.company_id",
                "account_template_installation.id",
            ],
            name="fk_account_template_binding_installation_id",
        ),
        CheckConstraint(
            "object_type IN ('HEAD', 'GROUP', 'ACCOUNT')",
            name="account_template_binding_object_type",
        ),
        MARIADB_TABLE_ARGS,
    )
    installation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    object_type: Mapped[str] = mapped_column(String(40), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    system_key: Mapped[str] = mapped_column(String(60), nullable=False)


class AccountPostingMapping(Record):
    __tablename__ = "account_posting_mapping"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_posting_mapping_scope"),
        Index("ix_account_posting_mapping_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_posting_mapping_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "purpose",
            "company_registration_id",
            "currency",
            "valid_from",
            name="uq_account_posting_mapping_0",
        ),
        CheckConstraint(
            "purpose IN ('SALES_REVENUE', 'SERVICE_REVENUE', 'SALES_RETURN', "
            "'PURCHASE_EXPENSE', 'OUTPUT_CGST', 'OUTPUT_SGST', 'OUTPUT_UTGST', "
            "'OUTPUT_IGST', 'OUTPUT_CESS', 'INPUT_CGST', 'INPUT_SGST', 'INPUT_UTGST', "
            "'INPUT_IGST', 'INPUT_CESS', 'PENDING_CGST', 'PENDING_SGST', 'PENDING_UTGST', "
            "'PENDING_IGST', 'PENDING_CESS', 'RCM_CGST', 'RCM_SGST', 'RCM_UTGST', 'RCM_IGST', "
            "'RCM_CESS', 'TDS_PAYABLE', 'TCS_PAYABLE', 'TDS_RECEIVABLE', 'TCS_RECEIVABLE', "
            "'CASH_RECEIPT', 'BANK_RECEIPT', 'INVENTORY_VALUE', 'COST_OF_GOODS', "
            "'ROUNDING_GAIN', 'ROUNDING_LOSS')",
            name="account_posting_mapping_purpose",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_account_posting_mapping_account_id",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="account_posting_mapping_dates"
        ),
        Index("ix_account_posting_mapping_ref0", "tenant_id", "company_id", "account_id"),
        Index("ix_account_posting_mapping_asof", "tenant_id", "company_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    company_registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class AccountTaxDefault(Record):
    """GST details on an income, expense or asset ledger (TallyPrime *Specify Details Here*).

    Dated: one default per account and direction on any date. ``rule_id`` names a Catalog
    rule through the local replica; posting-time tax still resolves by ``posting_date``.
    """

    __tablename__ = "account_tax_default"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_account_tax_default_scope"),
        Index("ix_account_tax_default_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="account_tax_default_version"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "account_id",
            "direction",
            "valid_from",
            name="uq_account_tax_default_0",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "account_id"],
            ["account.tenant_id", "account.company_id", "account.id"],
            name="fk_account_tax_default_account_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "rule_id"],
            ["tax_rule_replica.tenant_id", "tax_rule_replica.company_id", "tax_rule_replica.id"],
            name="fk_account_tax_default_rule_id",
        ),
        CheckConstraint(
            "direction IN ('SALE', 'PURCHASE') AND treatment IN ('TAXABLE', 'NIL_RATED', "
            "'EXEMPT', 'NON_GST') AND assessable_inclusion IN ('NONE', 'GOODS', 'SERVICES', "
            "'BOTH') AND (itc_eligibility IS NULL OR itc_eligibility IN ('ELIGIBLE', "
            "'INELIGIBLE', 'BLOCKED'))",
            name="account_tax_default_values",
        ),
        CheckConstraint(
            "(code_system = 'HSN' AND supply_kind = 'GOODS') OR "
            "(code_system = 'SAC' AND supply_kind = 'SERVICE')",
            name="account_tax_default_kind",
        ),
        CheckConstraint(
            "(assessable_inclusion = 'NONE' AND apportion_by IS NULL) OR "
            "(assessable_inclusion <> 'NONE' AND apportion_by IN ('VALUE', 'QUANTITY'))",
            name="account_tax_default_apportion",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="account_tax_default_dates"
        ),
        Index("ix_account_tax_default_ref0", "tenant_id", "company_id", "rule_id"),
        Index("ix_account_tax_default_asof", "tenant_id", "company_id", "valid_from", "id"),
        Index("ix_account_tax_default_code", "tenant_id", "company_id", "code", "id"),
        MARIADB_TABLE_ARGS,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    supply_kind: Mapped[str] = mapped_column(String(7), nullable=False)
    code_system: Mapped[str] = mapped_column(String(3), nullable=False)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    treatment: Mapped[str] = mapped_column(String(10), nullable=False)
    itc_eligibility: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rcm_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assessable_inclusion: Mapped[str] = mapped_column(String(8), nullable=False)
    apportion_by: Mapped[str | None] = mapped_column(String(8), nullable=True)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


def _fk(field: str, table: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "company_id", field],
        [f"{table}.tenant_id", f"{table}.company_id", f"{table}.id"],
        name=name,
    )


EVIDENCE_HASH = "LENGTH(source_sha256) = 64"
DEDUCTEE_CHECK = (
    "deductee_type IN ('INDIVIDUAL', 'HUF', 'COMPANY', 'FIRM', 'AOP_BOI', 'LOCAL_AUTHORITY', "
    "'ARTIFICIAL_JURIDICAL_PERSON', 'GOVERNMENT', 'COOPERATIVE', 'TRUST', "
    "'NON_RESIDENT_COMPANY', 'NON_RESIDENT_OTHER', 'OTHER')"
)


class WithholdingSection(Record):
    """TDS nature of payment or TCS nature of goods, entered by the company."""

    __tablename__ = "withholding_section"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_withholding_section_scope"),
        Index("ix_withholding_section_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="withholding_section_version"),
        UniqueConstraint(
            "tenant_id", "company_id", "kind", "code", name="uq_withholding_section_0"
        ),
        CheckConstraint("kind IN ('TDS', 'TCS')", name="withholding_section_kind"),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'INACTIVE')", name="withholding_section_status"
        ),
        Index("ix_withholding_section_name", "tenant_id", "company_id", "name", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")


class WithholdingRate(Record):
    """Dated, evidenced rate and threshold terms; superseded, never edited once effective."""

    __tablename__ = "withholding_rate"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_withholding_rate_scope"),
        Index("ix_withholding_rate_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="withholding_rate_version"),
        _fk("section_id", "withholding_section", "fk_withholding_rate_section_id"),
        _fk("supersedes_id", "withholding_rate", "fk_withholding_rate_supersedes_id"),
        CheckConstraint(DEDUCTEE_CHECK, name="withholding_rate_deductee_type"),
        CheckConstraint(
            "rate_percent >= 0 AND rate_percent <= 100 AND no_pan_rate_percent >= rate_percent "
            "AND no_pan_rate_percent <= 100",
            name="withholding_rate_percent",
        ),
        CheckConstraint(
            "(single_transaction_threshold IS NULL OR single_transaction_threshold > 0) AND "
            "(aggregate_annual_threshold IS NULL OR aggregate_annual_threshold > 0)",
            name="withholding_rate_threshold",
        ),
        CheckConstraint(
            "threshold_basis IN ('TRANSACTION', 'AGGREGATE', 'EXCESS')",
            name="withholding_rate_basis",
        ),
        CheckConstraint(EVIDENCE_HASH, name="withholding_rate_evidence"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="withholding_rate_dates"
        ),
        Index(
            "ix_withholding_rate_term",
            "tenant_id",
            "company_id",
            "section_id",
            "deductee_type",
            "valid_from",
        ),
        Index("ix_withholding_rate_ref0", "tenant_id", "company_id", "supersedes_id"),
        Index("ix_withholding_rate_asof", "tenant_id", "company_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    section_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    deductee_type: Mapped[str] = mapped_column(String(40), nullable=False)
    rate_percent: Mapped[Decimal] = mapped_column(Money, nullable=False)
    no_pan_rate_percent: Mapped[Decimal] = mapped_column(Money, nullable=False)
    single_transaction_threshold: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    aggregate_annual_threshold: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    threshold_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    threshold_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class PartyWithholdingProfile(Record):
    """Whether and how a party is withheld on; the PAN is referenced, never copied."""

    __tablename__ = "party_withholding_profile"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_party_withholding_profile_scope"
        ),
        Index("ix_party_withholding_profile_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="party_withholding_profile_version"),
        _fk("party_id", "party", "fk_party_withholding_profile_party_id"),
        _fk(
            "pan_identifier_id",
            "party_identifier",
            "fk_party_withholding_profile_pan_identifier_id",
        ),
        _fk(
            "default_section_id",
            "withholding_section",
            "fk_party_withholding_profile_default_section_id",
        ),
        CheckConstraint("kind IN ('TDS', 'TCS')", name="party_withholding_profile_kind"),
        CheckConstraint(DEDUCTEE_CHECK, name="party_withholding_profile_deductee_type"),
        CheckConstraint(
            "pan_status IN ('VERIFIED', 'NOT_AVAILABLE', 'INOPERATIVE')",
            name="party_withholding_profile_pan_status",
        ),
        CheckConstraint(
            "(pan_status <> 'VERIFIED' OR pan_identifier_id IS NOT NULL) AND "
            "(pan_status <> 'NOT_AVAILABLE' OR pan_identifier_id IS NULL)",
            name="party_withholding_profile_pan",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="party_withholding_profile_dates"
        ),
        Index(
            "ix_party_withholding_profile_term",
            "tenant_id",
            "company_id",
            "party_id",
            "kind",
            "valid_from",
        ),
        Index("ix_party_withholding_profile_ref1", "tenant_id", "company_id", "pan_identifier_id"),
        Index("ix_party_withholding_profile_ref2", "tenant_id", "company_id", "default_section_id"),
        Index("ix_party_withholding_profile_asof", "tenant_id", "company_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    deductible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deductee_type: Mapped[str] = mapped_column(String(40), nullable=False)
    pan_status: Mapped[str] = mapped_column(String(20), nullable=False)
    pan_identifier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    default_section_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class WithholdingCertificate(Record):
    """Lower or nil deduction/collection certificate held by a party for one section."""

    __tablename__ = "withholding_certificate"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_withholding_certificate_scope"),
        Index("ix_withholding_certificate_page", "tenant_id", "company_id", "id"),
        CheckConstraint("row_version > 0", name="withholding_certificate_version"),
        _fk("party_id", "party", "fk_withholding_certificate_party_id"),
        _fk("section_id", "withholding_section", "fk_withholding_certificate_section_id"),
        CheckConstraint(
            "rate_percent >= 0 AND rate_percent <= 100", name="withholding_certificate_percent"
        ),
        CheckConstraint(
            "(amount_limit IS NULL AND currency IS NULL) OR "
            "(amount_limit IS NOT NULL AND amount_limit > 0 AND currency IS NOT NULL)",
            name="withholding_certificate_limit",
        ),
        CheckConstraint(EVIDENCE_HASH, name="withholding_certificate_evidence"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="withholding_certificate_dates"
        ),
        Index(
            "ix_withholding_certificate_term",
            "tenant_id",
            "company_id",
            "party_id",
            "section_id",
            "valid_from",
        ),
        Index("ix_withholding_certificate_ref1", "tenant_id", "company_id", "section_id"),
        Index("ix_withholding_certificate_asof", "tenant_id", "company_id", "valid_from", "id"),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    section_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    certificate_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    rate_percent: Mapped[Decimal] = mapped_column(Money, nullable=False)
    amount_limit: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


BUSINESS_MODELS = (
    AccountHead,
    AccountingSetup,
    AccountGroup,
    AccountGroupClosure,
    Party,
    PartyRole,
    PaymentTerm,
    PaymentTermLine,
    Account,
    AccountAlias,
    AccountGroupAlias,
    AccountExternalKey,
    PartyAddress,
    PartyTaxRegistration,
    PartyDrugLicence,
    PartyAddressUse,
    PartyContact,
    PartyContactUse,
    PartyIdentifier,
    PartyRegistrationAddress,
    PartyBankAccount,
    PartyCommercialType,
    PartyCommercialTypeMembership,
    PartyAccountingPolicy,
    PartyCreditPolicy,
    AccountTaxProfile,
    AccountBankProfile,
    AccountTemplateInstallation,
    AccountTemplateBinding,
    AccountPostingMapping,
    AccountTaxDefault,
    WithholdingSection,
    WithholdingRate,
    PartyWithholdingProfile,
    WithholdingCertificate,
)
