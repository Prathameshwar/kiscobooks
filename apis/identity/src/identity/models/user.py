"""``user`` — a principal within one tenant.

docs/identity-schema.md §4.1. Credentials live in Authentik; what lives here is
profile, org placement and presentation preferences. **Never a password hash, an
MFA secret, a session or a recovery code** — duplicating any of those would make
this table a second authentication authority that can disagree with the first.

Three things are load-bearing.

**Email is unique per tenant, not globally.** The same address may exist in two
tenants as two different people-in-context, and that single constraint is what
stands between this model and a global ``principal`` (docs/org-model.md §4.3).

**``user_type`` is never used for authorization** (docs/roles-permissions.md §1.3).
It decides which application surface a principal sees. What they may do comes from
``role_assignment`` alone, so a route that branches on ``user_type`` has invented a
permission that no audit of the role catalogue would ever show.

**Deactivation anonymizes, never deletes** (CLAUDE.md invariant 12). A user who
posted an invoice is referenced from the ledger forever, so the row survives with
name, email and phone replaced by a tombstone and ``anonymized_at`` stamped.
``id`` and ``employee_code`` are preserved: they are what makes the surviving audit
trail resolvable.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Final

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, StatusMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

#: docs/identity-schema.md §4.1. Which surface a principal sees — **not** what they
#: may do. ``platform_admin`` here still needs the ``platform_admin`` *role*, and
#: holding the role without the type gets no platform surface either (§1.3).
USER_TYPES: Final[frozenset[str]] = frozenset(
    {"platform_admin", "tenant_user", "customer_portal_user", "service_account"}
)

#: Rule 4.12's ``status`` form, and no ``is_active`` alongside it. ``invited`` is a
#: real state with no ``authentik_sub`` yet; ``deactivated`` is terminal for access
#: and never for history.
USER_STATUSES: Final[frozenset[str]] = frozenset({"invited", "active", "suspended", "deactivated"})


class User(IdMixin, TenantMixin, StatusMixin, AuditMixin, Base):
    """docs/identity-schema.md §4.1."""

    __tablename__ = "user"
    __table_args__ = (
        Index("ix_user_default_company_owner", "tenant_id", "default_company_id"),
        ForeignKeyConstraint(
            ["tenant_id", "default_company_id"],
            ["company.tenant_id", "company.id"],
            name="fk_user_default_company_owner",
        ),
        Index(
            "ix_user_default_department_owner",
            "tenant_id",
            "default_company_id",
            "default_department_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "default_company_id", "default_department_id"],
            ["department.tenant_id", "department.company_id", "department.id"],
            name="fk_user_default_department_owner",
        ),
        Index("ix_user_manager_owner", "tenant_id", "reporting_manager_id"),
        ForeignKeyConstraint(
            ["tenant_id", "reporting_manager_id"],
            ["user.tenant_id", "user.id"],
            name="fk_user_manager_owner",
        ),
        CheckConstraint(
            "default_department_id IS NULL OR default_company_id IS NOT NULL",
            name="default_department_requires_company",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_user_owner_id"),
        # Per tenant, deliberately. Changing this to a global unique is a much
        # larger decision than it looks (docs/identity-schema.md §4.1).
        UniqueConstraint("tenant_id", "email", name="uq_user_tenant_id_email"),
        # Global, because it is the OIDC subject and login resolves by it alone:
        # two users sharing one subject would make the callback ambiguous.
        #
        # Nullable while `invited`, and MariaDB treating NULLs in a unique key as
        # distinct is exactly what is wanted here — every pending invitation has a
        # NULL subject and they must all coexist. The opposite of the sentinel case
        # in docs/identity-db-plan.md §2, where distinct NULLs break the key.
        UniqueConstraint("authentik_sub", name="uq_user_authentik_sub"),
        # `tenant_id` leads, per §1.7: the session filter injects it into every
        # query, so an index without it cannot be used.
        Index("ix_user_tenant_id_status", "tenant_id", "status"),
        # Declared so InnoDB does not invent them, named after the constraint, and
        # then read as autogenerate drift forever. Both break §1.7 under its first
        # exception: an index supporting a foreign key must lead with the FK's own
        # columns.
        Index("ix_user_reporting_manager_id", "reporting_manager_id"),
        Index("ix_user_default_company_id", "default_company_id"),
        # Added with the FK in revision 0020, once `department` exists (Phase 6). The
        # index leads with the FK column (§1.7 first exception) so InnoDB does not
        # invent a shadow one named after the constraint.
        Index("ix_user_default_department_id", "default_department_id"),
        MARIADB_TABLE_ARGS,
    )

    # --- link and type ---------------------------------------------------------
    #: OIDC subject. NULL until the invitation is accepted — an invited user has no
    #: Authentik account yet, and inventing one would mean provisioning a login for
    #: someone who may never accept.
    authentik_sub: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Local access revocation boundary, not IdP session/credential state.
    tokens_valid_after_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    user_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # --- name ------------------------------------------------------------------
    salutation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: Nullable — mononymous names are real, and a required surname makes them
    #: unrepresentable.
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: Rendered everywhere. Derived on create, then user-editable, which is why it
    #: is stored rather than composed at read time.
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # --- contact ---------------------------------------------------------------
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    #: A mirror of Authentik's state — a cache, never the source of truth. Treating
    #: it as authoritative would let a stale row grant access Authentik refuses.
    email_verified_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    phone_country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone_verified_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)

    # --- org -------------------------------------------------------------------
    #: HR reference. Survives anonymization, because it is the tenant's own handle
    #: on a person whose PII has been tombstoned.
    employee_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reporting_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        ForeignKey("user.id", name="fk_user_reporting_manager_id"),
        nullable=True,
    )
    #: The company the app opens on. Carries a foreign key — it is a real
    #: relationship, unlike the ``*_by`` metadata columns (§1.5).
    default_company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        ForeignKey("company.id", name="fk_user_default_company_id"),
        nullable=True,
    )
    #: The FK was deferred to Phase 6 — ``department`` did not exist at revision 0014,
    #: and one direction of the cycle had to give. Revision 0020 adds the constraint
    #: (and its supporting index) once ``department`` is created.
    default_department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        ForeignKey("department.id", name="fk_user_default_department_id"),
        nullable=True,
    )
    date_of_joining: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    date_of_exit: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    # --- preferences -----------------------------------------------------------
    # Presentation only. A user may **not** override `amount_precision`,
    # `quantity_precision` or `rounding_mode`: those change computed totals, so they
    # are company-level and frozen once anything has posted (docs/company.md §4.5).
    # Two users must never see different totals for the same document.
    locale: Mapped[str | None] = mapped_column(String(8), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    date_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    datetime_format: Mapped[str | None] = mapped_column(String(30), nullable=True)
    digit_grouping: Mapped[str | None] = mapped_column(String(10), nullable=True)
    currency_display: Mapped[str | None] = mapped_column(String(20), nullable=True)
    theme: Mapped[str | None] = mapped_column(String(20), nullable=True)
    landing_page: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # --- lifecycle -------------------------------------------------------------
    invited_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    invited_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    activated_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    #: Written asynchronously, never on the request path: a write per request turns
    #: every read into a write and every login into a hot row.
    last_active_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    #: Evidence for the ``deactivated`` status, not a second lifecycle switch — there
    #: is no ``is_active`` on this table (rule 4.12).
    deactivated_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    deactivated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    deactivation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: Stamped when PII is tombstoned. Set means the name and email in this row are
    #: placeholders, which is what stops a report presenting them as real.
    anonymized_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)

    # --- legal -----------------------------------------------------------------
    terms_accepted_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    terms_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    privacy_accepted_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)

    # --- extensibility ---------------------------------------------------------
    #: Store, validate, display, report — never price, tax, post or route approvals
    #: from one (CLAUDE.md invariant 14).
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
