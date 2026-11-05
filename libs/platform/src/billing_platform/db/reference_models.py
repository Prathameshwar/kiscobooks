"""Tier-1 ISO reference tables: ``currency``, ``country``, ``state``.

Defined in ``libs/platform`` because every service needs them and they must have an
identical shape in each service database (``docs/tech-stack.md``
§ *Reference data ownership*). Their **content** arrives by seed, never by a
migration — see ``billing_platform.reference``.

Three things make these tables different from every other table in the platform,
each deliberate and each tested:

* **Natural-code primary keys**, not UUIDv7 — the one documented exception
  (CLAUDE.md §4). A country is `IN` in every database, in every export and in every
  log line, which is worth more here than a uniform key type.
* **No ``tenant_id``.** They are shared across tenants, so they carry no
  ``TenantMixin`` and are on the ``TENANT_FILTER_EXEMPT`` whitelist.
* **No ``Audit`` mixin.** There is no actor: content changes by seed
  (``docs/identity-schema.md`` §1).

Codes are never renamed, and a row is never deleted — a code withdrawn from ISO is
deactivated, because posted documents reference it (invariant 12).

Field lists are ``docs/identity-schema.md`` §1.1 to §1.3.
"""

from __future__ import annotations

from sqlalchemy import CHAR, Boolean, ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base

# On the `is_active` column all three tables carry: it is deliberately *not*
# `DeactivableMixin`, which also brings `deactivated_at`/`deactivated_by` — there is
# no actor to record on a seeded table. It is still rule 4.12's boolean form, the
# only lifecycle mechanism on these three tables, and it means "not selectable for
# new records", never "hidden from history".


class Currency(Base):
    """ISO 4217, plus the presentation metadata needed to print an amount.

    ``minor_unit`` governs **display and rounding only**. Storage is always
    ``DECIMAL(19,4)``: a JPY amount is stored as ``1234.0000`` and rendered with no
    decimals (``docs/identity-schema.md`` §0.4). Reading it as a storage scale is
    how a subledger stops tying.
    """

    __tablename__ = "currency"
    __table_args__ = (MARIADB_TABLE_ARGS,)

    code: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    numeric_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Multi-byte — `₹` is three bytes in utf8mb4 — hence the width.
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    #: Decimal places for display: JPY 0, INR 2, KWD 3. ``TINYINT`` on MariaDB;
    #: ``SMALLINT`` elsewhere, because SQLite has no ``TINYINT``.
    minor_unit: Mapped[int] = mapped_column(
        SmallInteger().with_variant(mysql.TINYINT(), "mysql"), nullable=False
    )
    #: For amount-in-words on a printed invoice: "Rupees", "Paisa", "Paise".
    major_unit_name: Mapped[str] = mapped_column(String(40), nullable=False)
    minor_unit_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    minor_unit_name_plural: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Country(Base):
    """ISO 3166-1.

    Selects the jurisdiction profile that drives which statutory IDs and licences a
    company must supply (``docs/company.md``).
    """

    __tablename__ = "country"
    __table_args__ = (
        # Declared explicitly rather than left to InnoDB, which would otherwise
        # create an index named after the FK constraint to support it. An
        # implicitly created index is invisible in the model and shows up as
        # autogenerate drift.
        Index("ix_country_default_currency_code", "default_currency_code"),
        MARIADB_TABLE_ARGS,
    )

    code: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    iso3: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    numeric_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Legal name, for printed documents — "Republic of India".
    official_name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_currency_code: Mapped[str] = mapped_column(
        CHAR(3),
        ForeignKey("currency.code", name="fk_country_default_currency_code"),
        nullable=False,
    )
    phone_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    #: UI label for this country's subdivisions — "State", "Province", "Emirate".
    #: Widened from the doc's original 40 to 60; see the decision log.
    subdivision_label: Mapped[str] = mapped_column(String(60), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class State(Base):
    """ISO 3166-2 subdivisions. Required for tax place-of-supply.

    **The unique key on ``(country_code, code)`` is load-bearing.** It exists solely
    to be the target of the composite foreign key on ``company`` and
    ``company_address``, which is what makes ``country_code='IN'`` with
    ``state_code='US-CA'`` unrepresentable rather than merely unlikely
    (``docs/identity-schema.md`` §1.2). Redundant-looking — ``code`` is already
    unique on its own — and must not be removed for that reason.
    """

    __tablename__ = "state"
    __table_args__ = (
        UniqueConstraint("country_code", "code", name="uq_state_country_code_code"),
        MARIADB_TABLE_ARGS,
    )

    code: Mapped[str] = mapped_column(String(6), primary_key=True)
    country_code: Mapped[str] = mapped_column(
        CHAR(2), ForeignKey("country.code", name="fk_state_country_code"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    #: "State", "Union territory", "Province". Widened from the doc's original 40
    #: to 60: ISO 3166-2 carries "Metropolitan collectivity with special status" at
    #: 45 characters, and MariaDB truncates rather than raising.
    subdivision_type: Mapped[str] = mapped_column(String(60), nullable=False)
    #: GST state code — Maharashtra `27`. Prefixes every GSTIN issued there.
    #: Nullable: only India assigns one.
    tax_jurisdiction_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
