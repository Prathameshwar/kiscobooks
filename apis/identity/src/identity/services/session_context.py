"""Which company a session opens, and why.

The chain is **four rules in order** (docs/company-context-ui-todo.md, Part 2):

1. the company named on the request — an explicit switch
2. the company stored on the user as their default
3. the company of their primary membership — where this person works
4. the first company they can open, ordered by ``code``

It lives here, server-side, so that the console, mobile and every later client share one
answer. The console resolved it itself during the UI phase and had to make two session
round trips to do it; worse, its last step passed the company back as an explicit
selection, which turns a first-readable company that happens to require step-up into a
403 on the whole page instead of a prompt.

Steps 2-4 **fall through** when a candidate is unusable — deleted, deactivated, or no
longer readable — because a stale default must not dead-end a session. They do not fall
through on step-up: that company is a valid selection whose details simply need a fresh
proof, and quietly opening a *different* company instead would be a surprising answer to
"open my default". An explicit selection never falls through at all; it is refused, so a
caller learns their switch did not happen.

**What makes a company openable is authority in it, not ``company.read``.** Every
candidate is checked against :func:`own_company_ids` — the same rule the switcher's list
uses — because the two have to agree: a list of companies that then refuse to open is not
a switcher, and `company.read` is a key the seeded clerk, approver and controller roles do
not hold (docs/roles-permissions.md §4). Opening a company discloses exactly what that
list already discloses: its id, code, display name and status. `company.read` continues to
gate everything that *describes* a company — the company list, `CompanyDetail`, its
features, its statutory identifiers, its setup readiness.

Nothing here grants anything. The scope check is per candidate company (CLAUDE.md §5.2),
and every later request is authorized again on its own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError
from billing_platform.statutory import covers
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.models import Company, Department, Membership, User
from identity.services.step_up import StepUpRequiredError, require_company

#: How the open company was chosen. The client says so rather than implying a stored
#: default — "first readable" and "my default" look identical in a rail otherwise.
CompanySource = Literal["explicit", "default", "membership", "first", "none"]


@dataclass(frozen=True, slots=True)
class CompanySelection:
    """The resolved selection: what is open, which rule chose it, and what is missing."""

    #: The company whose details and scoped permissions this session may use. ``None``
    #: when nothing was selected *or* when a selection is withheld pending a proof.
    company: Company | None
    #: The company the chain chose, even where its details are withheld. The caller's
    #: own default or workplace, so naming it back discloses nothing it did not send.
    selected_company_id: uuid.UUID | None
    source: CompanySource
    #: The selection needs fresh company authentication before it will open.
    step_up_required: bool


#: The companies an actor may work in, or ``None`` meaning every company in the tenant.
Authority = frozenset[uuid.UUID] | None


def _reaches(allowed: Authority, company_id: uuid.UUID) -> bool:
    return allowed is None or company_id in allowed


async def may_work_in(db: AsyncSession, current: Actor, company_id: uuid.UUID) -> bool:
    """Whether this actor holds any authority in this company — the openable test.

    One rule, shared with the switcher's list, so the two cannot disagree about which
    companies a person has. Exported because reading a company's *display* configuration
    asks the same question: a clerk raising an invoice in this company has to render its
    money and dates the way the company states them (CLAUDE.md §4), and that is not a
    company detail.
    """
    return _reaches(await own_company_ids(db, current), company_id)


async def _usable(db: AsyncSession, allowed: Authority, company_id: uuid.UUID) -> Company | None:
    """The company if this actor may open it today, else ``None`` and the chain moves on."""
    if not _reaches(allowed, company_id):
        return None
    row = await db.get(Company, company_id)
    return row if row is not None and row.status == "active" else None


async def can_open(db: AsyncSession, current: Actor, company_id: uuid.UUID) -> bool:
    """Whether the chain would accept ``company_id`` for this actor.

    Exported so that storing a default company and resolving one are the *same* rule.
    Validating a stored default any other way would let a person save a preference the
    chain then silently ignores, which looks like the setting did not save.
    """
    allowed = await own_company_ids(db, current)
    return await _usable(db, allowed, company_id) is not None


async def _primary_company(db: AsyncSession, current: Actor) -> uuid.UUID | None:
    """The company of the actor's primary membership — affiliation, never authorization.

    Queried on ``primary_user_id``, the generated column that *is* the "one active
    primary per user" rule (``membership`` model, docs/identity-schema.md §4.7), so this
    cannot drift from it and uses its unique index. A membership says where someone
    works; whether they may open that company is still ``_usable``'s question.
    """
    company_id: uuid.UUID | None = await db.scalar(
        select(Membership.company_id).where(Membership.primary_user_id == current.user_id).limit(1)
    )
    return company_id


async def _first_openable(db: AsyncSession, allowed: Authority) -> Company | None:
    """The lowest ``code`` among the companies this actor may work in.

    Ordered by ``code`` because that is the order the switcher and the company directory
    use, so "the first one" is the row a reader would have clicked themselves. Unlisted
    companies are left out for the same reason they are left out of the list: unlisted is
    a display preference (invariant 17), and a session should not land on a company its
    tenant chose to keep out of the switcher.
    """
    statement = (
        select(Company)
        .where(Company.status == "active", Company.visibility == "listed")
        .order_by(Company.code)
        .limit(1)
    )
    if allowed is not None:
        if not allowed:
            return None
        statement = statement.where(Company.id.in_(allowed))
    company: Company | None = await db.scalar(statement)
    return company


async def own_company_ids(db: AsyncSession, current: Actor) -> Authority:
    """The companies this actor holds **any** authority in, or ``None`` for all of them.

    This is the switcher's own list (docs/company-context-ui-todo.md D2). ``/v1/companies``
    gates on ``company.read``, which the seeded clerk, approver and controller roles do
    not hold — so for them that endpoint is a 403 and their switcher was empty during the
    UI phase. A person who raises invoices in two companies has to be able to say which
    one they are working in, and asking for ``company.read`` to do it would hand them
    every company's details instead.

    Derived from grants, never from memberships. A membership is affiliation, not
    authorization (``membership`` model): a company a person is affiliated with but holds
    nothing in would be a switcher row that refuses to open, because the resolution chain
    and every later request still check the permission.

    A tenant-scoped grant means every company, returned as ``None``. A department-scoped
    grant resolves to the department's company: that actor works in that company, and
    scoping their switcher to nothing is what the first version of this did.
    """
    today = utcnow().date()
    if any(
        grant.scope.scope_type == "tenant" and grant.in_force(target=ScopePath(), on_date=today)
        for grant in current.grants
    ):
        return None
    companies = {
        grant.scope.scope_id
        for grant in current.grants
        if grant.scope.scope_type == "company"
        and grant.in_force(target=ScopePath(company_id=grant.scope.scope_id), on_date=today)
    }
    departments = {
        grant.scope.scope_id
        for grant in current.grants
        # Only the window is asked here: a department grant reaches its own department by
        # definition, and `ScopePath` cannot even be built for one without first knowing
        # the company — which is what the query below is for.
        if grant.scope.scope_type == "department"
        and grant.is_active
        and covers(grant.valid_from, grant.valid_to, today)
    }
    if departments:
        # One bounded query, and only when such a grant exists. Tenant-filtered like
        # every other session read, so a department id from elsewhere resolves to nothing.
        rows = await db.scalars(select(Department.company_id).where(Department.id.in_(departments)))
        companies |= set(rows)
    return frozenset(companies)


async def resolve_company(
    db: AsyncSession,
    request: Request,
    current: Actor,
    user: User,
    explicit: uuid.UUID | None,
) -> CompanySelection:
    """Run the chain. Raises 403 when an *explicit* selection is refused."""
    # Resolved once: a chain that tries three candidates must not ask three times.
    allowed = await own_company_ids(db, current)
    if explicit is not None:
        # An explicit switch is refused before anything is looked up, so a caller cannot
        # probe which company ids exist by watching the chain fall through — and so the
        # refusal reads the same whether the company is absent or simply not theirs.
        if not _reaches(allowed, explicit):
            raise PermissionDeniedError("this company is not one you work in")
        chosen = await _usable(db, allowed, explicit)
        if chosen is None:
            return CompanySelection(None, explicit, "explicit", False)
        await require_company(db, request, current, chosen.id)
        return CompanySelection(chosen, chosen.id, "explicit", False)

    row: Company | None = None
    source: CompanySource = "none"
    if user.default_company_id is not None:
        row = await _usable(db, allowed, user.default_company_id)
        if row is not None:
            source = "default"
    if row is None:
        primary = await _primary_company(db, current)
        if primary is not None:
            row = await _usable(db, allowed, primary)
            if row is not None:
                source = "membership"
    if row is None:
        row = await _first_openable(db, allowed)
        if row is not None:
            source = "first"
    if row is None:
        return CompanySelection(None, None, "none", False)
    try:
        await require_company(db, request, current, row.id)
    except StepUpRequiredError:
        # Session bootstrap stays usable: the client prompts for the proof it now knows
        # is missing, instead of rendering "no company" over a company that exists.
        return CompanySelection(None, row.id, source, True)
    return CompanySelection(row, row.id, source, False)
