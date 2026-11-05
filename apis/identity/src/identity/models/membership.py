"""``membership`` — a user's affiliation to a company or department.

docs/identity-schema.md §4.7, docs/org-model.md §2.3. **Affiliation, not authorization.**
A membership says where a person works; what they may do is ``role_assignment`` alone.
The two are separate tables on purpose — different lifecycles (HR vs security) and
different reviewers — and a membership may exist with no access at all (the Phase 6 exit
test: a user with a membership and no assignment reaches nothing).
"""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class Membership(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    """docs/identity-schema.md §4.7."""

    __tablename__ = "membership"
    __table_args__ = (
        Index("ix_membership_user_owner", "tenant_id", "user_id"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["user.tenant_id", "user.id"], name="fk_membership_user_owner"
        ),
        Index("ix_membership_company_owner", "tenant_id", "company_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["company.tenant_id", "company.id"],
            name="fk_membership_company_owner",
        ),
        Index("ix_membership_department_owner", "tenant_id", "company_id", "department_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "department_id"],
            ["department.tenant_id", "department.company_id", "department.id"],
            name="fk_membership_department_owner",
        ),
        # Leads with `user_id`, so it also supports that FK. `department_id` is
        # genuinely nullable here (not a SCOPE_ALL table, db-plan §2): a company-level
        # membership has no department.
        UniqueConstraint(
            "user_id", "company_id", "department_id", name="uq_membership_user_company_department"
        ),
        UniqueConstraint(
            "user_id", "company_id", "department_scope_key", name="uq_membership_affiliation"
        ),
        UniqueConstraint("primary_user_id", name="uq_membership_active_primary"),
        Index("ix_membership_company_id", "company_id"),
        Index("ix_membership_department_id", "department_id"),
        MARIADB_TABLE_ARGS,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("user.id", name="fk_membership_user_id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("company.id", name="fk_membership_company_id"), nullable=False
    )
    #: NULL is a company-level affiliation with no department.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7, ForeignKey("department.id", name="fk_membership_department_id"), nullable=True
    )
    #: Drives the default company on login. One primary per user is a ``domain/`` rule,
    #: not a constraint (a partial unique is not available on MariaDB).
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    #: Kept for history — an ended affiliation is not deleted (invariant 12).
    ended_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    # Generated keys enforce nullable affiliations and one active primary on both
    # MySQL and SQLite. Historical inactive rows keep their affiliation identity.
    department_scope_key: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        Computed("coalesce(department_id, X'00000000000000000000000000000000')", persisted=True),
        nullable=True,
    )
    primary_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        Computed(
            "CASE WHEN is_active = 1 AND is_primary = 1 THEN user_id ELSE NULL END", persisted=True
        ),
        nullable=True,
    )
