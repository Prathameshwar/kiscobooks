"""Send-time gate decisions (docs/notification.md §5), as pure logic.

The consumer loads rows; this module turns them into a decision per channel, so the
compliance-critical ordering — endpoint, preference, consent, suppression — is tested
with no database and no broker. Security messages bypass preference/consent/suppression
by policy (``domain/policy``); every other category honours all three.

Framework- and ORM-free (CLAUDE.md §4): the consumer extracts plain values and
``SuppressionRule`` records from the ORM rows and passes them in.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

from notification.domain.policy import policy_for

SEND = "send"
SUPPRESSED = "suppressed"
SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ChannelDecision:
    decision: str  # SEND | SUPPRESSED | SKIPPED
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SuppressionRule:
    """One suppression row reduced to what resolution reads."""

    reason: str
    scope_type: str  # "global" | "event" | "category"
    scope_key: str
    valid_from: dt.datetime
    valid_to: dt.datetime | None


def consent_is_granted(
    state: str | None, expires_at: dt.datetime | None, *, now: dt.datetime
) -> bool:
    """Consent counts only while explicitly granted and unexpired."""
    return state == "granted" and (expires_at is None or now < expires_at)


def active_suppression_reason(
    rules: Iterable[SuppressionRule], *, now: dt.datetime, event_key: str, category: str
) -> str | None:
    """The reason of the first in-window suppression whose scope matches, or ``None``.

    Rows are pre-filtered by the caller on ``(channel, destination_hmac)`` via the index;
    this applies the validity window and scope match.
    """
    for rule in rules:
        in_window = rule.valid_from <= now and (rule.valid_to is None or now <= rule.valid_to)
        if not in_window:
            continue
        if (
            rule.scope_type == "global"
            or (rule.scope_type == "event" and rule.scope_key == event_key)
            or (rule.scope_type == "category" and rule.scope_key == category)
        ):
            return rule.reason
    return None


def decide(
    *,
    category: str,
    has_endpoint: bool,
    preference_enabled: bool | None,
    consent_granted: bool,
    suppression_reason: str | None,
) -> ChannelDecision:
    """The §5 gates in order. ``preference_enabled=None`` means no explicit preference."""
    if not has_endpoint:
        return ChannelDecision(SKIPPED, "no_active_endpoint")

    pol = policy_for(category)
    if not pol.overridable:
        # Security: not suppressible, not preference-disabled, no consent gate.
        return ChannelDecision(SEND)

    enabled = pol.default_opt_in if preference_enabled is None else preference_enabled
    if not enabled:
        return ChannelDecision(SKIPPED, "preference_disabled")
    if pol.consent_required and not consent_granted:
        return ChannelDecision(SKIPPED, "consent_not_granted")
    if suppression_reason is not None:
        return ChannelDecision(SUPPRESSED, suppression_reason)
    return ChannelDecision(SEND)
