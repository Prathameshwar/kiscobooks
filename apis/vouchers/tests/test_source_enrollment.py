"""Discovery verifies complete signed pages before exposing any dynamic scopes."""

import secrets

import httpx
import pytest
from billing_platform.errors import PlatformError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import (
    SnapshotCredential,
    authenticate_snapshot,
    response_headers,
)
from pydantic import SecretStr

from vouchers.schemas.owners import Owner
from vouchers.tasks.source_worker import discover


@pytest.mark.parametrize(
    "fault", [None, "tampered", "duplicate", "cursor", "shape", "oversize", "redirect"]
)
async def test_verified_complete_enrollment_or_no_scope(fault):
    secret, key = secrets.token_hex(32), "vouchers.enrollment.test"
    owner = Owner(
        owner="identity",
        origin="http://127.0.0.1",
        key_id=key,
        secret=SecretStr(secret),
        allow_enrolled_companies=True,
    )
    credential = SnapshotCredential(secret=SecretStr(secret), allow_enrolled_companies=True)
    scopes = [{"tenant_id": str(uuid7()), "company_id": str(uuid7())} for _ in range(2)]
    calls = 0

    async def identity(request):
        nonlocal calls
        calls += 1
        checked, framed, key_id = authenticate_snapshot(
            {key: credential},
            owner="identity",
            headers=request.headers,
            method=request.method,
            path=request.url.path,
            query="",
            body=request.content,
        )
        assert request.url.path == "/internal/v1/voucher-enrollments" and request.method == "POST"
        if fault == "redirect":
            return httpx.Response(307, headers={"Location": "http://127.0.0.1/elsewhere"})
        selected = [scopes[min(calls - 1, 1)]]
        if fault == "duplicate":
            selected *= 2
        values = {
            "scopes": selected,
            "next_cursor": "next-page" if calls == 1 or fault == "cursor" else None,
        }
        if fault == "shape":
            values["unexpected"] = True
        raw = canonical_json(values)
        headers = response_headers(
            checked, owner="identity", key_id=key_id, request_bytes=framed, body=raw
        )
        if fault == "tampered":
            raw += b" "
        if fault == "oversize":
            raw = b" " * 65537
        return httpx.Response(200, content=raw, headers=headers)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(identity), follow_redirects=False
    ) as client:
        if fault:
            with pytest.raises((PlatformError, ValueError, httpx.HTTPError)):
                await discover(client, owner)
        else:
            result = await discover(client, owner)
            assert [str(scope.company_id) for scope in result] == [
                scope["company_id"] for scope in scopes
            ]
            assert calls == 2
