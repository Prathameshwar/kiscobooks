"""``company_licence`` — trading licences that gate posting and print on documents.

docs/identity-schema.md §3.8, docs/company.md §4.4. A licence is **behaviour, not a
text field**, and drug licences are the clearest case: the number is legally
required on the invoice, and posting a document containing a scheduled-drug line
with no licence valid on that ``posting_date`` is *rejected* — not warned.

Lifecycle is ``valid_from``/``valid_to`` (``EffectiveMixin``), and rule 4.12 makes
that the only defensible choice: the licence printed on a document is the one valid
on its ``posting_date``, so a reprint of an old invoice must show the licence that
was in force then, not the current one. Never deleted, for the same reason.

``ix_company_licence_valid_to`` exists for the expiry sweep — the Beat job that
raises ``notification`` events ``renewal_reminder_days`` ahead. An expiry discovered
at the till, mid-invoice, is a shop that has stopped trading.
"""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, EffectiveMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import Boolean, Date, ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CompanyLicence(IdMixin, TenantMixin, EffectiveMixin, AuditMixin, Base):
    """docs/identity-schema.md §3.8."""

    __tablename__ = "company_licence"
    __table_args__ = (
        # A renewal is a new row with a new `valid_from`, so the number repeats
        # across renewals and the start date is what distinguishes them.
        UniqueConstraint(
            "company_id",
            "kind",
            "number",
            "valid_from",
            name="uq_company_licence_company_id_kind_number_valid_from",
        ),
        # The resolution query, and it leads with `company_id` under §1.7's two
        # exceptions: it supports `fk_company_licence_company_id`, and `company_id`
        # functionally determines `tenant_id`.
        Index(
            "ix_company_licence_company_id_kind_valid_from_valid_to",
            "company_id",
            "kind",
            "valid_from",
            "valid_to",
        ),
        # The expiry sweep, which is the one query here that is *not* per company:
        # the Beat job asks "what expires soon" across every tenant, so this index
        # deliberately leads with neither `tenant_id` nor `company_id`. It runs
        # under `unfiltered()` by construction and is the only reader.
        Index("ix_company_licence_valid_to", "valid_to"),
        # Declared so InnoDB does not invent one named after the constraint.
        Index("ix_company_licence_premises_address_id", "premises_address_id"),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey("company.id", name="fk_company_licence_company_id"),
        nullable=False,
    )
    #: From the jurisdiction profile, which also carries what the licence ``gates``.
    #: No foreign key, for the reason ``company_statutory_id.kind`` has none.
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    #: Prints on documents that legally require it, resolved by ``posting_date``.
    number: Mapped[str] = mapped_column(String(60), nullable=False)
    issuing_authority: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Licences are usually per premises, which is why several of one kind may be
    #: valid at once and why ``resolve_licence`` picks the primary rather than
    #: treating two matches as ambiguous.
    premises_address_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        ForeignKey("company_address.id", name="fk_company_licence_premises_address_id"),
        nullable=True,
    )
    issued_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    #: Lead time for the renewal reminder. ``SMALLINT`` because it is a number of
    #: days, and a licence nobody renews within a year of expiry is not a reminder
    #: problem.
    renewal_reminder_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    #: The scanned certificate. A signed, expiring URL — never a public object
    #: (CLAUDE.md §5.14).
    document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: The default for the kind. Enforced in ``domain/``, not by a key: MariaDB has
    #: no partial unique index (docs/identity-db-plan.md §2).
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
