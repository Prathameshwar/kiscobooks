"""The privilege-escalation guards, and the policy over composing a role.

docs/roles-permissions.md §1.5, and CLAUDE.md §5.2. ``billing_platform.authz`` answers
"may this actor do this to this object". What is answered here is the harder question one
step up: **may this actor change what someone else may do.** Getting that wrong makes
``role.assign`` equivalent to every permission in the system, which is why §1.5 calls
these non-negotiable.

Three guards, all enforced on every assignment change — grant and revoke alike:

1. **You cannot assign a role containing a permission you do not hold.** Applied at the
   scope of the assignment, so a company clerk cannot hand out an authority they only
   lack there.
2. **You cannot change your own assignments** — not directly, and not through a group you
   belong to. Checked first, so the answer never depends on what the actor holds.
3. **You cannot assign at a scope broader than your own.** This is the object-level half
   of ``role.assign``: holding the key says nothing about *whose* company, and a check
   that stopped at the key is the shape CLAUDE.md §5.2 warns about.

Revocation is guarded identically to granting. It is de-escalation for the subject and
escalation for nobody, but revoking the controller's role the evening before a close is
an outage on one API call, so the authority required is the same in both directions.

**There is no ``system=True`` bypass.** §6 has exactly one documented exception — the
first ``tenant_admin`` assignment at tenant creation, made by the system principal and
audited as such — and it is a different call site that does not invoke these guards at
all. A flag here would be one boolean away from being passed by a request handler.

Two boundaries this module deliberately does not cover. Group **membership** is
``user_group``'s own guard (Phase 6): an actor barred by guard 2 from granting to their
own group could otherwise grant to a group they are not in and then join it. And guard
4 — every assignment change is a ``security``-category audit event — is the write path's
job, emitted in the same transaction through the outbox (CLAUDE.md invariant 8), not a
decision this module can make.

No framework and no ORM here (CLAUDE.md §4): the actor's grants are passed in, resolved
server-side from the permission cache, and never queried. ``on_date`` is a required
argument rather than today's date read from the clock, so a decision is reproducible.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

from billing_platform.authz import Grant, ScopePath, has_permission, resolve_permissions
from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import (
    ImmutableFieldError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.permissions import (
    separation_of_duties_conflicts,
    validated_permission_key,
)

#: What a role may be granted to. Defined here rather than in ``models`` because it is
#: domain vocabulary that these rules read, and a second list in the model layer would
#: let a value be storable in one place and unresolvable in the other.
#:
#: A role is granted to a user or a group, never to a company — that is a *scope*, the
#: other half of the triple. Conflating the two would make "everyone in company A" a
#: grant that silently follows company A's membership.
SUBJECT_TYPES: Final[frozenset[str]] = frozenset({"user", "user_group"})

#: The two keys these rules read. Named constants because a typo in a string literal
#: here fails open — a guard looking for ``role.asign`` finds nobody holding it and
#: refuses everyone, which reads as a permissions problem rather than a bug.
ROLE_ASSIGN: Final[str] = "role.assign"
ROLE_MANAGE: Final[str] = "role.manage"


@dataclass(frozen=True, slots=True)
class Actor:
    """Who is making the change, and what they hold.

    ``grants`` comes from the permission cache, resolved per request — the JWT never
    carries the permission set (CLAUDE.md §5.4), so revocation takes effect on the cache
    TTL rather than the token TTL.

    ``group_ids`` is every group the actor belongs to, and it defaults to empty because
    most actors belong to none. That default is safe in one direction only: a *missing*
    group makes guard 2 more permissive, so the caller that resolves memberships is the
    one that has to be complete, and it is tested as such.
    """

    user_id: uuid.UUID
    grants: tuple[Grant, ...] = ()
    group_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class AssignmentChange:
    """The assignment being created or revoked, as plain values.

    ``target`` is the assignment's scope expressed as its own ancestry — a
    company-scope grant is ``ScopePath(company_id=...)``. The caller builds it, because
    a department's company is a row this module must not read, and it is what both the
    scope guard and the permission comparison are measured against.
    """

    subject_type: str
    subject_id: uuid.UUID
    #: What the role being assigned grants, from ``role_permission``. Never from the
    #: request: a client-supplied permission set would make guard 1 self-certifying.
    role_permissions: frozenset[str]
    target: ScopePath

    def __post_init__(self) -> None:
        if self.subject_type not in SUBJECT_TYPES:
            raise ValidationFailedError(
                f"unknown subject type: {self.subject_type!r}",
                fields={"subject_type": f"not one of {', '.join(sorted(SUBJECT_TYPES))}"},
            )
        if self.subject_id == SCOPE_ALL:
            raise ValidationFailedError(
                "the sentinel meaning 'all' is not a subject",
                fields={"subject_id": "must be a real id"},
            )


def assert_not_own_assignment(change: AssignmentChange, *, actor: Actor) -> None:
    """Guard 2. Refuses self-modification before anything else is considered.

    A tenant admin granting themselves ``period.lock`` passes guard 1 the moment they
    hold it, and passes guard 3 at their own scope. This is the guard that stops it, and
    the reason it is unconditional: a separation of duties one person can undo alone is
    not a control.
    """
    if change.subject_type == "user" and change.subject_id == actor.user_id:
        raise PermissionDeniedError("you cannot change your own role assignments")
    if change.subject_type == "user_group" and change.subject_id in actor.group_ids:
        raise PermissionDeniedError(
            "you cannot change the role assignments of a group you belong to"
        )


def assert_scope_within_actors_own(
    change: AssignmentChange, *, actor: Actor, on_date: dt.date
) -> None:
    """Guard 3. ``role.assign`` must be held at a scope reaching the assignment's own.

    A company admin holds ``role.assign`` at company scope, so a tenant-scope
    assignment — ``ScopePath()``, which no company grant is an ancestor of — is refused,
    and so is a grant on another company. Breadth alone would not do it: two company
    scopes are equally broad and still unrelated.

    The message says what is required and never which scopes the actor does hold
    (CLAUDE.md §5.8) — a denial that explains itself is a scope-probing tool.
    """
    if not has_permission(actor.grants, ROLE_ASSIGN, target=change.target, on_date=on_date):
        raise PermissionDeniedError(
            f"this action requires {ROLE_ASSIGN} at or above the scope of the assignment"
        )


def assert_permissions_held(
    required: Iterable[str],
    *,
    actor: Actor,
    target: ScopePath,
    on_date: dt.date,
    action: str,
) -> None:
    """Guard 1. Everything the role grants must be something the actor already holds.

    Measured at ``target`` rather than tenant-wide: the actor's own grants are resolved
    against the same scope the assignment applies to, so a clerk holding ``invoice.post``
    in company A cannot pass that on in company B.

    The missing keys are named — a client needs to know what to ask for — and nothing
    about the actor or the subject is.
    """
    held = resolve_permissions(actor.grants, target=target, on_date=on_date)
    missing = sorted(frozenset(required) - held)
    if missing:
        raise PermissionDeniedError(
            f"{action} requires permissions you do not hold here: {', '.join(missing)}"
        )


def assert_assignment_change_allowed(
    change: AssignmentChange, *, actor: Actor, on_date: dt.date
) -> None:
    """All three guards, in the order a denial should be decided.

    Self-modification first, so the answer cannot depend on what the actor holds. Then
    the scope, because being in the wrong company makes the contents irrelevant. Then
    the contents, which is the check that names what is missing.
    """
    assert_not_own_assignment(change, actor=actor)
    assert_scope_within_actors_own(change, actor=actor, on_date=on_date)
    assert_permissions_held(
        change.role_permissions,
        actor=actor,
        target=change.target,
        on_date=on_date,
        action="assigning this role",
    )


def assert_role_editable(*, is_system_role: bool) -> None:
    """§1.2. A shipped role is read-only, to every actor including platform admin.

    ``ImmutableFieldError`` rather than a 403, for the same reason the company ratchet
    uses it: this is not "you may not", it is "nobody may". An upgrade that adds a
    permission to a shipped role must not be silently reverted by a tenant's edit, and
    code that relies on ``billing_clerk`` meaning one thing has to be able to.
    """
    if is_system_role:
        raise ImmutableFieldError(
            "a system role cannot be edited; clone it into a tenant role and edit the copy",
            fields={"role": "read-only"},
        )


def assert_role_composition_allowed(
    permissions: Iterable[str],
    *,
    actor: Actor,
    target: ScopePath,
    on_date: dt.date,
) -> tuple[tuple[str, str], ...]:
    """Guard 1 at the earlier point: composing a tenant role out of the catalogue.

    Returns the §1.4 separation-of-duties pairs the composition holds both halves of, for
    the caller to warn on and record as an ``admin``-category audit event. Returned
    rather than raised **because a tenant may legitimately need them** — a small business
    often has one person who must both raise and approve, and refusing outright would
    leave them unable to operate. A shipped system role holding a pair is the opposite
    case and fails the boot (``system_roles.py``).

    An unknown key is a 422, not a boot failure: composing a role is a legitimate
    request that can legitimately be wrong.
    """
    validated = frozenset(validated_permission_key(key) for key in permissions)

    if not has_permission(actor.grants, ROLE_MANAGE, target=target, on_date=on_date):
        raise PermissionDeniedError(f"this action requires {ROLE_MANAGE} at this scope")
    assert_permissions_held(
        validated,
        actor=actor,
        target=target,
        on_date=on_date,
        action="composing this role",
    )

    return separation_of_duties_conflicts(validated)
