"""Enabling, disabling and locking a company's features.

The catalogue — the dependency graph, the tax gates, which event locks which
feature — lives in ``billing_platform.features`` because every service reads it.
What lives here is the **policy over actual rows**: what the current state permits,
which rows a transition has to write, and what the ratchet refuses
(docs/company-features.md §4).

Two rules do the work.

**Dependencies close upward on enable and downward on disable.** Enabling
``expiry_tracking`` enables ``batch_tracking`` and ``inventory`` too, in that order,
or the request is rejected — never one without the other, because nothing
downstream re-checks it. Disabling ``inventory`` while any dependent is on is
refused for the same reason.

**Once ``locks_on`` fires, the feature is permanently enabled.** Enable
multi-currency, post a USD invoice against an INR base, disable multi-currency —
and nobody can say what that invoice is worth or which rate reproduces the figure
already filed. So ``locked_at`` is set by the first dependent write, inside that
write's transaction, and never cleared. Enforced for **every** actor including
platform admin: there is no actor parameter in this module, which is what makes
that structural rather than a promise.

No framework and no ORM here (CLAUDE.md §4). Callers pass the current rows as plain
``FeatureState`` values and get back what to write.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from billing_platform.errors import (
    FeatureNotEnabledError,
    ImmutableFieldError,
    ValidationFailedError,
)
from billing_platform.features import (
    FEATURES,
    assert_offerable,
    dependents,
    feature_locked_by_event,
    get,
    required_closure,
)


@dataclass(frozen=True, slots=True)
class FeatureState:
    """One ``company_feature`` row, reduced to what the rules read.

    A plain value rather than the ORM object so these rules can be tested with no
    database at all, and so a caller cannot accidentally mutate a row by deciding
    what to do with it.
    """

    is_enabled: bool
    locked_at: dt.datetime | None = None
    lock_reason: str | None = None


#: What a company's feature rows are, keyed by ``feature_key``. **An absent key means
#: disabled** (docs/company-features.md §3) — never "unknown, so allow".
FeatureRows = Mapping[str, FeatureState]


@dataclass(frozen=True, slots=True)
class FeatureOffer:
    """One catalogue entry as a setup form offers it: a name and a sentence.

    Wording and order are policy, so they are here rather than in
    ``billing_platform.features`` — no other service shows this list, and a label is
    not a rule. The *graph* stays there and is read, never restated.
    """

    key: str
    label: str
    description: str


#: The order the capabilities are offered in — Tally's F11 moment, grouped the way the
#: doc groups them (accounting, then inventory depth, then statutory, then commercial)
#: rather than alphabetically, because "Expiry dates" means nothing above "Batches".
#:
#: The console wizard carried this table itself during the UI phase; a stale copy there
#: could only omit a new capability from the screen, but a capability nobody can enable
#: is indistinguishable from one that does not exist.
OFFERED_FEATURES: Final[tuple[FeatureOffer, ...]] = (
    FeatureOffer(
        "inventory",
        "Stock and inventory",
        "Track item quantities, and value them on every movement.",
    ),
    FeatureOffer(
        "bom_definitions",
        "BOM definitions",
        "Define single-level manufacturing recipes, outputs and dated applicability. Production execution remains separate.",
    ),
    FeatureOffer(
        "multi_godown", "Multiple warehouses", "Hold and move stock across more than one location."
    ),
    FeatureOffer(
        "batch_tracking", "Batches", "Record a batch on every movement of a tracked item."
    ),
    FeatureOffer("expiry_tracking", "Expiry dates", "Record and report expiry against each batch."),
    FeatureOffer(
        "serial_tracking", "Serial numbers", "Identify individual units by serial number."
    ),
    FeatureOffer(
        "multi_currency",
        "Foreign currency",
        "Record documents in a currency other than the books currency.",
    ),
    FeatureOffer(
        "cost_centres", "Cost centres", "Allocate amounts across departments or projects."
    ),
    FeatureOffer("budgets", "Budgets", "Set budgets and report against them."),
    FeatureOffer(
        "e_invoicing", "GST e-invoicing", "Register invoices with the IRP and carry the IRN."
    ),
    FeatureOffer("e_waybill", "E-way bills", "Generate e-way bills for goods movements."),
    FeatureOffer("tds", "TDS", "Deduct tax at source on purchases and expenses."),
    FeatureOffer("tcs", "TCS", "Collect tax at source on sales."),
    FeatureOffer("reverse_charge", "Reverse charge", "Account for tax the recipient owes."),
    FeatureOffer(
        "sales_promotions",
        "Sales promotion definitions",
        "Author reviewed commercial definitions. Sale application requires the separate consumer release and enforcement checks.",
    ),
    FeatureOffer("multi_price_levels", "Price levels", "Keep different prices per customer group."),
    FeatureOffer(
        "credit_limits", "Credit limits", "Hold orders that would exceed a customer's limit."
    ),
    FeatureOffer("recurring_billing", "Recurring invoices", "Raise invoices on a schedule."),
    FeatureOffer("point_of_sale", "Point of sale", "Counter billing with its own till session."),
    FeatureOffer(
        "approval_workflow", "Approvals", "Require a second person before a document is posted."
    ),
)


def _assert_every_feature_is_offered() -> None:
    """Checked at import, like the catalogue it mirrors, so a boot fails rather than a form.

    A feature added to ``billing_platform.features`` without a label here would be
    missing from every setup form, which reads as "the platform cannot do that" — and
    nobody would think to grep this file. A label for a feature that no longer exists is
    the same bug from the other side: it offers a capability no code honours.
    """
    keys = tuple(offer.key for offer in OFFERED_FEATURES)
    problems = {
        "not offered": sorted(set(FEATURES) - set(keys)),
        "not in the catalogue": sorted(set(keys) - set(FEATURES)),
        "offered twice": sorted({key for key in keys if keys.count(key) > 1}),
    }
    reported = {name: found for name, found in problems.items() if found}
    if reported:
        raise ValueError(f"company feature offers are inconsistent with the catalogue: {reported}")


_assert_every_feature_is_offered()


def resolve_enabled(rows: FeatureRows) -> frozenset[str]:
    """The features currently on. What both clients render their menus from."""
    return frozenset(key for key, state in rows.items() if state.is_enabled)


def assert_enabled(feature_key: str, *, rows: FeatureRows) -> None:
    """The write-path gate. 409, deliberately not 403.

    403 means *you* may not; 409 means *nobody here can, yet*. Keeping them apart
    matters because permission denials are audit signal worth investigating, and
    feature-gated calls are ordinary client behaviour that would otherwise flood it
    (docs/company-features.md §5).
    """
    get(feature_key)
    state = rows.get(feature_key)
    if state is None or not state.is_enabled:
        raise FeatureNotEnabledError(
            f"{feature_key} is not enabled for this company.",
            feature=feature_key,
        )


def plan_enable(feature_key: str, *, rows: FeatureRows, tax_system: str) -> tuple[str, ...]:
    """The features to switch on, dependencies first. Empty if already on.

    Dependency order is load-bearing for the caller: writing in this order means a
    partial failure can leave a dependency on without its dependent, which is
    harmless, and never the reverse, which is not.
    """
    closure = required_closure(feature_key)
    for key in closure:
        assert_offerable(key, tax_system=tax_system)

    already_on = resolve_enabled(rows)
    return tuple(key for key in closure if key not in already_on)


def assert_disable_allowed(feature_key: str, *, rows: FeatureRows) -> None:
    """Refuse a disable the ratchet or the dependency graph forbids.

    Order matters: the lock is checked first because it is the answer that can never
    change, and telling someone to turn off three dependents before refusing them
    anyway would be worse than useless.
    """
    get(feature_key)
    state = rows.get(feature_key)

    if state is not None and state.locked_at is not None:
        raise ImmutableFieldError(
            f"{feature_key} cannot be disabled: {state.lock_reason or 'dependent data exists'}. "
            "Turning it off would reinterpret figures already filed.",
            fields={feature_key: "permanently enabled"},
        )

    blocking = sorted(dependents(feature_key) & resolve_enabled(rows))
    if blocking:
        raise ValidationFailedError(
            f"{feature_key} cannot be disabled while {', '.join(blocking)} "
            f"{'is' if len(blocking) == 1 else 'are'} enabled.",
            fields={feature_key: f"required by {', '.join(blocking)}"},
        )


def plan_lock(event: str, *, rows: FeatureRows) -> tuple[str, str] | None:
    """``(feature_key, lock_reason)`` for a dependent write, or ``None``.

    Called by whichever service just did the thing — a stock movement, an RCM
    posting — inside that write's transaction. Most writes lock nothing and get
    ``None`` back; that is the ordinary case, not an error.

    A dependent write against a **disabled** feature raises instead of locking it.
    Locking it would ratify a write that should never have been accepted, and
    silently make the flag permanent on the strength of the bug.
    """
    feature_key = feature_locked_by_event(event)
    if feature_key is None:
        return None

    assert_enabled(feature_key, rows=rows)

    state = rows[feature_key]
    if state.locked_at is not None:
        # Already locked. Returning None rather than the pair keeps the caller's
        # write idempotent — `locked_at` records the *first* dependent write, and
        # overwriting it would lose that.
        return None

    return feature_key, event
