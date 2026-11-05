"""``company_feature`` — per-company capability toggles.

Rows, not a JSON column on ``company`` (docs/company-features.md §3). A blob
cannot carry ``enabled_by``, cannot answer "which companies have inventory on",
and gives the audit trail one opaque diff where there should be a discrete event
per feature.

**Absent row means disabled.** A missing replica row in a consuming service is a
hard failure, never an implicit enable (§5).

``locked_at`` is the ratchet. Once the feature's ``locks_on`` event fires — a stock
movement, a foreign-currency posting — the flag is **permanently enabled**, set
inside that write's transaction and never cleared. Disabling multi-currency after a
USD invoice was filed against an INR base leaves nobody able to say what the
invoice is worth. Enforced in ``domain/`` for every actor including platform admin;
it is not a permission and no role overrides it.

Three columns look like they duplicate ``AuditMixin`` and do not:
``enabled_at``/``enabled_by`` and ``disabled_at``/``disabled_by`` are the *last*
transition each way and survive the next one, while ``updated_at``/``updated_by``
is simply the most recent write of any kind.

The lifecycle mechanism here is ``is_enabled`` — rule 4.12's boolean form, never
combined with a ``status``. It is not ``DeactivableMixin``, whose ``is_active``
means "not selectable for new records": this flag gates capability, and its
irreversibility lives in ``locked_at`` rather than in a deactivation timestamp.
"""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CompanyFeature(IdMixin, TenantMixin, AuditMixin, Base):
    """docs/identity-schema.md §3.4."""

    __tablename__ = "company_feature"
    __table_args__ = (
        # No `tenant_id` in the key, unlike `uq_company_tenant_id_code`: `company_id`
        # already determines the tenant, so adding it would let the same
        # (company, feature) pair insert twice under a mismatched `tenant_id` —
        # a weaker constraint, not a stronger one.
        #
        # It leads with `company_id`, which also supports
        # `fk_company_feature_company_id` and keeps InnoDB from inventing an index
        # for it (docs/identity-db-plan.md §1.7's foreign-key case).
        UniqueConstraint(
            "company_id", "feature_key", name="uq_company_feature_company_id_feature_key"
        ),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey("company.id", name="fk_company_feature_company_id"),
        nullable=False,
    )
    #: From the code catalogue in ``billing_platform.features``. **No foreign key**:
    #: features are code, not data, for the same reason permission keys are — a
    #: feature is a claim that code exists to honour it. Boot rejects a row naming a
    #: key the catalogue does not have.
    feature_key: Mapped[str] = mapped_column(String(60), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    enabled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    disabled_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    disabled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    #: Non-null means **permanently enabled**. Set by the first dependent write,
    #: inside that transaction, and never cleared.
    locked_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    #: The ``locks_on`` event that locked it, kept so the rejection message can say
    #: *why* rather than "this cannot be changed".
    lock_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
