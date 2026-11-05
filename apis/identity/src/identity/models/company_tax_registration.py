"""``company_tax_registration`` — the registrations a company invoices under.

docs/identity-schema.md §3.6, docs/company.md §4.2.

Lifecycle is ``valid_from``/``valid_to`` (``EffectiveMixin``), and rule 4.12 makes
that mandatory rather than a preference: ``regime`` decides whether tax may be
charged at all, so it affects a computed amount and must resolve by the document's
``posting_date`` (CLAUDE.md invariant 4). With ``is_active`` instead, a distributor
who moved from Composition to Regular on 1 October would reprint an August invoice
showing the wrong regime on a document already filed.

**Never deleted, and never deactivated.** An invoice issued under an old GSTIN must
still resolve it years later — which is also why ``DeactivableMixin`` is absent
here where it is present on ``company_statutory_id``.

The resolution itself is not here. It is ``billing_platform.statutory``, because
``billing`` resolves it from its own replica inside the posting transaction and may
not call ``identity`` to do it (CLAUDE.md invariant 7).
"""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, EffectiveMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class CompanyTaxRegistration(IdMixin, TenantMixin, EffectiveMixin, AuditMixin, Base):
    """docs/identity-schema.md §3.6."""

    __tablename__ = "company_tax_registration"
    __table_args__ = (
        Index(
            "ix_company_tax_registration_address_owner",
            "tenant_id",
            "company_id",
            "registered_address_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "registered_address_id"],
            ["company_address.tenant_id", "company_address.company_id", "company_address.id"],
            name="fk_company_tax_registration_address_owner",
        ),
        # One registration per system, class and jurisdiction per start date — the
        # same grouping as the overlap rule, so a regular GSTIN and a TDS-deductor
        # registration may start on the same day (revision 0063). It stops an exact
        # duplicate and nothing more: no database can express "no two rows with
        # intersecting date ranges", so the overlap rule is `domain/`'s
        # (`assert_no_overlap`). Named explicitly — the convention's generated name
        # would be past MariaDB's 64-character identifier limit
        # (docs/identity-db-plan.md §1.3).
        UniqueConstraint(
            "company_id",
            "tax_system",
            "registration_class",
            "jurisdiction_code",
            "valid_from",
            name="uq_company_tax_registration_class_jurisdiction_valid_from",
        ),
        # The resolution query: given a company, a jurisdiction and a posting date,
        # which registration was in force. Leads with `company_id` under §1.7's two
        # exceptions — it supports `fk_company_tax_registration_company_id`, and
        # `company_id` functionally determines `tenant_id`.
        Index(
            "ix_company_tax_registration_jurisdiction_validity",
            "company_id",
            "jurisdiction_code",
            "valid_from",
            "valid_to",
        ),
        # Declared so InnoDB does not invent one named after the constraint.
        Index("ix_company_tax_registration_registered_address_id", "registered_address_id"),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey("company.id", name="fk_company_tax_registration_company_id"),
        nullable=False,
    )
    #: ``billing_platform.tax``. Immutable after create, enforced in ``domain/``:
    #: changing it would reinterpret every document already issued under this row.
    tax_system: Mapped[str] = mapped_column(String(20), nullable=False)
    #: ``billing_platform.tax.REGIMES``, per system. The one field here that decides
    #: whether tax may be charged, which is why this whole table is date-effective.
    regime: Mapped[str] = mapped_column(String(30), nullable=False)
    #: ``billing_platform.tax.REGISTRATION_CLASSES`` — derived from ``regime`` by the
    #: catalogue and set in ``domain/`` on create; immutable because ``regime`` is.
    #: Stored so the unique key can group by it, as the overlap rule does.
    registration_class: Mapped[str] = mapped_column(String(20), nullable=False)
    #: GSTIN, VAT number, and so on. Validated against the jurisdiction profile.
    number: Mapped[str] = mapped_column(String(40), nullable=False)
    #: The state or country this registration covers. Which of the two is decided by
    #: the profile's ``tax_registration_is_per``, checked in ``domain/`` — there is
    #: no foreign key, because the column holds a state code in India and a country
    #: code in the UK, and no single target covers both.
    jurisdiction_code: Mapped[str] = mapped_column(String(6), nullable=False)
    #: May differ from ``company.legal_name``; prints as registered.
    legal_name_on_registration: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registered_address_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        ForeignKey("company_address.id", name="fk_company_tax_registration_registered_address_id"),
        nullable=True,
    )
    #: The default for the jurisdiction. Enforced in ``domain/``, not by a key: "at
    #: most one true per scope" needs a partial unique index, which MariaDB does not
    #: have (docs/identity-db-plan.md §2).
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    #: The portal or gateway reference that proves verification happened.
    verification_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
