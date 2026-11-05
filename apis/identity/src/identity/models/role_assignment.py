"""``role_assignment`` — the ``(subject, role, scope)`` triple.

docs/identity-schema.md §5.3, docs/roles-permissions.md §1.1 and §1.5. This is the
whole authorization model. Resolution is the union of every assignment whose scope is
an **ancestor-or-self** of the object being touched, and that resolution is
``billing_platform.authz`` — the rows here are its only input.

**``scope_id`` is NOT NULL and tenant scope stores ``SCOPE_ALL``**, where §5.3 has
NULL (docs/identity-db-plan.md §2). The unique key contains ``scope_id``, and MariaDB
treats NULLs inside a unique index as distinct, so one user could be granted
``tenant_admin`` tenant-wide any number of times — each row a separate revocation
somebody has to find. The API continues to accept and return ``null``; the sentinel
never crosses the boundary.

Both of rule 4.12's date-shaped mechanisms sit on this row, and that is not the rule's
"two competing lifecycles". ``is_active`` false is **revocation**, which must take
effect the moment it is written; ``valid_from``/``valid_to`` is **scheduled
elevation** — the year-end auditor whose access lapses on a date rather than when
someone remembers. Both must pass for a grant to be in force, so neither can override
the other in the permissive direction (``Grant.in_force``).

Every write here is a ``security``-category audit event, and the three escalation
guards in ``identity/domain/`` are what stand between this table and self-promotion:
you cannot grant a permission you do not hold, cannot modify your own assignments
directly or via a group you belong to, and cannot grant at a scope broader than your
own.
"""

from __future__ import annotations

import uuid
from typing import Final

from billing_platform.authz import SCOPE_TYPES
from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import (
    AuditMixin,
    DeactivableMixin,
    EffectiveMixin,
    IdMixin,
    TenantMixin,
)
from billing_platform.db.types import Uuid7
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

#: Both vocabularies are imported rather than restated: a second list would let a value
#: be storable here and unresolvable where it is enforced. ``SUBJECT_TYPES`` lives in
#: ``domain/`` because the escalation guards read it — models depending on domain, never
#: the reverse, which is what keeps ``domain/`` free of the ORM.
from identity.domain.authorization import SUBJECT_TYPES

ASSIGNMENT_SCOPE_TYPES: Final[frozenset[str]] = frozenset(SCOPE_TYPES)

__all__ = ["ASSIGNMENT_SCOPE_TYPES", "SUBJECT_TYPES", "RoleAssignment"]


class RoleAssignment(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, EffectiveMixin, Base):
    """docs/identity-schema.md §5.3."""

    __tablename__ = "role_assignment"

    # Deliberately **not** `__tenant_shared__`. A tenant may assign a system role, but
    # the assignment itself is that tenant's own row and must never be visible to
    # another — this is the table that says who can do what.

    __table_args__ = (
        # The full name — `..._subject_type_subject_id_role_id_scope_type_scope_id` —
        # is 70 characters, past the 64-character limit (docs/identity-db-plan.md
        # §1.3). Shortened by collapsing each `<thing>_type, <thing>_id` pair to
        # `<thing>`, so the name no longer lists its columns and a test asserts them.
        UniqueConstraint(
            "subject_type",
            "subject_id",
            "role_id",
            "scope_type",
            "scope_id",
            name="uq_role_assignment_subject_role_scope",
        ),
        # The resolution query, run on every request that touches a scoped object:
        # "what does this subject hold". `tenant_id` leads because the session filter
        # injects it (§1.7).
        Index("ix_role_assignment_tenant_id_subject", "tenant_id", "subject_type", "subject_id"),
        # Declared, not left to InnoDB, which would name it after the constraint and
        # read as autogenerate drift forever.
        Index("ix_role_assignment_role_id", "role_id"),
        MARIADB_TABLE_ARGS,
    )

    subject_type: Mapped[str] = mapped_column(String(12), nullable=False)
    #: No foreign key: it points at ``user`` **or** ``user_group`` depending on
    #: ``subject_type``, and no single constraint can express that. The compensating
    #: check is in ``domain/`` — the subject is resolved before the row is written,
    #: never trusted from the request.
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: A plain foreign key, **not** the composite one ``role_permission`` uses: a
    #: tenant legitimately assigns a system role, so the two ``tenant_id`` values
    #: differ by design and requiring them to agree would make the shipped roles
    #: unassignable.
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey("role.id", name="fk_role_assignment_role_id"),
        nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(String(12), nullable=False)
    #: ``SCOPE_ALL`` at tenant scope. No foreign key — it points at ``company`` or
    #: ``department`` by ``scope_type``, and at neither when it holds the sentinel.
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: Escalation-guard evidence, and the reason this is not merely ``created_by``:
    #: an assignment created by a migration or an SSO provisioning job has an actor
    #: for the row and no granter for the grant.
    granted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    #: Why, for the access review that asks it a year later.
    grant_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
