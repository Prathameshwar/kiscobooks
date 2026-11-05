"""The company feature catalogue — code, not data.

A feature flag says *what this company does* (docs/company-features.md §1). It is
not a permission, which says what an actor may do, and it is not a custom field,
which stores data the platform has no opinion about. Both gates must pass:
``feature_enabled AND has_permission``.

The catalogue is here rather than in a table because **a feature is a claim that
code exists to honour it** — enabling ``batch_tracking`` is not a preference, it
turns on native capability that prices, posts and prints. A tenant cannot invent
one. Same tier as the permission catalogue and the custom-field data types.

What lives here is the **graph**: dependencies, tax-system gating, and which
event makes a flag irreversible. What does *not* live here is anything that reads
a ``company_feature`` row — that is ``identity``'s domain, because it needs the
row's ``locked_at``, its actor, and its audit event. The split is CLAUDE.md §3's
line: mechanism here, policy in the service.

The catalogue is validated at **import time**, so a malformed entry fails the boot
rather than the first request that touches it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from billing_platform.errors import ValidationFailedError
from billing_platform.tax import TAX_SYSTEMS


@dataclass(frozen=True, slots=True)
class Feature:
    """One entry in the catalogue.

    Tuples rather than the lists the doc sketches, so an entry is hashable and
    cannot be mutated by a caller that happens to hold a reference to it.
    """

    #: Features that must be on for this one to be on. Transitive.
    requires: tuple[str, ...] = ()
    #: The event that makes the flag **permanently enabled** (§4). ``None`` means
    #: freely reversible: the feature constrains future behaviour without
    #: reinterpreting figures already filed.
    locks_on: str | None = None
    #: Tax systems this feature is offerable under. Empty means every system —
    #: ``e_waybill`` on a UK VAT company is meaningless and must not be selectable.
    tax_systems: tuple[str, ...] = ()


#: docs/company-features.md §2. Keys are immutable once shipped: they are stored in
#: ``company_feature.feature_key`` and referenced by ``custom_field_definition``.
FEATURES: Final[dict[str, Feature]] = {
    # accounting scope
    "inventory": Feature(locks_on="stock_movement"),
    # Definition authoring and non-posting quantity preview only. Execution has
    # its own owner/consumer admission and cannot be enabled by this flag.
    "bom_definitions": Feature(requires=("inventory",)),
    "multi_currency": Feature(locks_on="foreign_currency_posting"),
    "cost_centres": Feature(locks_on="cost_allocation"),
    "budgets": Feature(),
    # inventory depth
    "multi_godown": Feature(requires=("inventory",), locks_on="godown_movement"),
    "batch_tracking": Feature(requires=("inventory",), locks_on="batch_recorded"),
    "expiry_tracking": Feature(requires=("batch_tracking",), locks_on="expiry_recorded"),
    "serial_tracking": Feature(requires=("inventory",), locks_on="serial_recorded"),
    # statutory — gated by the company's tax system
    "e_invoicing": Feature(tax_systems=("gst_in",)),
    "e_waybill": Feature(requires=("inventory",), tax_systems=("gst_in",)),
    "tds": Feature(locks_on="tds_deducted"),
    "tcs": Feature(locks_on="tcs_collected"),
    "reverse_charge": Feature(locks_on="rcm_posting"),
    # commercial
    "sales_promotions": Feature(locks_on="sales_promotion_posted"),
    "multi_price_levels": Feature(locks_on="customer_price_level_posting"),
    "credit_limits": Feature(),
    "recurring_billing": Feature(),
    "point_of_sale": Feature(),
    "approval_workflow": Feature(),
}


def get(feature_key: str) -> Feature:
    """The catalogue entry, or a 422.

    Unknown keys are rejected at the boundary rather than stored: a
    ``company_feature`` row naming a feature no code implements would gate a route
    that will never be built, and reads as "not enabled yet" forever.
    """
    try:
        return FEATURES[feature_key]
    except KeyError:
        raise ValidationFailedError(
            f"unknown feature: {feature_key!r}",
            fields={"feature_key": "not in the platform catalogue"},
        ) from None


def required_closure(feature_key: str) -> tuple[str, ...]:
    """``feature_key`` plus everything it transitively requires, dependencies first.

    Dependency order matters to the caller: rows are written in this order so that
    a partial failure never leaves a dependent enabled with its dependency off.
    """
    get(feature_key)
    ordered: list[str] = []

    def visit(key: str) -> None:
        if key in ordered:
            return
        for dependency in FEATURES[key].requires:
            visit(dependency)
        ordered.append(key)

    visit(feature_key)
    return tuple(ordered)


def dependents(feature_key: str) -> frozenset[str]:
    """Every feature that transitively requires ``feature_key``.

    Read on the disable path: turning ``inventory`` off while ``expiry_tracking``
    is on would leave a feature enabled whose dependency is gone, and the check
    that would have caught it lives two services away.
    """
    get(feature_key)
    found = {key for key in FEATURES if feature_key in required_closure(key) and key != feature_key}
    return frozenset(found)


def assert_offerable(feature_key: str, *, tax_system: str) -> None:
    """Reject a feature that means nothing under this company's tax system."""
    feature = get(feature_key)
    if feature.tax_systems and tax_system not in feature.tax_systems:
        allowed = ", ".join(sorted(feature.tax_systems))
        raise ValidationFailedError(
            f"{feature_key} is only available under: {allowed}",
            fields={"feature_key": f"not offerable under tax system {tax_system}"},
        )


def is_reversible(feature_key: str) -> bool:
    """Whether the feature can ever be turned off once dependent data exists.

    ``False`` is the common case: most features shape posted data, and §4's ratchet
    then makes them permanent.
    """
    return get(feature_key).locks_on is None


def feature_locked_by_event(event: str) -> str | None:
    """The feature an event locks, or ``None`` if the event locks nothing.

    The first dependent write reports what it did — ``"stock_movement"`` — and this
    resolves which flag that freezes, inside the same transaction. Events are unique
    across the catalogue (enforced at import), so the answer is never ambiguous.
    """
    for key, feature in FEATURES.items():
        if feature.locks_on == event:
            return key
    return None


def _validate_catalogue() -> None:
    """Boot check. Four ways an entry can be wrong, all of them silent at runtime.

    A cycle would recurse forever on the first enable; an unknown dependency would
    raise from inside a transaction; an unknown tax system would gate the feature
    off everywhere; and a dependency narrower than its dependent would make the
    dependent permanently un-enableable, which looks like a bug in the UI.
    """
    for key, feature in FEATURES.items():
        for dependency in feature.requires:
            if dependency not in FEATURES:
                raise ValueError(f"{key} requires unknown feature {dependency!r}")
        for system in feature.tax_systems:
            if system not in TAX_SYSTEMS:
                raise ValueError(f"{key} names unknown tax system {system!r}")

    for key in FEATURES:
        _assert_acyclic(key, ())

    for key, feature in FEATURES.items():
        if not feature.tax_systems:
            continue
        allowed = set(feature.tax_systems)
        for dependency in required_closure(key)[:-1]:
            gate = FEATURES[dependency].tax_systems
            if gate and not allowed <= set(gate):
                raise ValueError(
                    f"{key} is offerable under {sorted(allowed)} but its dependency "
                    f"{dependency!r} is not, so it could never be enabled"
                )

    events = [f.locks_on for f in FEATURES.values() if f.locks_on is not None]
    if len(set(events)) != len(events):
        raise ValueError("two features share a locks_on event; the lock target is ambiguous")


def _assert_acyclic(key: str, path: tuple[str, ...]) -> None:
    if key in path:
        raise ValueError(f"feature dependency cycle: {' -> '.join((*path, key))}")
    for dependency in FEATURES[key].requires:
        _assert_acyclic(dependency, (*path, key))


_validate_catalogue()
