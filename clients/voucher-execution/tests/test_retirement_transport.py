import datetime as dt
import secrets

import httpx
import pytest
from billing_platform.db.types import utcnow
from billing_platform.errors import PlatformError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.service_auth import service_request_bytes, service_response_bytes
from pydantic import ValidationError

from voucher_execution.retirement_transport import (
    RetirementClient,
    RetirementConnection,
    RetirementUnavailableError,
    bounded_body,
    response_body,
    signing_headers,
    verified,
)
from voucher_execution.stock_retirement import ActorProof, RetirementEvidence, RetirementRequest


def test_service_proof_is_bound_to_owner_operation_direction_and_request():
    secret = secrets.token_bytes(32)
    headers = signing_headers(secret, "accounting", "inspect", b"first-request")
    verified(secret, "accounting", "inspect", b"first-request", headers)
    for owner, action, framed, response in (
        ("vouchers", "inspect", b"first-request", False),
        ("accounting", "acquire", b"first-request", False),
        ("accounting", "inspect", b"other-request", False),
        ("accounting", "inspect", b"first-request", True),
    ):
        with pytest.raises(PlatformError):
            verified(secret, owner, action, framed, headers, response=response)
    with pytest.raises(PlatformError):
        verified(secrets.token_bytes(32), "accounting", "inspect", b"first-request", headers)


def test_response_signature_cannot_be_replayed_against_another_request():
    secret = secrets.token_bytes(32)
    raw, headers = response_body(secret, "accounting", "inspect", b"first", {"result": "CLEARED"})
    assert headers["Cache-Control"] == "no-store"
    verified(
        secret,
        "accounting",
        "inspect",
        service_response_bytes(request_bytes=b"first", response_body=raw),
        headers,
        response=True,
    )
    with pytest.raises(PlatformError):
        verified(
            secret,
            "accounting",
            "inspect",
            service_response_bytes(request_bytes=b"second", response_body=raw),
            headers,
            response=True,
        )


@pytest.mark.asyncio
async def test_streaming_request_bound_is_enforced():
    async def chunks(extra):
        yield b"x" * 65536
        yield b"x" * (65536 + extra)

    assert len(await bounded_body(chunks(0))) == 131072
    with pytest.raises(ValidationFailedError):
        await bounded_body(chunks(1))


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.com",
        "http://localhost:8011",
        "https://example.com/path",
        "https://user:pass@example.com",
        "https://example.com?secret=x",
    ],
)
def test_retirement_origin_is_fixed_and_cannot_redirect_credentials(origin):
    with pytest.raises(ValidationError):
        RetirementConnection(origin=origin, secret=secrets.token_hex(32))


@pytest.mark.parametrize("invalid", ["check", "scope", "expired", "short-lifetime", "unsigned"])
@pytest.mark.asyncio
async def test_client_rejects_wrong_or_expiring_owner_evidence(invalid):
    secret = secrets.token_hex(32)
    request = RetirementRequest(
        check_id=uuid7(),
        tenant_id=uuid7(),
        company_id=uuid7(),
        actor_user_id=uuid7(),
        warehouse_id=uuid7(),
        expected_version=1,
        command_hash="a" * 64,
        authority=ActorProof(context="delegated-fixture", signature="not-authority"),
    )

    async def handler(incoming):
        framed = service_request_bytes(
            method="POST", path=incoming.url.path, query="", body=incoming.content
        )
        now = utcnow()
        evidence = RetirementEvidence(
            owner="accounting",
            check_id=uuid7() if invalid == "check" else request.check_id,
            request_hash="b" * 64 if invalid == "scope" else request.digest(),
            issued_at=now - dt.timedelta(seconds=40) if invalid == "expired" else now,
            expires_at=now - dt.timedelta(seconds=10)
            if invalid == "expired"
            else now + dt.timedelta(seconds=3 if invalid == "short-lifetime" else 30),
            result="CLEARED",
        )
        raw, headers = response_body(
            secret.encode(), "accounting", "inspect", framed, evidence.model_dump(mode="json")
        )
        return httpx.Response(200, content=raw, headers={} if invalid == "unsigned" else headers)

    transport = RetirementClient(
        "accounting",
        RetirementConnection(origin="http://127.0.0.1:8011", secret=secret),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RetirementUnavailableError):
        await transport.check(request)
