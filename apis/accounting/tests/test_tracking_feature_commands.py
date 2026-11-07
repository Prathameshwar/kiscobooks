"""Registration commits first-use delivery atomically and preserves uncertain retries."""

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.outbox import emit
from identity_posting import ReservationError
from sqlalchemy import select

from accounting.tasks.posting_delivery import deliver
from tests.conftest import TENANT
from tests.test_stock_tracking import BASE, auth, batch
from tests.test_stock_tracking import source as source

pytestmark = pytest.mark.usefixtures("source")


async def test_committed_registration_wins_over_late_abort(client, app):
    from billing_platform.company_context import verify_company_context
    from billing_platform.gateway import decode_actor_context
    from fastapi import Request

    from accounting.api.auth import Access
    from accounting.schemas.stock_tracking import BatchPrepare
    from accounting.stock_resources import BATCH
    from accounting.tasks.stock_tracking import command_identity
    from accounting.tasks.tracking_features import abort
    from tests.conftest import SECRET
    from tests.test_masters import prepare

    await prepare(client)
    h = auth()
    result = await client.post(BASE + "/batches", headers=h, json=batch())
    assert result.status_code == 201, result.text
    current = Access(
        decode_actor_context(h["X-Actor-Context"], h["X-Actor-Signature"], SECRET.encode()),
        verify_company_context(h["X-Company-Context"], h["X-Company-Signature"], SECRET.encode()),
    )
    identity = command_identity(current, BATCH, BatchPrepare.model_validate(batch()),
                                h["Idempotency-Key"], "prepare")
    intent = app.state.tracking_feature_client.calls[0][2]
    await abort(Request({"type": "http", "app": app}), current, intent, identity)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(Outbox.id).where(
                Outbox.event_type == "accounting.tracking_feature.abort",
            )) is None


async def test_registration_emits_exact_confirmation_once_and_replay_skips_reserve(client, app):
    from tests.test_masters import prepare

    await prepare(client)
    h = auth()
    result = await client.post(BASE + "/batches", headers=h, json=batch())
    assert result.status_code == 201, result.text
    replay = await client.post(BASE + "/batches", headers=h, json=batch())
    assert replay.status_code == 201, replay.text
    assert len(app.state.tracking_feature_client.calls) == 1
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.event_type == "accounting.tracking_feature.confirm",
                    )
                )
            )
            assert len(rows) == 1
            assert set(rows[0].payload["intent"]["features"]) == {
                "batch_tracking",
                "expiry_tracking",
            }


async def test_uncertain_reserve_can_recover_same_request_without_aborting(client, app):
    from tests.test_masters import prepare

    await prepare(client)
    remote = app.state.tracking_feature_client
    remote.failure = ReservationError("Lost signed reservation response")
    h = auth()
    failed = await client.post(BASE + "/batches", headers=h, json=batch())
    assert failed.status_code == 503, failed.text
    remote.failure = None
    recovered = await client.post(BASE + "/batches", headers=h, json=batch())
    assert recovered.status_code == 201, recovered.text
    assert remote.calls[0][2].operation_id == remote.calls[1][2].operation_id
    assert remote.calls[0][2].command_hash == remote.calls[1][2].command_hash
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (
                await db.scalar(
                    select(Outbox.id).where(
                        Outbox.event_type == "accounting.tracking_feature.abort",
                    )
                )
                is None
            )


async def test_unconfigured_registration_fails_closed(client, app):
    from tests.test_masters import prepare

    await prepare(client)
    app.state.tracking_feature_client = None
    result = await client.post(BASE + "/batches", headers=auth(), json=batch())
    assert result.status_code == 409, result.text


async def test_confirmation_delivery_failure_is_retained_and_retried(client, app):
    import datetime as dt

    from tests.test_masters import prepare

    await prepare(client)
    result = await client.post(BASE + "/batches", headers=auth(), json=batch())
    assert result.status_code == 201, result.text
    remote = app.state.tracking_feature_client
    remote.failure = ReservationError("Temporary terminal delivery failure")
    failed = await deliver(app.state.session_factory, None, stock_client=remote)
    assert failed.confirmed == 0 and failed.deferred == 1
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            event = await db.scalar(
                select(Outbox).where(
                    Outbox.event_type == "accounting.tracking_feature.confirm",
                )
            )
            assert event.published_at is None
            event.available_at = utcnow() - dt.timedelta(seconds=1)
    remote.failure = None
    delivered = await deliver(app.state.session_factory, None, stock_client=remote)
    assert delivered.confirmed == 1 and delivered.deferred == 0
    assert (await deliver(app.state.session_factory, None, stock_client=remote)).confirmed == 0


async def test_rejected_local_registration_releases_reserved_features(client, app):
    from tests.test_masters import prepare

    await prepare(client)
    result = await client.post(BASE + "/batches", headers=auth(), json=batch(manufactured_on=None))
    assert result.status_code == 422, result.text
    remote = app.state.tracking_feature_client
    delivered = await deliver(app.state.session_factory, None, stock_client=remote)
    assert delivered.confirmed == 1
    assert remote.calls[-1][1] == "tracking-aborted"


async def test_abort_winning_before_local_mutation_prevents_late_registration(
    client, app, monkeypatch
):
    from tests.test_masters import prepare

    await prepare(client)
    remote = app.state.tracking_feature_client
    original = remote.request

    async def aborted_before_commit(path, operation, intent):
        with tenant_scope(TENANT):
            async with app.state.session_factory.begin() as db:
                emit(
                    db,
                    tenant_id=TENANT,
                    aggregate_type="tracking_reservation",
                    aggregate_id=intent.operation_id,
                    event_type="accounting.tracking_feature.abort",
                    payload={},
                )
        return await original(path, operation, intent)

    monkeypatch.setattr(remote, "request", aborted_before_commit)
    result = await client.post(BASE + "/batches", headers=auth(), json=batch())
    assert result.status_code == 409, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (
                await db.scalar(
                    select(Outbox.id).where(
                        Outbox.event_type == "accounting.tracking_feature.confirm",
                    )
                )
                is None
            )
