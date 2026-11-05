"""Coordinated NoPendingDocument leases block concurrent native capture safely."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.gateway import decode_actor_context
from billing_platform.ids import uuid7
from conftest import COMPANY, PERMISSIONS, SECRET, TENANT, USER, headers
from pydantic import SecretStr
from sqlalchemy import select
from test_stock_capture import auth, fixture
from voucher_execution.retirement_transport import (
    RetirementClient,
    RetirementConnection,
    RetirementUnavailableError,
)
from voucher_execution.stock_retirement import ActorProof, RetirementRelease, RetirementRequest

from vouchers.models.stock_retirement import StockRetirementFence
from vouchers.tasks.stock_retirement import acquire, release


def request(warehouse):
    proof = headers(permissions=PERMISSIONS | {"warehouse.deactivate", "warehouse_bin.manage"})
    actor = decode_actor_context(
        proof["X-Actor-Context"], proof["X-Actor-Signature"], SECRET.encode()
    )
    return RetirementRequest(
        check_id=uuid7(),
        tenant_id=TENANT,
        company_id=COMPANY,
        actor_user_id=USER,
        warehouse_id=warehouse,
        expected_version=1,
        command_hash="a" * 64,
        authority=ActorProof(
            context=proof["X-Actor-Context"], signature=proof["X-Actor-Signature"]
        ),
    ), actor


async def test_retirement_write_fence_blocks_new_stock_and_replays_then_releases(
    client, prefix, app
):
    body = await fixture(client, prefix, app)
    check, actor = request(uuid.UUID(body["stock"]["lines"][0]["warehouse_id"]))
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            granted = await acquire(db, check, actor)
            assert granted.result == "CLEARED" and granted.fence_id
        async with app.state.session_factory.begin() as db:
            assert await acquire(db, check, actor) == granted
    blocked = await client.post(prefix + "/vouchers", json=body, headers=auth())
    assert blocked.status_code == 409, blocked.text
    assert "retirement check" in blocked.json()["error"]["message"]
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            await release(
                db,
                RetirementRelease(
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    check_id=check.check_id,
                    fence_id=granted.fence_id,
                ),
            )
        with pytest.raises(ConflictError, match="completed"):
            async with app.state.session_factory.begin() as db:
                await acquire(db, check, actor)
    saved = await client.post(prefix + "/vouchers", json=body, headers=auth())
    assert saved.status_code == 201, saved.text


async def test_pending_stock_document_prevents_clearance_but_cancelled_history_does_not(
    client, prefix, app
):
    body = await fixture(client, prefix, app)
    saved = await client.post(prefix + "/vouchers", json=body, headers=auth())
    assert saved.status_code == 201, saved.text
    check, actor = request(uuid.UUID(body["stock"]["lines"][0]["warehouse_id"]))
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            refused = await acquire(db, check, actor)
            assert refused.result == "BLOCKED" and refused.reason == "PENDING_DOCUMENT"
            assert refused.fence_id is None
        async with app.state.session_factory.begin() as db:
            other = await acquire(
                db, check.model_copy(update={"warehouse_id": uuid7(), "check_id": uuid7()}), actor
            )
            assert other.result == "CLEARED"
            await release(
                db,
                RetirementRelease(
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    check_id=other.check_id,
                    fence_id=other.fence_id,
                ),
            )
    cancelled = await client.post(
        prefix + "/vouchers/" + saved.json()["id"] + "/cancel",
        json={
            "expected_version": 1,
            "reason": "Cancel pending stock before retiring its warehouse",
        },
        headers=auth(),
    )
    assert cancelled.status_code == 200, cancelled.text
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            assert (await acquire(db, check, actor)).result == "CLEARED"


async def test_retirement_fence_is_tenant_isolated_and_immutable(client, prefix, app):
    await fixture(client, prefix, app)
    check, actor = request(uuid7())
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            granted = await acquire(db, check, actor)
        with pytest.raises(ConflictError, match="immutable"):
            async with app.state.session_factory.begin() as db:
                row = await db.get(StockRetirementFence, granted.fence_id)
                row.request_hash = "b" * 64
        with pytest.raises(ConflictError, match="deleted"):
            async with app.state.session_factory.begin() as db:
                await db.delete(await db.get(StockRetirementFence, granted.fence_id))
    with tenant_scope(uuid7()):
        async with app.state.session_factory() as db:
            assert list(await db.scalars(select(StockRetirementFence))) == []


async def test_signed_retirement_transport_requires_owner_and_current_actor(client, prefix, app):
    await fixture(client, prefix, app)
    check, actor = request(uuid7())
    secret = SecretStr("native-retirement-channel-test-credential" * 2)
    app.state.settings = app.state.settings.model_copy(update={"stock_retirement_secret": secret})
    connection = RetirementConnection(origin="http://127.0.0.1:8012", secret=secret)
    owner = RetirementClient("vouchers", connection, transport=httpx.ASGITransport(app=app))
    granted = await owner.check(check)
    assert granted.owner == "vouchers" and granted.result == "CLEARED"
    await owner.release(
        RetirementRelease(
            tenant_id=TENANT,
            company_id=COMPANY,
            check_id=check.check_id,
            fence_id=granted.fence_id,
        )
    )
    wrong = RetirementClient(
        "vouchers",
        connection.model_copy(update={"secret": SecretStr("wrong-key" * 8)}),
        transport=httpx.ASGITransport(app=app),
    )
    with pytest.raises(RetirementUnavailableError):
        await wrong.check(check)
    stale = check.model_copy(
        update={
            "check_id": uuid7(),
            "authority": ActorProof(
                context=check.authority.context,
                signature="invalid-subject-signature",
            ),
        }
    )
    with pytest.raises(RetirementUnavailableError):
        await owner.check(stale)
