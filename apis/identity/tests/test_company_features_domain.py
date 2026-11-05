"""Feature transitions over actual rows — enable, disable, and the ratchet.

No database, no session, no app (CLAUDE.md §7). The catalogue's own integrity is
tested in `libs/platform/tests/test_features.py`; what is tested here is the policy
laid over a company's current rows.

The ratchet block is the one that matters. ``locked_at`` is set by the first
dependent write and never cleared, and there is deliberately no actor parameter
anywhere in the module — the last test asserts that structurally, because it is the
only way to test "not even platform admin" without enumerating every role.
"""

from __future__ import annotations

import datetime as dt
import inspect

import pytest
from billing_platform.errors import (
    FeatureNotEnabledError,
    ImmutableFieldError,
    ValidationFailedError,
)

from identity.domain import (
    FeatureState,
    assert_disable_allowed,
    assert_enabled,
    plan_enable,
    plan_lock,
    resolve_enabled,
)

LOCKED_AT = dt.datetime(2026, 5, 2, 6, 15, tzinfo=dt.UTC)

ON = FeatureState(is_enabled=True)
OFF = FeatureState(is_enabled=False)


def locked(reason: str = "stock_movement") -> FeatureState:
    """An enabled feature the ratchet has closed. Enabled by definition: a lock
    records that dependent data exists, which could only happen while it was on."""
    return FeatureState(is_enabled=True, locked_at=LOCKED_AT, lock_reason=reason)


# --- reading the current state -------------------------------------------------


def test_no_rows_means_nothing_is_enabled() -> None:
    """docs/company-features.md §3. A new company has no rows, so "absent" has to
    mean disabled — never "unknown, so allow"."""
    assert resolve_enabled({}) == frozenset()


def test_a_disabled_row_is_not_enabled() -> None:
    """A row that exists and says ``False`` reads the same as no row at all. It exists
    only to carry ``disabled_at`` and ``disabled_by``."""
    assert resolve_enabled({"inventory": OFF}) == frozenset()


def test_only_the_enabled_rows_are_returned() -> None:
    rows = {"inventory": ON, "tds": OFF, "budgets": ON}

    assert resolve_enabled(rows) == {"inventory", "budgets"}


def test_a_locked_feature_is_enabled() -> None:
    assert resolve_enabled({"inventory": locked()}) == {"inventory"}


# --- the write-path gate ------------------------------------------------------


def test_the_gate_passes_for_an_enabled_feature() -> None:
    assert_enabled("inventory", rows={"inventory": ON})


def test_the_gate_refuses_an_absent_feature_with_a_409() -> None:
    """409, not 403. 403 means *you* may not, which is audit signal worth
    investigating; 409 means *nobody here can, yet*, which is ordinary client
    behaviour and would otherwise flood it (docs/company-features.md §5)."""
    with pytest.raises(FeatureNotEnabledError) as raised:
        assert_enabled("inventory", rows={})

    assert raised.value.status_code == 409
    assert raised.value.extra["feature"] == "inventory"


def test_the_gate_refuses_a_disabled_feature() -> None:
    with pytest.raises(FeatureNotEnabledError):
        assert_enabled("inventory", rows={"inventory": OFF})


def test_the_gate_rejects_a_feature_outside_the_catalogue_with_a_422() -> None:
    """Not a 409: an unknown key is a caller bug, and answering "not enabled yet"
    would have someone waiting for a flag that will never exist."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_enabled("teleportation", rows={})

    assert raised.value.status_code == 422


# --- enabling -----------------------------------------------------------------


def test_enabling_a_standalone_feature_plans_one_row() -> None:
    assert plan_enable("budgets", rows={}, tax_system="gst_in") == ("budgets",)


def test_enabling_plans_dependencies_first() -> None:
    """**The order is load-bearing.** Written this way, a partial failure leaves a
    dependency on without its dependent, which is harmless — never the reverse, which
    would leave a feature enabled that nothing downstream re-checks."""
    assert plan_enable("expiry_tracking", rows={}, tax_system="gst_in") == (
        "inventory",
        "batch_tracking",
        "expiry_tracking",
    )


def test_enabling_skips_the_dependencies_already_on() -> None:
    rows = {"inventory": ON, "batch_tracking": ON}

    assert plan_enable("expiry_tracking", rows=rows, tax_system="gst_in") == ("expiry_tracking",)


def test_enabling_something_already_on_plans_nothing() -> None:
    """An empty plan, not an error: re-enabling is the idempotent case, and a client
    retrying a request whose response it lost must not get a 409."""
    rows = {"inventory": ON, "batch_tracking": ON, "expiry_tracking": ON}

    assert plan_enable("expiry_tracking", rows=rows, tax_system="gst_in") == ()


def test_re_enabling_a_disabled_feature_plans_the_row_again() -> None:
    """Disable then enable is allowed for a reversible feature; the same row is
    rewritten rather than a second one added — that is what
    ``uq_company_feature_company_id_feature_key`` guarantees."""
    assert plan_enable("budgets", rows={"budgets": OFF}, tax_system="gst_in") == ("budgets",)


def test_a_feature_outside_the_tax_system_is_refused() -> None:
    """``e_invoicing`` under UK VAT is not a preference someone might want — there is
    no such filing, so the row must never be written."""
    with pytest.raises(ValidationFailedError) as raised:
        plan_enable("e_invoicing", rows={}, tax_system="vat_gb")

    assert raised.value.status_code == 422
    assert "gst_in" in str(raised.value)


def test_the_tax_gate_is_checked_on_the_whole_closure() -> None:
    """Not just on the requested feature. A dependency gated more narrowly than its
    dependent would otherwise be written by an enable that then failed — and the
    catalogue's boot check forbids that shape precisely so this stays true."""
    with pytest.raises(ValidationFailedError):
        plan_enable("e_waybill", rows={}, tax_system="vat_ae")


def test_a_gated_feature_is_planned_under_its_own_tax_system() -> None:
    assert plan_enable("e_waybill", rows={}, tax_system="gst_in") == ("inventory", "e_waybill")


def test_enabling_an_unknown_feature_is_a_422() -> None:
    with pytest.raises(ValidationFailedError):
        plan_enable("teleportation", rows={}, tax_system="gst_in")


# --- disabling ----------------------------------------------------------------


def test_disabling_a_reversible_feature_with_no_dependents_is_allowed() -> None:
    assert_disable_allowed("budgets", rows={"budgets": ON})


def test_disabling_a_feature_that_was_never_enabled_is_allowed() -> None:
    """A no-op disable, which is what a client sends when it has lost track. There is
    nothing to refuse."""
    assert_disable_allowed("inventory", rows={})


def test_disabling_is_refused_while_a_dependent_is_enabled() -> None:
    """Turning ``inventory`` off under ``batch_tracking`` would leave a feature on
    whose dependency is gone, and the code that would notice is two services away."""
    rows = {"inventory": ON, "batch_tracking": ON}

    with pytest.raises(ValidationFailedError) as raised:
        assert_disable_allowed("inventory", rows=rows)

    assert raised.value.status_code == 422
    assert "batch_tracking" in str(raised.value)


def test_the_refusal_names_every_blocking_dependent() -> None:
    """All of them at once, sorted. One at a time turns a single cleanup into four
    round trips, each of which looks like a new problem."""
    rows = {"inventory": ON, "batch_tracking": ON, "serial_tracking": ON, "multi_godown": OFF}

    with pytest.raises(ValidationFailedError) as raised:
        assert_disable_allowed("inventory", rows=rows)

    message = str(raised.value)
    assert "batch_tracking, serial_tracking" in message
    assert "multi_godown" not in message, "a disabled dependent blocks nothing"


def test_a_transitive_dependent_blocks_a_disable() -> None:
    """``expiry_tracking`` requires ``batch_tracking`` requires ``inventory``. The
    check is transitive or the middle row could be removed to free the bottom one."""
    rows = {"inventory": ON, "batch_tracking": ON, "expiry_tracking": ON}

    with pytest.raises(ValidationFailedError) as raised:
        assert_disable_allowed("inventory", rows=rows)

    assert "expiry_tracking" in str(raised.value)


# --- the ratchet --------------------------------------------------------------


def test_a_locked_feature_cannot_be_disabled() -> None:
    """**Invariant 16's shape applied to features.** Enable multi-currency, post a USD
    invoice against an INR base, disable multi-currency — and nobody can say what that
    invoice is worth or which rate reproduces the figure already filed."""
    rows = {"multi_currency": locked("foreign_currency_posting")}

    with pytest.raises(ImmutableFieldError) as raised:
        assert_disable_allowed("multi_currency", rows=rows)

    assert raised.value.status_code == 422
    assert raised.value.extra["fields"] == {"multi_currency": "permanently enabled"}


def test_the_refusal_quotes_the_lock_reason() -> None:
    """The reason is the only thing that tells someone *why* it is permanent — "a
    stock movement was posted" is actionable in a way "locked" is not."""
    with pytest.raises(ImmutableFieldError) as raised:
        assert_disable_allowed("inventory", rows={"inventory": locked("stock_movement")})

    assert "stock_movement" in str(raised.value)


def test_the_lock_is_checked_before_the_dependents() -> None:
    """Order matters: the lock is the answer that can never change, and telling
    someone to turn off three dependents before refusing them anyway would be worse
    than useless."""
    rows = {"inventory": locked(), "batch_tracking": ON, "serial_tracking": ON}

    with pytest.raises(ImmutableFieldError):
        assert_disable_allowed("inventory", rows=rows)


def test_a_lock_with_no_reason_still_refuses() -> None:
    """Defensive: a row written before ``lock_reason`` existed, or by a caller that
    omitted it. A missing explanation must not become permission."""
    rows = {"inventory": FeatureState(is_enabled=True, locked_at=LOCKED_AT)}

    with pytest.raises(ImmutableFieldError) as raised:
        assert_disable_allowed("inventory", rows=rows)

    assert "dependent data exists" in str(raised.value)


# --- planning a lock ----------------------------------------------------------


def test_an_ordinary_write_locks_nothing() -> None:
    """The common case by a wide margin. ``None`` is the answer, not an error — most
    writes in the platform match no lock event at all."""
    assert plan_lock("invoice_posted", rows={"inventory": ON}) is None


def test_the_first_dependent_write_plans_the_lock() -> None:
    assert plan_lock("stock_movement", rows={"inventory": ON}) == ("inventory", "stock_movement")


def test_a_second_dependent_write_plans_nothing() -> None:
    """``locked_at`` records the **first** dependent write. Returning the pair again
    would have the caller overwrite it and lose that — and the caller's write has to
    stay idempotent under redelivery (invariant 10)."""
    assert plan_lock("stock_movement", rows={"inventory": locked()}) is None


def test_each_lock_event_resolves_to_its_own_feature() -> None:
    rows = {"tds": ON, "tcs": ON, "reverse_charge": ON, "cost_centres": ON}

    assert plan_lock("tds_deducted", rows=rows) == ("tds", "tds_deducted")
    assert plan_lock("tcs_collected", rows=rows) == ("tcs", "tcs_collected")
    assert plan_lock("rcm_posting", rows=rows) == ("reverse_charge", "rcm_posting")
    assert plan_lock("cost_allocation", rows=rows) == ("cost_centres", "cost_allocation")


def test_a_dependent_write_against_a_disabled_feature_raises() -> None:
    """**It does not lock it.** Locking would ratify a write that should never have
    been accepted, and make the flag permanent on the strength of the bug. The 409
    surfaces the accepted write instead of burying it."""
    with pytest.raises(FeatureNotEnabledError):
        plan_lock("stock_movement", rows={"inventory": OFF})


def test_a_dependent_write_against_an_absent_feature_raises() -> None:
    with pytest.raises(FeatureNotEnabledError):
        plan_lock("stock_movement", rows={})


# --- not a permission ---------------------------------------------------------


def test_no_transition_takes_an_actor_or_an_override() -> None:
    """**"For every actor including platform admin", asserted structurally.**

    If someone adds ``actor``, ``force`` or ``is_platform_admin`` to one of these
    signatures, the ratchet has become a permission and this fails.
    """
    forbidden = {"actor", "actor_user_id", "user", "force", "override", "is_platform_admin"}

    for function in (
        resolve_enabled,
        assert_enabled,
        plan_enable,
        assert_disable_allowed,
        plan_lock,
    ):
        parameters = set(inspect.signature(function).parameters)
        assert not parameters & forbidden, f"{function.__name__} gained an override parameter"


def test_a_feature_state_cannot_be_mutated_by_a_rule() -> None:
    """Frozen, so deciding what to do with a row cannot accidentally change it. The
    plan functions return what to write; they never write."""
    state = ON

    with pytest.raises(AttributeError):
        state.is_enabled = False  # type: ignore[misc]
