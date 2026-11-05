from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from fastapi import FastAPI, Request
from redis.exceptions import RedisError

from identity.api.auth import Actor
from identity.models import (
    CustomFieldDefinition,
    Department,
    FieldPolicy,
    Membership,
    RoleAssignment,
)
from identity.services.step_up import (
    RedisProofStore,
    StepUpRequiredError,
    StepUpUnavailableError,
    enforce_request,
    require_company,
)


@pytest.mark.parametrize(
    "kind",
    [
        "path",
        "query",
        "body",
        "company_scope",
        "department_scope",
        "membership",
        "definition",
        "assignment",
        "policy",
    ],
)
async def test_all_company_scope_forms_require_a_proof(kind):
    company, reference = uuid7(), uuid7()
    current = Actor(uuid7(), uuid7())
    params, body, query = {}, {}, b""
    if kind == "path":
        params = {"company_id": str(company)}
    if kind == "query":
        query = f"company_id={company}".encode()
    if kind == "body":
        body = {"company_id": str(company)}
    if kind == "company_scope":
        body = {"scope_type": "company", "scope_id": str(company)}
    if kind == "department_scope":
        body = {"scope_type": "department", "scope_id": str(reference)}
    for name in ("membership", "definition", "assignment", "policy"):
        if kind == name:
            params = {name + "_id": str(reference)}

    def get(model, identifier):
        if model in {Membership, CustomFieldDefinition, Department}:
            return SimpleNamespace(company_id=company)
        if model in {RoleAssignment, FieldPolicy}:
            return SimpleNamespace(scope_type="company", scope_id=company)
        return None

    db = SimpleNamespace(get=AsyncMock(side_effect=get), scalar=AsyncMock(return_value=True))
    app = FastAPI()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/resource",
            "headers": [],
            "path_params": params,
            "query_string": query,
            "app": app,
        }
    )
    request._body = json.dumps(body).encode()
    with pytest.raises(StepUpRequiredError):
        await enforce_request(db, request, current)


async def test_invalid_scope_and_missing_references_fail_safely():
    app = FastAPI()
    current = Actor(uuid7(), uuid7())
    db = SimpleNamespace(get=AsyncMock(return_value=None), scalar=AsyncMock(return_value=None))
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/resource",
            "headers": [],
            "path_params": {"company_id": "malformed"},
            "query_string": b"",
            "app": app,
        }
    )
    with pytest.raises(ValidationFailedError):
        await enforce_request(db, request, current)
    request.scope["path_params"] = {
        "assignment_id": str(uuid7()),
        "membership_id": str(uuid7()),
        "definition_id": str(uuid7()),
        "policy_id": str(uuid7()),
    }
    await enforce_request(db, request, current)
    await require_company(db, request, current, uuid7())
    request.scope["path"] = "/v1/companies/invalid/step-up/challenge"
    await enforce_request(db, request, current)


async def test_redis_adapter_atomic_take_and_outage_mapping():
    store = RedisProofStore("redis://127.0.0.1:6379/15")
    real = store.client
    store.client = SimpleNamespace(
        set=AsyncMock(),
        get=AsyncMock(return_value="proof"),
        getdel=AsyncMock(return_value="challenge"),
        aclose=AsyncMock(),
    )
    try:
        await store.put("challenge", "value", 300)
        store.client.set.assert_awaited_once_with("challenge", "value", ex=300)
        assert await store.get("proof") == "proof"
        assert await store.take("challenge") == "challenge"
        store.client.getdel.assert_awaited_once_with("challenge")
        store.client.get.return_value = 42
        store.client.getdel.return_value = None
        assert await store.get("missing") is None
        assert await store.take("used") is None
        for name, args in (("put", ("key", "value", 300)), ("get", ("key",)), ("take", ("key",))):
            getattr(
                store.client, {"put": "set", "get": "get", "take": "getdel"}[name]
            ).side_effect = RedisError("offline")
            with pytest.raises(StepUpUnavailableError):
                await getattr(store, name)(*args)
        await store.close()
        store.client.aclose.assert_awaited_once()
    finally:
        await real.aclose()
