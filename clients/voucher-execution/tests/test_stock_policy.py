import datetime as dt

import httpx
import pytest
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import (
    SnapshotCredential,
    authenticate_snapshot,
    response_headers,
)
from pydantic import SecretStr, ValidationError

from voucher_execution.stock_policy import KEY, PolicyInspection, PolicyManifest
from voucher_execution.stock_policy_transport import (
    PolicyClient,
    PolicyConnection,
    PolicyUnavailableError,
)
from voucher_execution.stock_retirement import ActorProof


def inspection():
    identity = uuid7()
    return PolicyInspection(
        check_id=uuid7(),
        tenant_id=uuid7(),
        company_id=uuid7(),
        actor_user_id=uuid7(),
        release_id=uuid7(),
        release_revision=1,
        effective_date=dt.date(2026, 10, 28),
        manifest=PolicyManifest.model_validate(
            {
                "locations": [
                    {
                        "warehouse_id": identity,
                        "revision": 1,
                        "flags": ["allow_purchase_receipt"],
                    }
                ],
                "defaults": {"default_purchase_warehouse_id": identity},
            }
        ),
        authority=ActorProof(
            context="original-actor-context", signature="original-actor-signature"
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["none", "scope", "key", "expired", "future", "large", "redirect"]
)
async def test_policy_transport_accepts_only_fresh_request_bound_owner_claims(change):
    secret = SecretStr("separate-ephemeral-stock-policy-contract-key")
    credential = SnapshotCredential(secret=secret, allow_enrolled_companies=True)
    body = inspection()

    def handler(request):
        _, framed, key = authenticate_snapshot(
            {KEY: credential},
            requester="catalog",
            owner="accounting",
            headers=request.headers,
            method=request.method,
            path=request.url.path,
            query="",
            body=request.content,
        )
        now = utcnow()
        raw = canonical_json(
            {
                "check_id": str(body.check_id),
                "request_hash": "a" * 64 if change == "scope" else body.digest(),
                "issued_at": (
                    now + dt.timedelta(seconds=10) if change == "future" else now
                ).isoformat(),
                "expires_at": (
                    now + dt.timedelta(seconds=2 if change == "expired" else 30)
                ).isoformat(),
                "result": "APPLIED",
                "reason": None,
            }
        )
        if change == "large":
            raw = b"x" * 16385
        signer = (
            credential.model_copy(
                update={"secret": SecretStr("other-native-policy-key" * 3)}
            )
            if change == "key"
            else credential
        )
        return httpx.Response(
            302 if change == "redirect" else 200,
            content=raw,
            headers=response_headers(
                signer,
                owner="accounting",
                requester="catalog",
                key_id=key,
                request_bytes=framed,
                body=raw,
            ),
        )

    client = PolicyClient(
        PolicyConnection(origin="http://127.0.0.1:8011", secret=secret),
        transport=httpx.MockTransport(handler),
    )
    if change == "none":
        assert (await client.inspect(body)).result == "APPLIED"
    else:
        with pytest.raises(PolicyUnavailableError):
            await client.inspect(body)


def test_manifest_and_scope_are_closed_and_bounded():
    body = inspection().model_dump(mode="json")
    with pytest.raises(ValidationError):
        PolicyInspection.model_validate(body | {"consumer": "billing"})
    for manifest in (
        {"locations": body["manifest"]["locations"] * 2, "defaults": {}},
        {"locations": body["manifest"]["locations"] * 501, "defaults": {}},
        {
            "locations": [
                {
                    "warehouse_id": str(uuid7()),
                    "revision": 1,
                    "flags": ["allow_teleport"],
                }
            ],
            "defaults": {},
        },
        {
            "locations": body["manifest"]["locations"],
            "defaults": {"default_sale_warehouse_id": str(uuid7())},
        },
    ):
        with pytest.raises(ValidationError):
            PolicyInspection.model_validate(body | {"manifest": manifest})
