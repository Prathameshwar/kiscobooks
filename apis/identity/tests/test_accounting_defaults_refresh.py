"""Tax entry after creation refreshes books with a new, replay-stable setup key."""

import uuid

import httpx
import pytest
from billing_platform.company_context import verify_company_context
from billing_platform.db import tenant_scope
from sqlalchemy import select

from identity.models import CompanySetupRun, CompanySetupStep
from identity.seeds.roles import seed_system_roles
from identity.tasks.company_setup import Worker
from tests.api_support import ACTOR_SECRET, actor_headers, grant
from tests.factories import build_user, seed_two_tenants
from tests.test_api_companies import _valid_company_body
from tests.test_api_company_statutory import _gst_body


@pytest.mark.parametrize("arrival", ["after", "during_success", "during_failure"])
async def test_registration_requeues_only_books_and_changes_its_owner_key(
    client,
    session,
    factory,
    app,
    tenant_a,
    tenant_b,
    arrival,
):
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    user = build_user(tenant_id=tenant_a)
    with tenant_scope(tenant_a):
        session.add(user)
        await session.commit()
    auth = actor_headers(
        tenant_id=tenant_a,
        user_id=user.id,
        grants=[
            grant(
                [
                    "company.create",
                    "company.read",
                    "company.tax_registration.manage",
                ]
            )
        ],
    )
    result = await client.post("/v1/companies", json=_valid_company_body(), headers=auth)
    assert result.status_code == 201, result.text
    company = uuid.UUID(result.json()["id"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            for step in await db.scalars(select(CompanySetupStep)):
                step.status = "PENDING" if step.key == "books" else "READY"
    calls = []
    registration_result = None

    async def accounting(request):
        nonlocal registration_result
        calls.append(request)
        if len(calls) == 1 and arrival != "after":
            # The owner has received the old context, but has not replied yet.
            registration_result = await client.post(
                f"/v1/companies/{company}/tax-registrations", json=_gst_body(), headers=auth
            )
            if arrival == "during_failure":
                return httpx.Response(503)
        return httpx.Response(200, json={"company_id": str(company)})

    settings = app.state.settings.model_copy(
        update={
            "company_setup_origins": {"accounting": "http://127.0.0.1"},
        }
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(accounting)) as owners:
        worker = Worker(factory, settings, owners)
        assert await worker.once()
        before = calls[0].headers["Idempotency-Key"]
        if arrival == "after":
            assert not await worker.once()
            registration_result = await client.post(
                f"/v1/companies/{company}/tax-registrations", json=_gst_body(), headers=auth
            )
        assert registration_result is not None
        assert registration_result.status_code == 201, registration_result.text
        with tenant_scope(tenant_a):
            async with factory() as db:
                run = await db.scalar(select(CompanySetupRun))
                assert run.status == "PENDING" and run.lease_token is None
                assert run.created_by == user.id
                steps = list(await db.scalars(select(CompanySetupStep)))
                assert {step.key for step in steps if step.status == "PENDING"} == {"books"}
        assert await worker.once()
        assert not await worker.once()
        after = calls[-1].headers["Idempotency-Key"]
        assert after != before
        context = verify_company_context(
            calls[-1].headers["X-Company-Context"],
            calls[-1].headers["X-Company-Signature"],
            ACTOR_SECRET.encode(),
        )
        assert context.company_id == company
        assert [row["id"] for row in context.registrations] == [registration_result.json()["id"]]
        # Requeue the same facts to model a lost response; it must reuse the command key.
        with tenant_scope(tenant_a):
            async with factory.begin() as db:
                run = await db.scalar(select(CompanySetupRun))
                run.status = "PENDING"
                step = await db.scalar(
                    select(CompanySetupStep).where(CompanySetupStep.key == "books")
                )
                step.status = "PENDING"
        assert await worker.once()
        assert calls[-1].headers["Idempotency-Key"] == after
    with tenant_scope(tenant_b):
        async with factory() as db:
            assert await db.scalar(select(CompanySetupRun.id)) is None
