from __future__ import annotations

import uuid

import pytest
from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import ConflictError, ValidationFailedError

from notification.domain.retry import backoff_seconds
from notification.domain.routing import RouteCandidate, select_route
from notification.domain.state import require_transition, should_advance
from notification.domain.template import render


def test_delivery_state_never_regresses() -> None:
    assert should_advance("accepted", "delivered")
    assert not should_advance("delivered", "accepted")
    with pytest.raises(ConflictError):
        require_transition("read", "failed")


def test_template_renderer_allows_names_only() -> None:
    assert render("Hello {{ name }}", {"name": "Ada"}) == "Hello Ada"
    with pytest.raises(ValidationFailedError):
        render("{{ user.name }}", {"user": {"name": "Ada"}})


def test_routing_prefers_company_event_and_is_deterministic() -> None:
    company, stable = uuid.uuid4(), uuid.uuid4()
    tenant = RouteCandidate(uuid.uuid4(), SCOPE_ALL, "invoice.posted", "transactional", 1, 100)
    exact = RouteCandidate(uuid.uuid4(), company, "invoice.posted", "transactional", 1, 100)
    assert (
        select_route(
            [tenant, exact],
            company_id=company,
            event_key="invoice.posted",
            category="transactional",
            stable_key=stable,
        )
        == exact
    )


def test_invalid_scan_retry_state_and_route_boundaries() -> None:
    from billing_platform.errors import NotFoundError

    from notification.domain.attachments import assert_scan_status, assert_sendable

    assert_scan_status("clean")
    assert_sendable("clean")
    for operation, value in ((assert_scan_status, "unknown"), (assert_sendable, "infected")):
        with pytest.raises(ValidationFailedError):
            operation(value)
    with pytest.raises(ValueError):
        backoff_seconds(0, initial=1, maximum=2, stable_key=uuid.uuid4())
    with pytest.raises(ValidationFailedError):
        should_advance("unknown", "delivered")
    require_transition("accepted", "delivered")
    company, stable = uuid.uuid4(), uuid.uuid4()
    category = RouteCandidate(uuid.uuid4(), company, "*", "transactional", 1, 1)
    default = RouteCandidate(uuid.uuid4(), SCOPE_ALL, "*", "transactional", 1, 1)
    assert (
        select_route(
            [default, category],
            company_id=company,
            event_key="event",
            category="transactional",
            stable_key=stable,
        )
        == category
    )
    with pytest.raises(NotFoundError):
        select_route(
            [RouteCandidate(uuid.uuid4(), uuid.uuid4(), "other", "transactional", 1, 1)],
            company_id=company,
            event_key="event",
            category="transactional",
            stable_key=stable,
        )
    with pytest.raises(ValidationFailedError):
        select_route(
            [RouteCandidate(uuid.uuid4(), company, "event", "transactional", 1, 0)],
            company_id=company,
            event_key="event",
            category="transactional",
            stable_key=stable,
        )
    assert backoff_seconds(3, initial=10, maximum=100, stable_key=stable) == backoff_seconds(
        3, initial=10, maximum=100, stable_key=stable
    )
