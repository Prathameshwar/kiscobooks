"""The feature catalogue and its graph.

The graph functions are the ones worth testing hard: they are read on the enable
and disable paths, and both of those paths are how a company ends up with a
feature on whose dependency is off — a state no route checks for afterwards
(docs/company-features.md §2).

The ratchet itself is tested in ``identity``: it needs a ``company_feature`` row's
``locked_at``, and that is policy, not catalogue.
"""

from __future__ import annotations

import pytest

from billing_platform.errors import ValidationFailedError
from billing_platform.features import (
    FEATURES,
    Feature,
    assert_offerable,
    dependents,
    feature_locked_by_event,
    get,
    is_reversible,
    required_closure,
)
from billing_platform.tax import TAX_SYSTEMS

# --- the catalogue as shipped -------------------------------------------------


def test_the_documented_features_are_the_ones_the_code_knows() -> None:
    """The doc's §2 listing is the authority. Drift means a client renders a menu
    entry for a feature no route honours, or hides one that works."""
    assert set(FEATURES) == {
        "inventory",
        "bom_definitions",
        "sales_promotions",
        "multi_currency",
        "multi_price_levels",
        "cost_centres",
        "budgets",
        "multi_godown",
        "batch_tracking",
        "expiry_tracking",
        "serial_tracking",
        "e_invoicing",
        "e_waybill",
        "tds",
        "tcs",
        "reverse_charge",
        "credit_limits",
        "recurring_billing",
        "approval_workflow",
        "point_of_sale",
    }


def test_a_feature_entry_cannot_be_mutated() -> None:
    """Frozen because the catalogue is process-global: one caller appending to a
    ``requires`` list would change the dependency graph for every company."""
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError is not public
        FEATURES["inventory"].locks_on = "anything"  # type: ignore[misc]


def test_every_dependency_names_a_real_feature() -> None:
    for key, feature in FEATURES.items():
        for dependency in feature.requires:
            assert dependency in FEATURES, f"{key} requires unknown {dependency}"


def test_every_tax_gate_names_a_real_tax_system() -> None:
    for key, feature in FEATURES.items():
        for system in feature.tax_systems:
            assert system in TAX_SYSTEMS, f"{key} names unknown tax system {system}"


def test_no_two_features_share_a_lock_event() -> None:
    """``feature_locked_by_event`` must have one answer. A shared event would lock
    an arbitrary one of the two, and the other would stay reversible."""
    events = [f.locks_on for f in FEATURES.values() if f.locks_on is not None]
    assert len(set(events)) == len(events)


# --- lookup -------------------------------------------------------------------


def test_an_unknown_feature_is_rejected() -> None:
    with pytest.raises(ValidationFailedError):
        get("inventry")


def test_a_known_feature_returns_its_entry() -> None:
    assert get("expiry_tracking").requires == ("batch_tracking",)


# --- dependency resolution ----------------------------------------------------


def test_a_closure_is_dependencies_first() -> None:
    """Order is load-bearing: rows are written in this order so a partial failure
    never leaves a dependent enabled with its dependency off."""
    assert required_closure("expiry_tracking") == ("inventory", "batch_tracking", "expiry_tracking")


def test_a_feature_with_no_dependencies_closes_over_itself() -> None:
    assert required_closure("budgets") == ("budgets",)


def test_a_closure_over_an_unknown_feature_is_rejected() -> None:
    with pytest.raises(ValidationFailedError):
        required_closure("nope")


def test_dependents_are_transitive() -> None:
    """`expiry_tracking` requires `batch_tracking` requires `inventory`, so turning
    `inventory` off has to account for `expiry_tracking` two levels away."""
    assert dependents("inventory") == {
        "bom_definitions",
        "multi_godown",
        "batch_tracking",
        "expiry_tracking",
        "serial_tracking",
        "e_waybill",
    }


def test_dependents_of_a_leaf_are_empty() -> None:
    assert dependents("expiry_tracking") == frozenset()


def test_a_feature_is_not_its_own_dependent() -> None:
    """Otherwise every disable would report itself as a blocker and nothing could
    ever be turned off."""
    for key in FEATURES:
        assert key not in dependents(key)


def test_the_graph_has_no_cycles() -> None:
    """Asserted as well as enforced at import: the import check is what fails the
    boot, and this is what says why."""
    for key in FEATURES:
        assert key not in FEATURES[key].requires
        assert key not in dependents(key)


# --- tax gating ---------------------------------------------------------------


def test_an_ungated_feature_is_offerable_everywhere() -> None:
    for system in TAX_SYSTEMS:
        assert_offerable("inventory", tax_system=system)


def test_a_gated_feature_is_offerable_under_its_own_system() -> None:
    assert_offerable("e_waybill", tax_system="gst_in")


def test_a_gated_feature_is_refused_under_another_system() -> None:
    """`e_waybill` on a UK VAT company is meaningless, and a company that enabled
    it would gate its own routes on a document type that does not exist there."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_offerable("e_waybill", tax_system="vat_gb")

    assert "gst_in" in str(raised.value)


def test_a_gated_feature_never_depends_on_a_more_narrowly_gated_one() -> None:
    """Enforced at import; asserted here because the failure is invisible — the
    feature simply can never be switched on, which reads as a UI bug."""
    for key, feature in FEATURES.items():
        if not feature.tax_systems:
            continue
        for dependency in required_closure(key)[:-1]:
            gate = FEATURES[dependency].tax_systems
            assert not gate or set(feature.tax_systems) <= set(gate), f"{key} -> {dependency}"


# --- the lock event -----------------------------------------------------------


def test_a_feature_that_shapes_posted_data_is_irreversible() -> None:
    """§4's table, asserted. Each of these reinterprets figures already filed."""
    for key in (
        "inventory",
        "multi_currency",
        "batch_tracking",
        "expiry_tracking",
        "cost_centres",
        "tds",
        "tcs",
        "reverse_charge",
    ):
        assert not is_reversible(key), f"{key} must carry a locks_on event"


def test_a_feature_that_only_constrains_future_behaviour_is_reversible() -> None:
    for key in ("budgets", "credit_limits", "approval_workflow", "point_of_sale"):
        assert is_reversible(key)


def test_an_event_resolves_to_the_feature_it_locks() -> None:
    assert feature_locked_by_event("stock_movement") == "inventory"
    assert feature_locked_by_event("foreign_currency_posting") == "multi_currency"


def test_an_event_that_locks_nothing_resolves_to_none() -> None:
    """A write reporting an event no feature watches is ordinary, not an error:
    most writes lock nothing."""
    assert feature_locked_by_event("invoice_posted") is None


# --- the catalogue rejects a malformed entry at import ------------------------


def test_a_cycle_would_fail_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """The import-time check, exercised against a deliberately broken catalogue.

    Patched rather than reimplemented: a copy of the cycle walk in the test would
    pass while the real one was broken.
    """
    from billing_platform import features as module

    monkeypatch.setitem(module.FEATURES, "a", Feature(requires=("b",)))
    monkeypatch.setitem(module.FEATURES, "b", Feature(requires=("a",)))

    with pytest.raises(ValueError, match="cycle"):
        module._validate_catalogue()


def test_an_unknown_dependency_would_fail_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    from billing_platform import features as module

    monkeypatch.setitem(module.FEATURES, "a", Feature(requires=("ghost",)))

    with pytest.raises(ValueError, match="unknown feature"):
        module._validate_catalogue()


def test_an_unknown_tax_gate_would_fail_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    from billing_platform import features as module

    monkeypatch.setitem(module.FEATURES, "a", Feature(tax_systems=("vat_zz",)))

    with pytest.raises(ValueError, match="unknown tax system"):
        module._validate_catalogue()


def test_a_dependency_narrower_than_its_dependent_would_fail_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from billing_platform import features as module

    monkeypatch.setitem(module.FEATURES, "narrow", Feature(tax_systems=("gst_in",)))
    monkeypatch.setitem(
        module.FEATURES, "wide", Feature(requires=("narrow",), tax_systems=("vat_gb",))
    )

    with pytest.raises(ValueError, match="could never be enabled"):
        module._validate_catalogue()


def test_a_duplicated_lock_event_would_fail_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    from billing_platform import features as module

    monkeypatch.setitem(module.FEATURES, "a", Feature(locks_on="stock_movement"))

    with pytest.raises(ValueError, match="ambiguous"):
        module._validate_catalogue()


def test_multiple_price_levels_lock_on_their_own_posting_event() -> None:
    assert FEATURES["multi_price_levels"].locks_on == "customer_price_level_posting"
    assert FEATURES["multi_price_levels"].requires == ()


def test_bom_definitions_are_inventory_dependent_and_do_not_claim_execution() -> None:
    assert FEATURES["bom_definitions"].requires == ("inventory",)
    assert FEATURES["bom_definitions"].locks_on is None
