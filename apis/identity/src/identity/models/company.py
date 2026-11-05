"""``company`` — the legal entity that issues documents.

Not the same thing as a tenant (docs/org-model.md §2.1): a tenant is who pays us,
a company is who signs the invoice. One tenant routinely holds several, and they
may sit in different states under different registrations.

Three things about this table are load-bearing beyond its size.

**``first_posted_at`` is the enforcement mechanism for immutability.** Ten columns
here are frozen once anything has posted (docs/company.md §5.2) — currency, fiscal
start, precision, rounding, code, country, state. The freeze is enforced in
``domain/``, for **every** actor including platform admin, and is not a permission:
no role can lift it. See ``identity.domain.company_immutability``.

**The composite foreign key is what makes an impossible jurisdiction
unrepresentable.** ``(country_code, state_code)`` points at
``state (country_code, code)``, so ``IN`` with ``US-CA`` is refused by the database
rather than by a form. ``state_code`` drives place of supply on every line, and a
wrong pair silently flips every invoice between intra-state and inter-state GST.

**Display precision is not storage precision.** ``amount_precision`` and
``quantity_precision`` are 0 to 4 *display and rounding* scales; storage is fixed at
``DECIMAL(19,4)`` everywhere (docs/company.md §4.5). Reading them as storage scales
is how a subledger stops tying.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Final

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, StatusMixin, TenantMixin
from billing_platform.db.types import Money, UtcDateTime, Uuid7
from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from identity.models.business_classification import CompanyBusinessRole

#: Rule 4.12's ``status`` form. No ``is_active`` here: ``suspended`` blocks new
#: documents while leaving history fully readable, and ``closed`` is terminal for
#: new activity only — history stays queryable and printable forever
#: (docs/company.md §5.4). A company is never hard-deleted (invariant 12).
COMPANY_STATUSES: Final[frozenset[str]] = frozenset({"active", "suspended", "closed"})

#: docs/identity-schema.md §3.3. Validated in ``domain/``, never a MySQL ``ENUM``.
ENTITY_TYPES: Final[frozenset[str]] = frozenset(
    {"pvt_ltd", "llp", "partnership", "sole_prop", "public", "trust", "branch"}
)

BUSINESS_NATURES: Final[frozenset[str]] = frozenset(
    {"trading", "manufacturing", "service", "distribution", "retail"}
)

#: ``Decimal`` contexts, not float modes. ``half_even`` is banker's rounding.
ROUNDING_MODES: Final[frozenset[str]] = frozenset({"half_up", "half_even", "down"})

TAX_TREATMENTS: Final[frozenset[str]] = frozenset({"inclusive", "exclusive"})

#: A **display preference, not access control** (docs/company.md §6.2). ``unlisted``
#: keeps a company out of switchers and pickers; it never removes an audit row and
#: never hides data from an authorized reader (invariant 17).
VISIBILITIES: Final[frozenset[str]] = frozenset({"listed", "unlisted"})

#: ``indian`` is 12,34,567; ``western`` is 1,234,567. Not derivable from the locale
#: alone, and getting it wrong is immediately visible on a printed invoice.
DIGIT_GROUPINGS: Final[frozenset[str]] = frozenset({"indian", "western"})

NEGATIVE_FORMATS: Final[frozenset[str]] = frozenset({"minus", "parentheses"})

CURRENCY_SYMBOL_POSITIONS: Final[frozenset[str]] = frozenset({"prefix", "suffix"})

#: Inclusive bounds for ``amount_precision`` and ``quantity_precision``. The upper
#: bound is the storage scale: displaying more decimals than are stored would show
#: digits that do not exist.
PRECISION_MIN: Final[int] = 0
PRECISION_MAX: Final[int] = 4


class Company(IdMixin, TenantMixin, StatusMixin, AuditMixin, Base):
    """docs/identity-schema.md §3.3."""

    __tablename__ = "company"
    __table_args__ = (
        # `code` is embedded in document numbers, so a duplicate inside a tenant
        # would produce two documents with the same number.
        UniqueConstraint("tenant_id", "code", name="uq_company_tenant_id_code"),
        UniqueConstraint("tenant_id", "id", name="uq_company_tenant_id_id"),
        Index("ix_company_business_category_code", "business_category_code"),
        Index("ix_company_store_format_code", "store_format_code"),
        # `tenant_id` leads, per docs/identity-db-plan.md §1.7: the session filter
        # injects it into every query, and an index without it is unusable.
        Index("ix_company_tenant_id_status", "tenant_id", "status"),
        # The composite jurisdiction key. Declared before the single-column FKs
        # because its supporting index also supports `fk_company_country_code` —
        # InnoDB accepts any index whose leftmost prefix matches the FK columns, so
        # no shadow index is created for that one.
        ForeignKeyConstraint(
            ["country_code", "state_code"],
            ["state.country_code", "state.code"],
            name="fk_company_country_code_state_code",
        ),
        # These three exist so InnoDB does not invent them. An implicitly created
        # index is invisible in the model and reads as autogenerate drift forever.
        #
        # They intentionally break §1.7's `tenant_id`-leads rule: an index
        # supporting a foreign key must begin with the FK's own columns, so these
        # are structural rather than query indexes.
        Index("ix_company_country_code_state_code", "country_code", "state_code"),
        Index("ix_company_base_currency", "base_currency"),
        Index("ix_company_reporting_currency", "reporting_currency"),
        Index("ix_company_parent_company_id", "parent_company_id"),
        MARIADB_TABLE_ARGS,
    )

    # --- identity -------------------------------------------------------------

    #: Group hierarchy, self-referencing. The FK proves the parent exists; it
    #: cannot prove the parent is in the *same tenant*, which is checked in
    #: ``domain/`` — a cross-tenant parent would be a §5.2 object-scope breach that
    #: no `WHERE` would catch.
    parent_company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        ForeignKey("company.id", name="fk_company_parent_company_id"),
        nullable=True,
    )
    #: **Immutable after first posting.** Embedded in issued document numbers.
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Registered name, for statutory output. Distinct from ``trade_name``, which is
    #: what customers recognise, and from ``display_name``, which is what fits in a
    #: switcher.
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    incorporation_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    #: **Immutable after first posting.** Selects the jurisdiction profile that
    #: decided which statutory IDs and licences existing rows were validated against.
    country_code: Mapped[str] = mapped_column(
        CHAR(2),
        ForeignKey("country.code", name="fk_company_country_code"),
        nullable=False,
    )
    #: **Immutable after first posting.** Home state; drives place of supply on
    #: every line. Deliberately *not* derived from the primary registered address
    #: (org-model §6.2) — flipping ``is_primary`` there must never retroactively
    #: change the tax treatment of an issued invoice.
    state_code: Mapped[str] = mapped_column(String(6), nullable=False)
    #: Set once, inside the first posting's transaction, and never cleared. Arrives
    #: via the company replica, so it is part of the ``company.updated`` event
    #: rather than a local-only column.
    first_posted_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)

    # --- financial: ledger settings freeze after posting; presentation does not ---

    #: Ledger currency. Changing it reinterprets every amount already stored —
    #: ₹100,000 becomes $100,000 — which is why it is frozen rather than migrated.
    base_currency: Mapped[str] = mapped_column(
        CHAR(3),
        ForeignKey("currency.code", name="fk_company_base_currency"),
        nullable=False,
    )
    #: Presentation translation only. NULL means "same as base".
    reporting_currency: Mapped[str | None] = mapped_column(
        CHAR(3),
        ForeignKey("currency.code", name="fk_company_reporting_currency"),
        nullable=True,
    )
    #: 1 to 12. Source for ``fiscal_year`` generation in ``billing``; changing it moves
    #: every posted document's period assignment.
    fiscal_year_start_month: Mapped[int] = mapped_column(
        SmallInteger().with_variant(mysql.TINYINT(), "mysql"), nullable=False
    )
    #: 1 to 31.
    fiscal_year_start_day: Mapped[int] = mapped_column(
        SmallInteger().with_variant(mysql.TINYINT(), "mysql"), nullable=False
    )
    #: Earliest postable date. May be after the fiscal-year start on a migration
    #: from another system.
    books_begin_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    #: 0 to 4. **Display and rounding scale, not storage scale** (docs/company.md §4.5):
    #: a company at 2 stores ``1234.5000`` and shows ``1,234.50``.
    amount_precision: Mapped[int] = mapped_column(
        SmallInteger().with_variant(mysql.TINYINT(), "mysql"), nullable=False
    )
    quantity_precision: Mapped[int] = mapped_column(
        SmallInteger().with_variant(mysql.TINYINT(), "mysql"), nullable=False
    )
    rounding_mode: Mapped[str] = mapped_column(String(20), nullable=False)

    # --- tax posture: defaults only --------------------------------------------

    #: Form default, from the code catalogue in ``billing_platform.tax``.
    #: **Never read by a posting path** — the authoritative value is the
    #: registration resolved by the document's ``posting_date`` (invariant 17).
    default_tax_system: Mapped[str] = mapped_column(String(20), nullable=False)
    tax_treatment_default: Mapped[str] = mapped_column(String(12), nullable=False)

    # --- commercial defaults ---------------------------------------------------

    default_payment_terms_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: Money in ``base_currency`` — that column is the currency sibling for both
    #: amounts here, so neither carries its own. Safe because both are ceilings on
    #: the company's own ledger, never a foreign-currency figure.
    credit_limit_default: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    #: Statutory cap (₹2,00,000 in India, §269ST). May be **lowered** by the tenant,
    #: never raised above the jurisdiction profile value (docs/company.md §5.5).
    cash_receipt_limit: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    #: Rejects implausible back-dating even inside an open period
    #: (docs/fiscal-year.md §6.3). NULL means no additional limit beyond the period.
    backdated_posting_limit_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # --- business nature -------------------------------------------------------

    #: NIC / NAICS. Free text against an external standard, so no FK.
    industry_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    business_nature: Mapped[str | None] = mapped_column(String(20), nullable=True)

    business_category_code: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("business_category.code", name="fk_company_business_category_code"),
        nullable=True,
    )
    store_format_code: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("store_format.code", name="fk_company_store_format_code"),
        nullable=True,
    )
    business_role_bindings: Mapped[list[CompanyBusinessRole]] = relationship(
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="CompanyBusinessRole.business_role_code",
    )

    @property
    def business_roles(self) -> list[str]:
        return sorted(binding.business_role_code for binding in self.business_role_bindings)

    @business_roles.setter
    def business_roles(self, codes: list[str]) -> None:
        # Retain existing bindings: inserting before deletion would violate uniqueness.
        existing = {binding.business_role_code: binding for binding in self.business_role_bindings}
        self.business_role_bindings = [
            existing[code]
            if code in existing
            else CompanyBusinessRole(
                tenant_id=self.tenant_id,
                company_id=self.id,
                business_role_code=code,
            )
            for code in codes
        ]

    # --- locale and presentation ----------------------------------------------
    #
    # All of it resolved server-side and served as one payload
    # (docs/company.md §4.5). Neither client formats from its own locale defaults:
    # a `toLocaleString()` in web and a different one in mobile produce two
    # renderings of the same invoice, and the PDF worker produces a third.

    #: IANA name. Governs document-date defaulting, so never a UTC offset.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    date_format: Mapped[str] = mapped_column(String(20), nullable=False)
    datetime_format: Mapped[str] = mapped_column(String(30), nullable=False)
    digit_grouping: Mapped[str] = mapped_column(String(10), nullable=False)
    decimal_separator: Mapped[str] = mapped_column(String(2), nullable=False)
    #: May be empty — some conventions group with nothing at all.
    thousands_separator: Mapped[str] = mapped_column(String(2), nullable=False)
    negative_format: Mapped[str] = mapped_column(String(15), nullable=False)
    #: Prints the amount-in-words line. The words themselves come from the shared
    #: ``libs/platform`` formatter, never from a per-client implementation.
    show_amount_in_words: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    currency_symbol_position: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Legacy stationery — "Rs." instead of "₹". NULL uses the currency's own symbol.
    currency_symbol_override: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # --- documents and branding -----------------------------------------------

    #: Object key, served through a signed expiring URL (CLAUDE.md §5.14). Never a
    #: public bucket path.
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signature_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand_color: Mapped[str | None] = mapped_column(CHAR(7), nullable=True)
    #: No foreign key: print templates live outside ``identity``, and a
    #: cross-service FK is exactly what the architecture forbids (CLAUDE.md §4).
    print_template_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    terms_and_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    declaration_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    jurisdiction_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    signatory_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    signatory_designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The certificate **thumbprint only** — a fingerprint, not a credential.
    #: Never a private key and never a PFX blob (CLAUDE.md §5.9).
    dsc_thumbprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- visibility ------------------------------------------------------------

    visibility: Mapped[str] = mapped_column(String(10), nullable=False, default="listed")
    #: Demands fresh authentication before the company opens. A real control, unlike
    #: ``visibility`` — but step-up, not a per-company password (docs/company.md §6.3).
    requires_step_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Audit support. The authoritative record is the audit event; these two exist so
    #: the current state can answer "who last changed this" without a query to
    #: ``audit`` (docs/company.md §6.5).
    visibility_changed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    visibility_changed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)

    # --- extensibility ---------------------------------------------------------

    #: Values keyed by definition ``key``. **No domain logic reads this**
    #: (invariant 14): store, validate, display and report only — never price, tax,
    #: post or route an approval from it. Anything that drives money becomes a real
    #: column with a migration.
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
