"""Signed registration reserve/terminal authority and lost-response recovery."""

import httpx
import pytest
from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from identity_posting import ReservationRejectedError
from identity_posting.stock import (
    StockPostingClient,
    TrackingReservationIntent,
    TrackingTerminalRequest,
    tracking_root,
)
from sqlalchemy import select

from identity.models import Company, CompanyFeature
from tests.api_support import ACTOR_SECRET
from tests.factories import build_company_feature
from tests.test_stock_posting_client import fixture


async def setup(app, session, tenant_a, tenant_b, *, permitted=True):
    company, user, request_secret, response_secret, stock_intent = await fixture(
        app,
        session,
        tenant_a,
        tenant_b,
    )
    with tenant_scope(tenant_a):
        session.add_all(
            [
                build_company_feature(tenant_id=tenant_a, company_id=company, feature_key=key)
                for key in ("batch_tracking", "expiry_tracking")
            ]
        )
        await session.commit()
    authority = stock_intent(
        permissions=[
            "accounting.batch.manage" if permitted else "accounting.batch.read",
        ]
    ).authority
    context = verify_company_context(
        authority.company_context, authority.company_signature, ACTOR_SECRET.encode()
    )
    token, signature = sign_company_context(
        context.model_copy(
            update={
                "finance": None,
                "features": frozenset({"inventory", "batch_tracking", "expiry_tracking"}),
            }
        ),
        ACTOR_SECRET.encode(),
    )
    body = TrackingReservationIntent(
        operation_id=uuid7(),
        actor_user_id=user,
        command_hash="a" * 64,
        resource="BATCH",
        features=("batch_tracking", "expiry_tracking"),
        authority=authority.model_copy(
            update={"company_context": token, "company_signature": signature}
        ),
    )
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1")
    client = StockPostingClient(
        http, request_secret=request_secret.encode(), response_secret=response_secret.encode()
    )
    return company, body, http, client


async def test_registration_confirm_locks_dates_but_does_not_post_money(
    app,
    session,
    tenant_a,
    tenant_b,
):
    company, body, http, client = await setup(app, session, tenant_a, tenant_b)
    async with http:
        root = tracking_root(tenant_a, company)
        first = await client.request(root, "tracking-reserve", body)
        assert first.status == "pending"
        assert await client.request(root, "tracking-reserve", body) == first
        with pytest.raises(ReservationRejectedError) as changed:
            await client.request(
                root,
                "tracking-reserve",
                body.model_copy(
                    update={
                        "command_hash": "b" * 64,
                    }
                ),
            )
        assert changed.value.status_code == 409
        terminal = TrackingTerminalRequest(intent=body, committed_at=utcnow())
        result = await client.request(
            root + f"/{body.operation_id}/confirmed", "tracking-confirmed", terminal
        )
        assert result.status == "confirmed"
        assert (
            await client.request(
                root + f"/{body.operation_id}/confirmed", "tracking-confirmed", terminal
            )
            == result
        )
    with tenant_scope(tenant_a):
        stored = await session.get(Company, company)
        await session.refresh(stored)
        assert stored.first_posted_at is None
        rows = {
            f.feature_key: f
            for f in await session.scalars(
                select(CompanyFeature).where(
                    CompanyFeature.company_id == company,
                )
            )
        }
        assert rows["expiry_tracking"].locked_at is not None
        assert rows["batch_tracking"].locked_at is not None
        assert rows["inventory"].locked_at is None


async def test_abort_before_lost_reserve_response_blocks_late_registration(
    app,
    session,
    tenant_a,
    tenant_b,
):
    company, body, http, client = await setup(app, session, tenant_a, tenant_b)
    async with http:
        root = tracking_root(tenant_a, company)
        result = await client.request(
            root + f"/{body.operation_id}/aborted",
            "tracking-aborted",
            TrackingTerminalRequest(intent=body),
        )
        assert result.status == "aborted"
        late = await client.request(root, "tracking-reserve", body)
        assert late.status == "aborted"
        with pytest.raises(ReservationRejectedError) as terminal:
            await client.request(
                root + f"/{body.operation_id}/confirmed",
                "tracking-confirmed",
                TrackingTerminalRequest(intent=body, committed_at=utcnow()),
            )
        assert terminal.value.status_code == 409


async def test_registration_requires_manage_and_exact_tenant_company(
    app,
    session,
    tenant_a,
    tenant_b,
):
    company, body, http, client = await setup(app, session, tenant_a, tenant_b, permitted=False)
    async with http:
        for tenant in (tenant_a, tenant_b):
            with pytest.raises(ReservationRejectedError) as denied:
                await client.request(tracking_root(tenant, company), "tracking-reserve", body)
            assert denied.value.status_code in {401, 403}
