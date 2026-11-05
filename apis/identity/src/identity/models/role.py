"""``role`` — a named permission bundle.

docs/identity-schema.md §5.1, docs/roles-permissions.md. **Permissions are code, roles
are data** (CLAUDE.md invariant 13): the key set is a fixed catalogue in
``billing_platform.permissions``, and this table is what a tenant composes out of it.

Two departures from the doc's field grid, both deliberate and both recorded in that
doc's decision log.

**``tenant_id`` is NOT NULL and a system role carries ``SCOPE_ALL``**, not NULL
(docs/identity-db-plan.md §2). The doc's ``UNIQUE (tenant_id, key)`` cannot work with
NULLs: MariaDB treats them as distinct inside a unique index, so ``billing_clerk``
could be inserted as a system role any number of times. The session filter's
exception is written for the sentinel — ``tenant_id = :current OR tenant_id =
SCOPE_ALL`` — and gated by ``__tenant_shared__`` rather than by table name.

**``is_system`` is a property, not a column.** A stored flag can disagree with
``tenant_id``, and the disagreement is an escalation: ``is_system = false`` on a row
with ``tenant_id = SCOPE_ALL`` is a platform-wide role a tenant may edit. Deriving it
makes that state unrepresentable rather than merely wrong. The doc's
``INDEX (is_system)`` goes with it — ``ix_role_tenant_id`` from ``TenantMixin``
already serves every query that would have used it.
"""

from __future__ import annotations

import uuid

from billing_platform.authz import SCOPE_HINTS
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

#: Re-exported from ``billing_platform.authz``, where it is derived from ``SCOPE_TYPES``.
#: UI guidance for the assignment form — which scope this role is *meant* for. Never
#: enforcement: what a grant reaches is ``role_assignment``'s own scope, and treating
#: this as the check would put authorization in a hint column (§5.1).
__all__ = ["SCOPE_HINTS", "Role"]


class Role(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    """docs/identity-schema.md §5.1."""

    __tablename__ = "role"
    #: System roles are visible to every tenant. Without this the session filter
    #: hides all twelve shipped roles and nobody can be assigned anything.
    __tenant_shared__ = True

    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_role_tenant_id_key"),
        # The parent of `role_permission`'s composite foreign key. `id` alone is the
        # primary key, so the pair is trivially unique — declared UNIQUE to say so
        # rather than leaving InnoDB's laxer requirement to carry the meaning.
        UniqueConstraint("id", "tenant_id", name="uq_role_id_tenant_id"),
        Index("ix_role_cloned_from_role_id", "cloned_from_role_id"),
        MARIADB_TABLE_ARGS,
    )

    #: ``key`` is a **MariaDB reserved word**, so every hand-written statement that
    #: names it must backtick it. SQLAlchemy quotes it in generated SQL; the raw DDL
    #: in ``dbs/identity/versions/`` does not get that for free, and a test compiles
    #: ``CreateTable`` under the mysql dialect to keep the two honest.
    #:
    #: Stable and **never renamed**: seeds name it, and a rename is a silent
    #: revocation for every tenant holding an assignment to it.
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    #: Display only, and freely editable — which is exactly why ``key`` exists.
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: Set when a tenant clones a system role. Kept for provenance in an access
    #: review: "where did this bundle come from" is otherwise unanswerable once the
    #: clone has been edited. Not a live link — the clone does not track its origin.
    cloned_from_role_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        ForeignKey("role.id", name="fk_role_cloned_from_role_id"),
        nullable=True,
    )
    scope_hint: Mapped[str | None] = mapped_column(String(20), nullable=True)

    @property
    def is_system(self) -> bool:
        """A shipped, read-only role rather than one a tenant composed.

        Derived, so it cannot disagree with ``tenant_id``. A plain property and not
        a hybrid: the SQL form is ``tenant_id == SCOPE_ALL``, which every caller can
        write directly, and a hybrid would offer a second spelling of the filter
        that has to stay in step with the session-level one.
        """
        return self.tenant_id == SCOPE_ALL
