"""Audit cursors stay small and never reuse another query or authority."""

import datetime as dt
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.errors import ValidationFailedError
from billing_platform.gateway import Actor, AuditReadScope, ReadPolicyContext
from pydantic import SecretStr
from starlette.datastructures import QueryParams

from audit.api.listing import cursor_codec


def request(query: str = "limit=1") -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(cursor_signing_secret=SecretStr("cursor-test-key-" * 3))
            )
        ),
        query_params=QueryParams(query),
    )


def broad_actor() -> Actor:
    company = uuid.uuid4()
    return Actor(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        grants=(
            Grant(
                frozenset({"audit.read", "activity.read"})
                | frozenset(f"catalogue_resource_{i:03}.read" for i in range(200)),
                Scope("tenant"),
                dt.date(2026, 1, 1),
            ),
        ),
        field_policies=tuple(
            ReadPolicyContext(
                entity_type="catalog.item",
                field_key=f"attribute_{i:03}",
                effect="deny",
                scope_type="company",
                scope_id=company,
            )
            for i in range(20)
        ),
    )


def test_broad_administrator_cursor_is_bounded_and_round_trips() -> None:
    actor = broad_actor()
    codec = cursor_codec(request(), "audit-events", actor)
    values = {"occurred_at": "2026-10-29T00:00:00+00:00", "id": str(uuid.uuid4())}
    token = codec.encode(values)
    assert len(token) < 1024
    assert codec.decode(token) == values


@pytest.mark.parametrize(
    "change",
    ["tenant", "user", "grants", "policies", "impersonator", "audit_scope"],
)
def test_cursor_rejects_changed_actor_binding(change: str) -> None:
    actor = broad_actor()
    token = cursor_codec(request(), "audit-events", actor).encode({"id": str(uuid.uuid4())})
    if change == "tenant":
        other = replace(actor, tenant_id=uuid.uuid4())
    elif change == "user":
        other = replace(actor, user_id=uuid.uuid4())
    elif change == "grants":
        other = replace(actor, grants=())
    elif change == "policies":
        other = replace(actor, field_policies=())
    elif change == "impersonator":
        other = replace(actor, real_user_id=uuid.uuid4(), impersonation_id=uuid.uuid4())
    else:
        other = replace(actor, audit_scope=AuditReadScope(company_id=uuid.uuid4()))
    with pytest.raises(ValidationFailedError, match="invalid cursor"):
        cursor_codec(request(), "audit-events", other).decode(token)


@pytest.mark.parametrize("query", ["limit=2", "limit=1&category=admin", "limit=1&sort=sequence"])
def test_cursor_rejects_changed_query(query: str) -> None:
    actor = broad_actor()
    token = cursor_codec(request(), "audit-events", actor).encode({"id": str(uuid.uuid4())})
    with pytest.raises(ValidationFailedError, match="invalid cursor"):
        cursor_codec(request(query), "audit-events", actor).decode(token)


def test_cursor_ignores_cursor_parameter_and_binds_the_surface() -> None:
    actor = broad_actor()
    token = cursor_codec(request(), "audit-events", actor).encode({"id": str(uuid.uuid4())})
    assert cursor_codec(request("cursor=ignored&limit=1"), "audit-events", actor).decode(token)
    with pytest.raises(ValidationFailedError, match="invalid cursor"):
        cursor_codec(request(), "activity", actor).decode(token)
