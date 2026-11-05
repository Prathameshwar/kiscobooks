"""Native delivery verdicts require an exact manifest and original company publisher."""

import datetime as dt

import httpx
import pytest
from billing_platform.ids import uuid7
from pydantic import SecretStr
from voucher_execution.stock_policy import PATH, PolicyInspection, PolicyManifest
from voucher_execution.stock_policy_transport import (
    PolicyClient,
    PolicyConnection,
    PolicyUnavailableError,
)
from voucher_execution.stock_retirement import ActorProof

from tests.conftest import COMPANY, TENANT, USER
from tests.test_ledger_api import journal_setup, ledger_headers


def inspection(**changes):
    location = uuid7()
    proof = ledger_headers(permissions={"warehouse.manage"})
    return PolicyInspection(
        check_id=uuid7(),
        tenant_id=TENANT,
        company_id=COMPANY,
        actor_user_id=USER,
        release_id=uuid7(),
        release_revision=1,
        effective_date=dt.date(2026, 4, 2),
        manifest=PolicyManifest.model_validate(
            {
                "locations": [
                    {
                        "warehouse_id": location,
                        "revision": 1,
                        "flags": ["allow_purchase_receipt", "allow_transfer_in"],
                    }
                ],
                "defaults": {"default_purchase_warehouse_id": location},
            }
        ),
        authority=ActorProof(
            context=proof["X-Actor-Context"], signature=proof["X-Actor-Signature"]
        ),
    ).model_copy(update=changes)


async def test_native_manifest_inspection_never_guesses_enforcement_from_configuration(app, client):
    await journal_setup(client, app)
    secret = SecretStr("separate-native-policy-inspection-test-key")
    app.state.settings = app.state.settings.model_copy(update={"stock_policy_secret": secret})
    consumer = PolicyClient(
        PolicyConnection(origin="http://127.0.0.1:8011", secret=secret),
        transport=httpx.ASGITransport(app=app),
    )
    body = inspection()
    result = await consumer.inspect(body)
    assert result.result == "PENDING" and result.reason == "SOURCE_UNAVAILABLE"
    app.state.settings = app.state.settings.model_copy(
        update={
            "voucher_stock_enabled": True,
            "stock_execution_secret": secret,
            "stock_owner_url": "http://127.0.0.1:8003",
            "stock_owner_secret": secret,
            "stock_identity_url": "http://127.0.0.1:8001",
            "stock_identity_request_secret": secret,
            "stock_identity_response_secret": secret,
        }
    )
    correction = body.model_copy(
        update={
            "manifest": PolicyManifest.model_validate(
                {
                    "locations": [
                        {"warehouse_id": uuid7(), "revision": 1, "flags": ["allow_adjustment"]}
                    ],
                    "defaults": {},
                }
            )
        }
    )
    corrected = await consumer.inspect(correction)
    assert corrected.result == "APPLIED" and corrected.reason is None
    accepted = await consumer.inspect(body)
    assert accepted.result == "APPLIED" and accepted.request_hash == body.digest()
    assert "quantity" not in accepted.model_dump() and "value" not in accepted.model_dump()
    for changes in ({"company_id": uuid7()}, {"tenant_id": uuid7()}, {"actor_user_id": uuid7()}):
        with pytest.raises(PolicyUnavailableError):
            await consumer.inspect(body.model_copy(update=changes))
    denied = ledger_headers(permissions={"warehouse.read"})
    with pytest.raises(PolicyUnavailableError):
        await consumer.inspect(
            body.model_copy(
                update={
                    "authority": ActorProof(
                        context=denied["X-Actor-Context"], signature=denied["X-Actor-Signature"]
                    )
                }
            )
        )
    assert (await client.post(PATH, json=body.model_dump(mode="json"))).status_code == 401
