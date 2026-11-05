"""Column mixins, composed rather than restated per table.

See docs/identity-schema.md §0.2. Field grids in that doc list only
table-specific columns; these supply the rest.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import ClassVar

from sqlalchemy import Boolean, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from billing_platform.db.types import UtcDateTime, Uuid7, utcnow
from billing_platform.ids import uuid7


class IdMixin:
    """UUIDv7 primary key."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid7, primary_key=True, default=uuid7)


class TenantMixin:
    """Tenant isolation boundary.

    Presence of this mixin is what subjects a model to the session-level tenant
    filter. It carries **no foreign key** to ``tenant`` — see
    docs/identity-db-plan.md §1.4 for why, and the compensating test.
    """

    #: When true, rows with ``tenant_id == SCOPE_ALL`` are visible to every
    #: tenant in addition to their own. Set by ``role`` and ``role_permission``:
    #: the shipped system roles are shared platform-wide, and their permission rows
    #: have to follow or the roles resolve to nothing. A naive filter hides both.
    __tenant_shared__: ClassVar[bool] = False

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False, index=True)


class SelfTenantMixin(IdMixin):
    """A table whose own primary key **is** the tenant id.

    Only ``tenant`` uses this. It carries no ``tenant_id`` column — there is
    nothing to point at — so ``TenantMixin`` cannot apply, and without a second
    mechanism the one table that *defines* the isolation boundary would be the
    only one sitting outside it. Leaving it to route-level checks contradicts
    CLAUDE.md §5.3: the filter is session-level precisely so that no route can
    forget it.

    Subclasses ``IdMixin`` rather than being combined with it, because
    ``with_loader_criteria`` resolves ``cls.id`` against this class to build the
    criteria once — so ``id`` has to be reachable from the mixin, not only from
    the model. Compose it alone: ``class Tenant(SelfTenantMixin, AuditMixin, Base)``.

    The filter compares ``id`` to the ambient tenant, so provisioning a new tenant
    and any platform-admin listing must run under ``unfiltered()`` — the same,
    greppable, audited escape hatch every other cross-tenant operation uses.

    No marker attribute: inheriting this class *is* the marker, so there is no way
    to be a self-tenant table with the flag left off.
    """


class AuditMixin:
    """Who and when, on every mutable table.

    ``*_by`` columns carry no foreign key: ``company`` is created four phases
    before ``user`` exists, while ``user.default_company_id`` points the other
    way, so one direction has to give (docs/identity-db-plan.md §1.5). Nullable
    because system and migration writes have no actor.
    """

    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class DeactivableMixin:
    """The ``is_active`` form of rule 4.12. Never combined with a ``status`` column.

    ``false`` means not selectable for new records — it never hides history.
    """

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deactivated_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    deactivated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class EffectiveMixin:
    """The date-validity form of rule 4.12, for anything affecting a computed amount.

    ``valid_to`` NULL means open-ended. A gap is meaningful and must not be
    papered over by falling back to the nearest row.
    """

    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class StatusMixin:
    """The ``status`` form of rule 4.12. Never combined with ``is_active``."""

    status: Mapped[str] = mapped_column(String(20), nullable=False)
