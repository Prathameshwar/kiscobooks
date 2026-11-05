"""The freeze on a company's shape once anything has posted.

docs/company.md §5.2, CLAUDE.md invariant 16. Ten columns become immutable the
moment ``first_posted_at`` is set, because changing any of them **reinterprets
figures that have already been filed** rather than merely altering a setting:

* ``base_currency`` — ₹100,000 silently becomes $100,000
* ``fiscal_year_start_month`` / ``_day`` — every posted document's period moves
* ``books_begin_date`` — postings would exist before the books open
* ``amount_precision`` / ``quantity_precision`` / ``rounding_mode`` — recomputed
  totals stop matching the documents already sent to customers and to the tax
  authority
* ``code`` — already embedded in issued document numbers
* ``country_code`` — changes the jurisdiction profile existing rows were validated
  under
* ``state_code`` — flips every issued invoice between intra-state and inter-state

**This is not a permission.** No role lifts it, no platform admin overrides it, and
there is deliberately no actor parameter in this module for one to be checked
against — the same class of rule as "a posted document in a closed period is never
edited" (docs/field-permissions.md §1). Changing one of these after posting means a
new company and a migration of opening balances: a deliberate, audited operation,
never a settings edit.

No framework and no database here (CLAUDE.md §4). The caller supplies the current
row's values and the incoming ones; what comes back is a decision.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from typing import Any, Final

from billing_platform.errors import ImmutableFieldError

#: docs/company.md §5.2's table, as a set. Ordered output everywhere it is reported,
#: so an error message is stable enough to assert on.
IMMUTABLE_AFTER_POSTING: Final[frozenset[str]] = frozenset(
    {
        "base_currency",
        "fiscal_year_start_month",
        "fiscal_year_start_day",
        "books_begin_date",
        "amount_precision",
        "quantity_precision",
        "rounding_mode",
        "code",
        "country_code",
        "state_code",
    }
)


def changed_fields(current: Mapping[str, Any], incoming: Mapping[str, Any]) -> frozenset[str]:
    """The fields whose value actually differs, not the ones merely present.

    The distinction is the whole point (docs/field-permissions.md §6, and the same
    rule field policy uses): a client that PUTs the entire company back, unchanged,
    is not editing anything. Rejecting on payload presence would make every full
    update impossible after the first posting, and clients would work around it by
    sending partial payloads — which is how a field ends up cleared by accident.

    Keys absent from ``incoming`` are untouched. Keys absent from ``current`` are
    reported as changed, because there is nothing to compare them against.
    """
    return frozenset(
        key for key, value in incoming.items() if key not in current or current[key] != value
    )


def assert_company_fields_mutable(
    changed: Iterable[str], *, first_posted_at: dt.datetime | None
) -> None:
    """Reject a change to a frozen field. Takes no actor, by design.

    Before the first posting every one of these is freely editable — that window is
    exactly what it is for. After it, the answer is no for everybody.
    """
    if first_posted_at is None:
        return

    frozen = sorted(set(changed) & IMMUTABLE_AFTER_POSTING)
    if not frozen:
        return

    raise ImmutableFieldError(
        f"{', '.join(frozen)} cannot be changed: this company has posted documents. "
        "Changing it would reinterpret figures already filed. A new company with "
        "migrated opening balances is the supported route.",
        fields={name: "immutable after first posting" for name in frozen},
    )


def assert_update_allowed(
    current: Mapping[str, Any],
    incoming: Mapping[str, Any],
    *,
    first_posted_at: dt.datetime | None,
) -> None:
    """The two steps above, in the order every caller needs them.

    Exists so no route has to remember to diff before checking — computing the
    changed set from the payload alone is the mistake this prevents.
    """
    assert_company_fields_mutable(
        changed_fields(current, incoming), first_posted_at=first_posted_at
    )
