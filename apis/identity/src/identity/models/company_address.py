"""``company_address`` — several real addresses per company.

Rows rather than columns on ``company`` because a company genuinely has a
registered office, a billing address, and branch and warehouse addresses at
different places, and a shipping address drives place of supply on its own.

**``company.state_code`` is not derived from the primary registered address**, and
that is deliberate (docs/org-model.md §6.2). If it were, flipping ``is_primary``
here would retroactively change whether every issued invoice was intra-state or
inter-state. The company's home state is set once and frozen after first posting;
these rows describe where post goes.

Lifecycle is ``is_active`` (``DeactivableMixin``), not ``status`` and not dates:
an address does not affect a computed amount, so rule 4.12's boolean form is the
right one. Deactivating it means "not selectable for new documents" — it never
hides the address from a document already issued to it.
"""

from __future__ import annotations

import uuid
from typing import Final

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import (
    CHAR,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

#: docs/identity-schema.md §3.5. ``shipping`` is the one that matters to tax: it is
#: the place of supply for a goods invoice.
ADDRESS_TYPES: Final[frozenset[str]] = frozenset({"registered", "billing", "shipping", "branch"})


class CompanyAddress(IdMixin, TenantMixin, DeactivableMixin, AuditMixin, Base):
    """docs/identity-schema.md §3.5."""

    __tablename__ = "company_address"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_company_address_owner_id"),
        # docs/identity-schema.md §3.5's documented key, and it leads with
        # `company_id` rather than `tenant_id` for two reasons that agree:
        # `company_id` functionally determines `tenant_id`, so §1.7's concern — a
        # composite index the tenant-filtered query cannot use — does not arise; and
        # an index supporting `fk_company_address_company_id` must begin with that
        # column, or InnoDB silently creates a second, invisible one.
        Index("ix_company_address_company_id_type", "company_id", "type"),
        # The same composite jurisdiction key `company` carries: `IN` with `US-CA`
        # is refused by the database, not by a form. It matters more here than it
        # looks, because a shipping address's state decides the tax on the invoice.
        ForeignKeyConstraint(
            ["country_code", "state_code"],
            ["state.country_code", "state.code"],
            name="fk_company_address_country_code_state_code",
        ),
        # Declared so InnoDB does not invent it. It also supports
        # `fk_company_address_country_code`, whose column is its leftmost prefix.
        Index("ix_company_address_country_code_state_code", "country_code", "state_code"),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey("company.id", name="fk_company_address_company_id"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    #: User-facing name — "Andheri Warehouse". Distinct from ``type``, which the
    #: domain reads.
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Part of the composite FK above. Drives place of supply on shipping addresses.
    state_code: Mapped[str] = mapped_column(String(6), nullable=False)
    #: Validated against the jurisdiction profile's pattern, not a global one — a
    #: six-digit PIN and a UK postcode share no shape.
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country_code: Mapped[str] = mapped_column(
        CHAR(2),
        ForeignKey("country.code", name="fk_company_address_country_code"),
        nullable=False,
    )
    #: One per ``type``, enforced in ``domain/``. Not a unique constraint: "at most
    #: one true per (company, type)" needs a partial unique index, which MariaDB
    #: does not have (docs/identity-db-plan.md §2).
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
