from __future__ import annotations

import secrets

import httpx
from billing_platform.reference.replication import Change, apply
from billing_platform.reference.worker import request
from billing_platform.service_auth import ServiceKey
from pydantic import SecretStr
from sqlalchemy import select

from identity.models import Language, ReferenceChange
from tests.test_platform_setup import signed
from tests.test_reference_crud import DATA, ready

pytest_plugins = ["tests.test_platform_setup"]


async def test_authenticated_feed_ack_and_replica_integrity(setup_app, client, factory):
    key, _ = await ready(setup_app, client, factory)
    app, _, _ = setup_app
    secret = SecretStr(secrets.token_hex(32))
    app.state.settings.reference_sync_credentials = {"catalog": secret, "accounting": secret}
    created = await client.post(
        "/v1/platform/references/languages", json=DATA["languages"], headers=signed(key)
    )
    assert created.status_code == 201
    assert (await client.get("/internal/v1/reference-changes/catalog")).status_code == 401
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as transport:
        for service in ["catalog", "accounting"]:
            credential = ServiceKey(
                service,
                "identity",
                frozenset({"reference.read", "reference.ack"}),
                secret.get_secret_value().encode(),
            )
            raw = await request(
                transport,
                credential,
                "http://identity.test",
                "/internal/v1/reference-changes/" + service,
            )
            import json

            event = json.loads(raw)["items"][0]
            await request(
                transport,
                credential,
                "http://identity.test",
                "/internal/v1/reference-changes/" + service + "/ack",
                method="POST",
                query="cursor=" + event["id"],
            )
    detail = await client.get("/v1/platform/references/languages/zz", headers=signed(key))
    assert detail.json()["sync_ready"]
    # A separate consumer database is exercised in native integration; this test
    # additionally verifies version replay handling against a transaction rollback.
    async with factory() as db:
        change = await db.scalar(select(ReferenceChange))
        await apply(
            db,
            [
                Change(
                    id=change.id,
                    kind=change.kind,
                    code=change.code,
                    version=change.version,
                    payload=change.payload,
                )
            ],
            service="replica-check",
        )
        assert (await db.get(Language, "zz")).name == "Test language"
        await db.rollback()


async def test_pending_custom_choices_wait_for_both_consumer_acks(setup_app, client, factory):
    from billing_platform.db.reference_management import ReferenceSyncState

    key, _ = await ready(setup_app, client, factory)
    result = await client.post(
        "/v1/platform/references/countries", json=DATA["countries"], headers=signed(key)
    )
    assert result.status_code == 201
    assert not any(
        row["code"] == "ZZ"
        for row in (await client.get("/v1/registration/options")).json()["countries"]
    )
    async with factory() as db, db.begin():
        change = await db.scalar(select(ReferenceChange))
        db.add(ReferenceSyncState(service="catalog", cursor=change.id))
    assert not any(
        row["code"] == "ZZ"
        for row in (await client.get("/v1/registration/options")).json()["countries"]
    )
    async with factory() as db, db.begin():
        db.add(ReferenceSyncState(service="accounting", cursor=change.id))
    assert any(
        row["code"] == "ZZ"
        for row in (await client.get("/v1/registration/options")).json()["countries"]
    )


async def test_invalid_replica_batch_rolls_back_records_and_checkpoint(setup_app, client, factory):
    import pytest
    from billing_platform.db.reference_management import ReferenceSyncState
    from billing_platform.errors import ValidationFailedError
    from billing_platform.ids import uuid7

    await ready(setup_app, client, factory)
    first, second = uuid7(), uuid7()
    async with factory() as db:
        with pytest.raises(ValidationFailedError, match="ordered"):
            async with db.begin():
                await apply(
                    db,
                    [
                        Change(
                            id=second,
                            kind="language",
                            code="zz",
                            version=1,
                            payload={
                                **{
                                    key: value
                                    for key, value in DATA["languages"].items()
                                    if key != "kind"
                                },
                                "is_active": True,
                            },
                        ),
                        Change(
                            id=first,
                            kind="language",
                            code="zz",
                            version=2,
                            payload={
                                **{
                                    key: value
                                    for key, value in DATA["languages"].items()
                                    if key != "kind"
                                },
                                "is_active": True,
                            },
                        ),
                    ],
                    service="catalog",
                )
    async with factory() as db:
        assert await db.get(Language, "zz") is None
        assert (
            await db.scalar(
                select(ReferenceSyncState).where(ReferenceSyncState.service == "catalog")
            )
            is None
        )


async def test_worker_rejects_unsigned_or_oversized_responses():
    import pytest
    from billing_platform.errors import AuthenticationRequiredError

    key = ServiceKey("catalog", "identity", frozenset({"reference.read"}), secrets.token_bytes(32))
    for response in [
        httpx.Response(200, json={"items": [], "has_more": False}),
        httpx.Response(200, content=b"a" * 1_000_001),
    ]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _, response=response: response)
        ) as client:
            with pytest.raises((AuthenticationRequiredError, ValueError)):
                await request(
                    client, key, "http://identity.test", "/internal/v1/reference-changes/catalog"
                )
