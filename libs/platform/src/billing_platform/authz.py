"""Resolving what an actor may do to *this* object.

docs/identity-schema.md §5.3, docs/roles-permissions.md §1.1 and §1.5. The whole
authorization model is the triple ``(subject, role, scope)``, and resolution is the
union of every assignment whose scope is an **ancestor-or-self** of the object being
touched.

**An endpoint permission is not enough** (CLAUDE.md §5.2). Holding ``invoice.post``
says nothing about *whose* invoice, and a check that stops at the key is the most
likely real vulnerability in this system. So every entry point here takes the
object's ``target`` scope as a required keyword argument: there is no way to ask
"may they post an invoice" without saying which company's.

The actor's grants are passed in, never queried (CLAUDE.md invariant 7, the same
rule that shapes ``statutory.py``). They come from the permission cache, which is
resolved server-side per request — **the JWT never carries the permission set**
(CLAUDE.md §5.4), so revocation takes effect on the cache TTL rather than the token
TTL. A helper here that issued its own query would be a second data path with no
tenant scope of its own, and inside a money transaction it would be a synchronous
cross-service call.

``tenant_id`` is deliberately absent from every type in this module. It is the
session-level filter's job (CLAUDE.md §5.3), so the grants a caller holds are
already its own tenant's, and a ``tenant_id`` parameter here would read as the
isolation check while duplicating one that cannot be forgotten.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.permissions import assert_known_permission
from billing_platform.statutory import covers

#: Broadest first. The order is the containment order: a tenant-scope grant reaches
#: every company, a company-scope grant reaches every department in that company.
SCOPE_TYPES: Final[tuple[str, ...]] = ("tenant", "company", "department")

#: What ``role.scope_hint`` may say — UI guidance on the assignment form, never
#: enforcement (docs/identity-schema.md §5.1). Derived from ``SCOPE_TYPES`` so the two
#: cannot drift, plus ``platform``: a platform role is *assigned* at tenant scope like
#: any other, so ``platform`` is a hint that has no matching ``Scope`` and deliberately
#: never becomes one — a platform-scope assignment would be a cross-tenant grant.
SCOPE_HINTS: Final[frozenset[str]] = frozenset({"platform", *SCOPE_TYPES})


@dataclass(frozen=True, slots=True)
class Scope:
    """Where a grant applies — one ``role_assignment``'s ``(scope_type, scope_id)``.

    At tenant scope ``scope_id`` is ``SCOPE_ALL`` rather than ``NULL``, because
    MariaDB treats NULLs inside a unique key as distinct and the assignment's
    unique key contains it (docs/identity-db-plan.md §2). The API continues to
    accept and return ``null``; the sentinel never crosses the boundary.
    """

    scope_type: str
    scope_id: uuid.UUID = SCOPE_ALL

    def __post_init__(self) -> None:
        if self.scope_type not in SCOPE_TYPES:
            raise ValidationFailedError(
                f"unknown scope type: {self.scope_type!r}",
                fields={"scope_type": f"not one of {', '.join(SCOPE_TYPES)}"},
            )
        if self.scope_type == "tenant" and self.scope_id != SCOPE_ALL:
            raise ValidationFailedError(
                "a tenant-scope grant applies to the whole tenant and names no object",
                fields={"scope_id": "must be omitted at tenant scope"},
            )
        if self.scope_type != "tenant" and self.scope_id == SCOPE_ALL:
            raise ValidationFailedError(
                f"a {self.scope_type}-scope grant must name the {self.scope_type}",
                fields={"scope_id": f"required at {self.scope_type} scope"},
            )

    @property
    def breadth(self) -> int:
        """Position in ``SCOPE_TYPES`` — smaller is broader.

        Read by the third escalation guard, which refuses a grant broader than the
        granter's own (docs/roles-permissions.md §1.5). Breadth alone is not the
        guard: two company scopes are equally broad and still unrelated, which is
        why the guard compares against the target's ``ScopePath`` as well.
        """
        return SCOPE_TYPES.index(self.scope_type)


#: The scope that reaches everything in one tenant. A module constant because it is
#: what every ``tenant_admin`` assignment carries and constructing it by hand
#: invites passing a ``scope_id`` that then has to be rejected.
TENANT_SCOPE: Final[Scope] = Scope("tenant")


@dataclass(frozen=True, slots=True)
class ScopePath:
    """The object being touched, as its own ancestry — broadest first.

    The caller supplies the ancestry because only it can: a department's company is
    a ``department`` row this library must not read, and resolving it here would
    make every permission check a query. Building the path is one join at the
    boundary; getting it wrong is a cross-company read, so it is deliberately
    explicit rather than defaulted.

    ``ScopePath()`` — no company, no department — is a tenant-wide object, such as
    the tenant's own settings.
    """

    company_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    department_ancestors: tuple[uuid.UUID, ...] = ()

    def __post_init__(self) -> None:
        if self.department_ancestors and (
            self.department_id is None
            or SCOPE_ALL in self.department_ancestors
            or self.department_id in self.department_ancestors
            or len(set(self.department_ancestors)) != len(self.department_ancestors)
            or len(self.department_ancestors) > 5
        ):
            raise ValidationFailedError("invalid department ancestry")
        if self.department_id is not None and self.company_id is None:
            raise ValidationFailedError(
                "a department belongs to a company, so its path must name the company",
                fields={"company_id": "required when department_id is given"},
            )
        for name, value in (
            ("company_id", self.company_id),
            ("department_id", self.department_id),
        ):
            if value == SCOPE_ALL:
                raise ValidationFailedError(
                    f"{name} is the sentinel meaning 'all', which is not an object",
                    fields={name: "must be a real id"},
                )

    def scopes(self) -> tuple[Scope, ...]:
        """Every scope a grant could carry and still reach this object."""
        found = [TENANT_SCOPE]
        if self.company_id is not None:
            found.append(Scope("company", self.company_id))
        if self.department_id is not None:
            found.extend(Scope("department", value) for value in self.department_ancestors)
            found.append(Scope("department", self.department_id))
        return tuple(found)

    def includes(self, scope: Scope) -> bool:
        """Whether ``scope`` is an ancestor of this object, or the object itself.

        Equality on both fields, not breadth: a grant on company A must not reach
        company B's invoice however broad ``company`` scope sounds. That
        substitution — comparing only ``scope_type`` — is the shape CLAUDE.md §5.2
        is warning about.
        """
        return scope in self.scopes()


@dataclass(frozen=True, slots=True)
class Grant:
    """One ``role_assignment`` row joined to its role's permission keys.

    ``is_active`` and the validity window are **two questions, both of which must
    pass** — not the two competing lifecycles rule 4.12 forbids. ``is_active``
    false is *revocation*, which has to take effect the moment it is written and
    cannot be expressed as a date. The window is *scheduled elevation* — the
    year-end auditor whose access lapses on a date rather than when someone
    remembers (docs/identity-schema.md §5.3). Neither can override the other in
    the permissive direction, which is what keeps the pair unambiguous.
    """

    #: No defaults on these three. A ``Grant`` that defaulted to "every permission
    #: this role has, tenant-wide, since the beginning of time" is exactly the row
    #: a forgotten argument should not silently produce.
    permissions: frozenset[str]
    scope: Scope
    valid_from: dt.date
    #: ``None`` is open-ended, not unknown.
    valid_to: dt.date | None = None
    is_active: bool = True

    def in_force(self, *, target: ScopePath, on_date: dt.date) -> bool:
        """Whether this grant reaches ``target`` on ``on_date``."""
        return (
            self.is_active
            and covers(self.valid_from, self.valid_to, on_date)
            and target.includes(self.scope)
        )


def resolve_permissions(
    grants: Iterable[Grant], *, target: ScopePath, on_date: dt.date
) -> frozenset[str]:
    """The union of every grant in force on ``target``.

    A union, never an intersection and never "the narrowest one wins": roles are
    additive by design (docs/roles-permissions.md §1.1), which is what lets one
    person be a clerk in one company and a viewer in another without a third role
    being invented for them.

    Subtraction happens later and elsewhere — ``field_policy`` narrows an update
    already permitted (docs/field-permissions.md), and it never widens.
    """
    return frozenset(
        permission
        for grant in grants
        if grant.in_force(target=target, on_date=on_date)
        for permission in grant.permissions
    )


def has_permission(
    grants: Iterable[Grant], permission: str, *, target: ScopePath, on_date: dt.date
) -> bool:
    """Whether the actor holds ``permission`` **on this object**.

    ``permission`` is checked against the code catalogue first, and an unknown key
    raises rather than returning ``False``. Returning ``False`` would turn a typo in
    a route's declared permission into a permanent, plausible-looking 403 that
    nobody would think to grep the catalogue for.
    """
    assert_known_permission(permission, named_by="a permission check")
    return any(
        permission in grant.permissions
        for grant in grants
        if grant.in_force(target=target, on_date=on_date)
    )


def assert_permitted(
    grants: Iterable[Grant], permission: str, *, target: ScopePath, on_date: dt.date
) -> None:
    """Deny by default (CLAUDE.md §5.1): no matching grant is a 403.

    The message names the permission — a client needs to know what to ask for —
    and nothing about the object, the actor, or which grants were considered
    (CLAUDE.md §5.8). A denial that explains itself in detail is a scope-probing
    tool.
    """
    if not has_permission(grants, permission, target=target, on_date=on_date):
        raise PermissionDeniedError(f"this action requires {permission}")


# ---------------------------------------------------------------------------
# Wire codec
#
# One canonical (de)serialization for a resolved grant set. Both the permission
# cache (identity ``services/authz_cache``) and the gateway's signed actor context
# (identity ``api/login.gateway_authorize``) speak this shape, so it lives here rather
# than being written twice and drifting. The API boundary speaks ``null`` for a
# tenant-wide ``scope_id``; the resolver speaks the ``SCOPE_ALL`` sentinel (see
# :class:`Scope`), and the codec is the single place that translation happens.
# ---------------------------------------------------------------------------


def grant_to_wire(grant: Grant) -> dict[str, Any]:
    """A single grant as JSON-safe primitives. ``permissions`` is sorted so the
    encoding of an identical grant set is stable (a stable cache value, a stable
    signed context)."""
    return {
        "permissions": sorted(grant.permissions),
        "scope_type": grant.scope.scope_type,
        "scope_id": None if grant.scope.scope_id == SCOPE_ALL else str(grant.scope.scope_id),
        "valid_from": grant.valid_from.isoformat(),
        "valid_to": grant.valid_to.isoformat() if grant.valid_to else None,
        "is_active": grant.is_active,
    }


def grant_from_wire(raw: Mapping[str, Any]) -> Grant:
    """Rebuild a :class:`Grant` from :func:`grant_to_wire`. A ``null`` ``scope_id``
    becomes the ``SCOPE_ALL`` sentinel; ``Scope.__post_init__`` still validates that a
    non-tenant scope names its object, so a malformed entry raises rather than granting
    tenant-wide by accident."""
    scope_id_raw = raw.get("scope_id")
    scope = Scope(
        scope_type=str(raw["scope_type"]),
        scope_id=SCOPE_ALL if scope_id_raw is None else uuid.UUID(str(scope_id_raw)),
    )
    valid_to_raw = raw.get("valid_to")
    return Grant(
        permissions=frozenset(str(p) for p in raw["permissions"]),
        scope=scope,
        valid_from=dt.date.fromisoformat(str(raw["valid_from"])),
        valid_to=None if valid_to_raw is None else dt.date.fromisoformat(str(valid_to_raw)),
        is_active=bool(raw.get("is_active", True)),
    )


def encode_grants(grants: Iterable[Grant], groups: Iterable[uuid.UUID]) -> str:
    """A resolved authority set — grants plus the actor's group ids — as one compact
    JSON string suitable for a cache value. Groups are sorted for a stable encoding."""
    return json.dumps(
        {
            "grants": [grant_to_wire(g) for g in grants],
            "groups": sorted(str(g) for g in groups),
        },
        separators=(",", ":"),
    )


def decode_grants(data: str) -> tuple[tuple[Grant, ...], frozenset[uuid.UUID]]:
    """Inverse of :func:`encode_grants`. Raises ``ValueError`` on any malformed or
    truncated payload — including one whose ``scope`` fails validation — so a caller
    can treat a poisoned or version-skewed cache entry as a miss and re-resolve from
    the source of truth, in one ``except ValueError``."""
    try:
        obj = json.loads(data)
        grants = tuple(grant_from_wire(entry) for entry in obj["grants"])
        groups = frozenset(uuid.UUID(str(g)) for g in obj.get("groups", ()))
    except (KeyError, TypeError, ValidationFailedError) as exc:
        raise ValueError("malformed grant payload") from exc
    return grants, groups
