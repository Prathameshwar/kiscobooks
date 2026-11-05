"""Send-time gate decisions and category policy, tested with no DB (docs/notification.md §5)."""

from __future__ import annotations

import datetime as dt

import pytest
from billing_platform.errors import ValidationFailedError

from notification.domain.planning import (
    SEND,
    SKIPPED,
    SUPPRESSED,
    SuppressionRule,
    active_suppression_reason,
    consent_is_granted,
    decide,
)
from notification.domain.policy import policy_for

_NOW = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)


def test_category_policies() -> None:
    assert policy_for("security").overridable is False
    assert policy_for("marketing").consent_required is True
    assert policy_for("marketing").default_opt_in is False
    assert policy_for("transactional").default_opt_in is True
    with pytest.raises(ValidationFailedError):
        policy_for("promo")


def test_no_endpoint_is_skipped() -> None:
    d = decide(
        category="transactional",
        has_endpoint=False,
        preference_enabled=None,
        consent_granted=False,
        suppression_reason=None,
    )
    assert d.decision == SKIPPED and d.reason == "no_active_endpoint"


def test_security_bypasses_preference_and_suppression() -> None:
    d = decide(
        category="security",
        has_endpoint=True,
        preference_enabled=False,
        consent_granted=False,
        suppression_reason="bounced",
    )
    assert d.decision == SEND


def test_transactional_default_on_but_preference_off_skips() -> None:
    assert (
        decide(
            category="transactional",
            has_endpoint=True,
            preference_enabled=None,
            consent_granted=False,
            suppression_reason=None,
        ).decision
        == SEND
    )
    off = decide(
        category="transactional",
        has_endpoint=True,
        preference_enabled=False,
        consent_granted=False,
        suppression_reason=None,
    )
    assert off.decision == SKIPPED and off.reason == "preference_disabled"


def test_marketing_requires_consent() -> None:
    no_consent = decide(
        category="marketing",
        has_endpoint=True,
        preference_enabled=True,
        consent_granted=False,
        suppression_reason=None,
    )
    assert no_consent.decision == SKIPPED and no_consent.reason == "consent_not_granted"
    ok = decide(
        category="marketing",
        has_endpoint=True,
        preference_enabled=True,
        consent_granted=True,
        suppression_reason=None,
    )
    assert ok.decision == SEND


def test_active_suppression_suppresses() -> None:
    d = decide(
        category="transactional",
        has_endpoint=True,
        preference_enabled=True,
        consent_granted=True,
        suppression_reason="hard_bounce",
    )
    assert d.decision == SUPPRESSED and d.reason == "hard_bounce"


def test_consent_expiry() -> None:
    assert consent_is_granted("granted", None, now=_NOW)
    assert not consent_is_granted("granted", dt.datetime(2026, 1, 1, tzinfo=dt.UTC), now=_NOW)
    assert not consent_is_granted("denied", None, now=_NOW)


def _reason(
    rule: SuppressionRule, *, event_key: str = "invoice.posted", category: str = "operational"
) -> str | None:
    return active_suppression_reason([rule], now=_NOW, event_key=event_key, category=category)


def test_suppression_scope_and_window() -> None:
    start = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    assert _reason(SuppressionRule("complaint", "global", "", start, None)) == "complaint"

    event = SuppressionRule("opt_out", "event", "invoice.posted", start, None)
    assert _reason(event) == "opt_out"
    assert _reason(event, event_key="other.event") is None

    expired = SuppressionRule("old", "global", "", start, dt.datetime(2025, 6, 1, tzinfo=dt.UTC))
    assert _reason(expired) is None
