"""Which companies an actor's own grants name — the object-level half of a company list.

CLAUDE.md §5.2: holding ``company.read`` says nothing about *whose* company. Every
endpoint that returns more than one company has to narrow its rows to the scopes the
actor's grants actually name, or a company-A clerk can enumerate company B's existence.

That narrowing was written once in ``api/companies.list_companies`` and is now needed by
three callers (the list, the session's resolution chain and the session's own switcher
read), so it lives here as one rule. No framework and no ORM (CLAUDE.md §4): grants are
passed in, already resolved server-side from the permission cache, and ``on_date`` is a
required argument so a decision is reproducible.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable

from billing_platform.authz import Grant, ScopePath, has_permission


def scoped_company_ids(
    grants: Iterable[Grant], permission: str, *, on_date: dt.date
) -> frozenset[uuid.UUID] | None:
    """The companies ``permission`` reaches, or ``None`` for a tenant-wide holder.

    ``None`` means *every company in the tenant* and is deliberately not an empty set:
    the two are opposite answers, and a caller that treated a missing narrowing as "no
    companies" would hide a tenant admin's own list from them.

    An empty set means the actor holds ``permission`` somewhere — possibly at a
    department, possibly in a window that has lapsed — but at no company that is in
    force today. The caller returns an empty page rather than an unfiltered query.

    Only company-scoped grants contribute. A department-scoped grant does not imply its
    company (``ScopePath`` narrows downward, never up), and a tenant-scoped one is the
    ``None`` case above.
    """
    if has_permission(grants, permission, target=ScopePath(), on_date=on_date):
        return None
    return frozenset(
        grant.scope.scope_id
        for grant in grants
        if grant.scope.scope_type == "company"
        and permission in grant.permissions
        and grant.in_force(target=ScopePath(company_id=grant.scope.scope_id), on_date=on_date)
    )
