"""``company_statutory_id`` — PAN, TAN, CIN, EIN, Udyam, and their equivalents.

docs/identity-schema.md §3.7, docs/company.md §4.3. Rows rather than columns
because the set is jurisdiction-specific: a `pan` column would be NULL for every
company outside India, and a new country would be a migration instead of a profile
entry (``billing_platform.jurisdiction``).

**``value`` is NULL for a restricted kind, and that is the point of the table.**
AADHAAR and SSN-class personal identity numbers are never stored (CLAUDE.md §5.10):
the API accepts a full number, ``prepare_statutory_value`` derives ``value_last4``,
the row records a ``verification_reference``, and the rest is discarded before it
reaches this model. PAN, TAN, CIN and EIN are *business* identifiers, print on
invoices, and are stored in full.

``value_last4`` is **NOT NULL for every kind**, not only restricted ones. It is the
last column of the unique key, and MariaDB treats NULLs inside a unique key as
distinct (docs/identity-db-plan.md §2) — left NULL for unrestricted kinds, the
constraint would let a company store the same PAN twice.

Two lifecycle-shaped columns, and only one of them is a lifecycle. ``is_active``
(``DeactivableMixin``) is rule 4.12's mechanism here: an identifier does not affect
a computed amount, it prints. ``valid_to`` is *data* — the expiry printed on the
certificate — and there is no ``valid_from`` to pair it with, so it cannot be read
as the date-validity form.
"""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import Date, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CompanyStatutoryId(IdMixin, TenantMixin, DeactivableMixin, AuditMixin, Base):
    """docs/identity-schema.md §3.7."""

    __tablename__ = "company_statutory_id"
    __table_args__ = (
        # One identifier of a kind per company, keyed on the last four digits
        # because that is the only part a restricted kind leaves behind. Two
        # different values of one kind sharing their last four digits would be
        # falsely rejected; that is inherent in the documented key, and the
        # alternative — keying on `value`, which is NULL for restricted kinds — would
        # enforce nothing at all for exactly the kinds that matter most.
        UniqueConstraint(
            "company_id",
            "kind",
            "value_last4",
            name="uq_company_statutory_id_company_id_kind_value_last4",
        ),
        # Leads with `company_id` under §1.7's two exceptions: it supports
        # `fk_company_statutory_id_company_id`, and `company_id` functionally
        # determines `tenant_id`.
        Index("ix_company_statutory_id_company_id_kind", "company_id", "kind"),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey("company.id", name="fk_company_statutory_id_company_id"),
        nullable=False,
    )
    #: From the jurisdiction profile. No foreign key: kinds are code, so a `kind`
    #: table would let a tenant invent one no service knows how to validate or print
    #: (the same argument as ``company_feature.feature_key``).
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    #: The full value — **NULL for a restricted kind, permanently**. Nothing writes
    #: this except a value that came back from ``prepare_statutory_value``.
    value: Mapped[str | None] = mapped_column(String(60), nullable=True)
    #: Always populated. See the module docstring for why it is NOT NULL.
    value_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    #: For a proprietor-held identifier, whose holder is a person rather than the
    #: company. A name, never an identity number.
    holder_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    issued_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    #: The expiry printed on the certificate. Data, not this row's lifecycle.
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    verified_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    #: Proof that the holder was verified, without holding the number. For a
    #: restricted kind this and ``value_last4`` are the entire record.
    verification_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
