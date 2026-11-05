"""Creation recovery must survive a lost response and a different browser session."""

import secrets
import uuid
from datetime import timedelta

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Company, CompanySetupRun, CompanySetupStep, ReportSourceEnrollment
from identity.schemas.company_setup import CompanySetupOptions
from identity.seeds.roles import seed_system_roles
from tests.api_support import actor_headers, grant
from tests.factories import seed_two_tenants
from tests.test_api_companies import _valid_company_body

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "case,expected,code",
    [
        ("pending", "RETRY_WAIT", "PRODUCT_CONFIGURATION_PENDING"),
        ("draft", "NEEDS_ACTION", "PRODUCT_CONFIGURATION_REVIEW_REQUIRED"),
        ("policy", "NEEDS_ACTION", "PRODUCT_PRICING_POLICY_REVIEW_REQUIRED"),
    ],
)
async def test_catalog_setup_waits_for_published_configuration_and_pricing(
    client, session, factory, app, tenant_a, tenant_b, case, expected, code
):
    from identity.tasks.company_setup import Worker
    from tests.factories import build_user

    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    user = build_user(tenant_id=tenant_a)
    with tenant_scope(tenant_a):
        session.add(user)
        await session.commit()
    auth = actor_headers(
        tenant_id=tenant_a, user_id=user.id, grants=[grant(["company.create", "company.read"])]
    )
    created = await client.post("/v1/companies", json=_valid_company_body(), headers=auth)
    assert created.status_code == 201, created.text
    company, product = created.json()["id"], str(uuid7())

    def owner(request):
        path = request.url.path
        result = {"company_id": company}
        if path.endswith("unit-defaults/bootstrap"):
            result.update(status="READY", inventory_enabled=True)
        elif path.endswith(("product-types", "item-groups")):
            result["items"] = [
                {"id": product, "kind": "BOTH", "allowed_kind": "BOTH", "is_active": True}
            ]
        elif path.endswith("product-configuration-scopes"):
            result["items"] = (
                []
                if case == "pending"
                else [
                    {
                        "id": product,
                        "owner_id": company,
                        "latest_revision": 0 if case == "draft" else 1,
                    }
                ]
            )
        elif path.endswith("product-configuration/effective"):
            result.update(
                kind=request.url.params["kind"],
                as_of=request.url.params["as_of"],
                sources=[{"revision_id": product}],
            )
        elif path.endswith("company-pricing-policies"):
            result["items"] = []
        elif path.endswith(("revisions", "price-plans")):
            result["items"] = [{"id": product}]
        return httpx.Response(200, json=result)

    settings = app.state.settings.model_copy(
        update={"company_setup_origins": {"catalog": "http://127.0.0.1"}}
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(owner)) as wire:
        worker = Worker(factory, settings, wire)
        assert await worker.once()  # capability verification
        assert await worker.once()  # catalog readiness
    with tenant_scope(tenant_a):
        async with factory() as db:
            step = await db.scalar(
                select(CompanySetupStep).where(CompanySetupStep.key == "catalog")
            )
            assert step.status == expected and step.failure_code == code


async def test_support_session_cannot_delegate_background_authority(session, tenant_a):
    from billing_platform.errors import ConflictError

    from identity.api.auth import Actor
    from identity.schemas.company import CompanyCreate
    from identity.services.company_setup import enroll
    from tests.factories import build_company

    actor = Actor(tenant_a, uuid7(), impersonation_id=uuid7())
    with pytest.raises(ConflictError, match="support sessions"):
        await enroll(
            session,
            actor,
            build_company(tenant_id=tenant_a),
            CompanyCreate.model_validate(_valid_company_body()),
            "a" * 64,
            "b" * 64,
        )


async def test_lost_creation_response_replays_original_company(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.create", "company.read"])]
    ) | {"Idempotency-Key": "lost-company-response"}
    first = await client.post("/v1/companies", json=_valid_company_body(), headers=headers)
    assert first.status_code == 201, first.text
    second = await client.post("/v1/companies", json=_valid_company_body(), headers=headers)
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
    with tenant_scope(tenant_a):
        assert await session.scalar(select(func.count(Company.id))) == 1
    status = await client.get(f"/v1/companies/{first.json()['id']}/setup", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["company_id"] == first.json()["id"]
    assert status.json()["opening_choice"] == "ZERO_CONFIRMED"
    assert len(status.json()["steps"]) == 8
    with tenant_scope(tenant_b):
        for model in (CompanySetupRun, CompanySetupStep, ReportSourceEnrollment):
            assert await session.scalar(select(func.count(model.id))) == 0
    wrong = actor_headers(tenant_id=tenant_b, user_id=uuid7(), grants=[grant(["company.read"])])
    assert (
        await client.get(f"/v1/companies/{first.json()['id']}/setup", headers=wrong)
    ).status_code == 404
    assert (await client.get(f"/v1/companies/{first.json()['id']}/setup")).status_code == 401
    receipt = await client.get("/v1/company-setup-commands/lost-company-response", headers=headers)
    assert receipt.status_code == 200 and receipt.json()["company_id"] == first.json()["id"]
    assert (
        await client.post(f"/v1/companies/{first.json()['id']}/setup/retry", headers=headers)
    ).status_code == 403
    scoped_elsewhere = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["company.read"], scope_type="company", scope_id=uuid7())],
    )
    assert (
        await client.get(f"/v1/companies/{first.json()['id']}/setup", headers=scoped_elsewhere)
    ).status_code == 403


async def test_existing_report_adoption_is_scoped_idempotent_and_preserves_disabled_enrollment(
    client, session, tenant_a, tenant_b
):
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[
            grant(["company.create", "company.read", "company.update", "report.definition.manage"])
        ],
    )
    response = await client.post("/v1/companies", json=_valid_company_body(), headers=headers)
    company = uuid.UUID(response.json()["id"])
    with tenant_scope(tenant_a):
        enrollment = await session.scalar(select(ReportSourceEnrollment))
        await session.delete(enrollment)
        await session.commit()
    path = f"/v1/companies/{company}/setup/enroll-reports"
    assert (await client.post(path)).status_code == 401
    limited = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.update"])])
    assert (await client.post(path, headers=limited)).status_code == 403
    for _ in range(2):
        assert (await client.post(path, headers=headers)).json() == {
            "company_id": str(company),
            "enrolled": True,
        }
    with tenant_scope(tenant_a):
        assert await session.scalar(select(func.count(ReportSourceEnrollment.id))) == 1
        enrollment = await session.scalar(select(ReportSourceEnrollment))
        enrollment.status = "DISABLED"
        await session.commit()
    assert (await client.post(path, headers=headers)).json()["enrolled"] is False


async def test_worker_lease_recovery_and_revoked_actor(
    client, session, factory, app, tenant_a, tenant_b
) -> None:
    import datetime as dt

    from billing_platform.db.types import utcnow

    from identity.models import User
    from identity.tasks.company_setup import Worker
    from tests.factories import build_user

    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    user = build_user(tenant_id=tenant_a)
    with tenant_scope(tenant_a):
        session.add(user)
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a, user_id=user.id, grants=[grant(["company.create", "company.read"])]
    )
    response = await client.post("/v1/companies", json=_valid_company_body(), headers=headers)
    assert response.status_code == 201, response.text
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    ) as owners:
        worker = Worker(factory, app.state.settings, owners)
        claimed = await worker.claim()
        assert claimed is not None and claimed.step == "features"
        assert await worker.claim() is None
        with tenant_scope(tenant_a):
            async with factory.begin() as db:
                run = await db.get(CompanySetupRun, claimed.run)
                run.lease_expires_at = utcnow() - dt.timedelta(seconds=1)
        recovered = await worker.claim()
        assert recovered is not None and recovered.token != claimed.token
        with tenant_scope(tenant_a):
            async with factory.begin() as db:
                run = await db.get(CompanySetupRun, recovered.run)
                run.lease_expires_at = utcnow() - dt.timedelta(seconds=1)
                principal = await db.get(User, user.id)
                principal.status = "suspended"
        assert await worker.once()
        with tenant_scope(tenant_a):
            async with factory() as db:
                run = await db.get(CompanySetupRun, recovered.run)
                assert run.status == "NEEDS_ACTION"
                assert run.failure_code == "ACTOR_OR_COMPANY_UNAVAILABLE"


async def test_feature_dependencies_and_explicit_opening_declaration() -> None:
    defaults = CompanySetupOptions()
    assert defaults.features == ["inventory"] and defaults.opening_choice == "ZERO_CONFIRMED"
    assert defaults.opening_reason
    assert CompanySetupOptions(features=["expiry_tracking"]).features == [
        "batch_tracking",
        "expiry_tracking",
        "inventory",
    ]
    for body in (
        {"opening_choice": "ZERO_CONFIRMED", "opening_reason": "   "},
        {"features": ["unknown"]},
        {"opening_choice": "IMPORT_EXISTING", "opening_reason": "No balances"},
    ):
        with pytest.raises(ValidationError):
            CompanySetupOptions.model_validate(body)


async def test_creation_key_cannot_change_company_facts(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.create", "company.read"])]
    ) | {"Idempotency-Key": "same-command-different-facts"}
    first = await client.post("/v1/companies", json=_valid_company_body(), headers=headers)
    assert first.status_code == 201, first.text
    response = await client.post(
        "/v1/companies", json=_valid_company_body("OTHER"), headers=headers
    )
    assert response.status_code == 409, response.text
    with tenant_scope(tenant_a):
        assert await session.scalar(select(func.count(Company.id))) == 1


@pytest.mark.parametrize(
    "owner_status,message,actionable",
    [
        (503, "unavailable", False),
        (409, "request is busy; retry with the same idempotency key", False),
        (409, "request is already in progress; retry later", False),
        (409, "authoritative company settings differ from financial setup", True),
    ],
)
async def test_backend_setup_advances_without_browser_and_retries_owner_outage(
    client,
    session,
    factory,
    app,
    tenant_a,
    tenant_b,
    monkeypatch,
    owner_status,
    message,
    actionable,
) -> None:
    from billing_platform.db.types import utcnow

    from identity.tasks.company_setup import Worker
    from tests.factories import build_user

    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    user = build_user(tenant_id=tenant_a)
    with tenant_scope(tenant_a):
        session.add(user)
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a, user_id=user.id, grants=[grant(["company.create", "company.read"])]
    )
    response = await client.post("/v1/companies", json=_valid_company_body(), headers=headers)
    assert response.status_code == 201, response.text
    calls = []

    def owner(request):
        calls.append(request)
        return httpx.Response(
            owner_status, json={"error": {"code": "conflict", "message": message}}
        )

    settings = app.state.settings.model_copy(
        update={"company_setup_origins": {"catalog": "http://127.0.0.1:8002"}}
    )
    now = utcnow()
    monkeypatch.setattr("identity.tasks.company_setup.utcnow", lambda: now)
    async with httpx.AsyncClient(transport=httpx.MockTransport(owner)) as owners:
        worker = Worker(factory, settings, owners)
        assert await worker.once()
        with tenant_scope(tenant_a):
            async with factory() as db:
                steps = list(await db.scalars(select(CompanySetupStep)))
                assert next(s for s in steps if s.key == "features").status == "READY"
        assert await worker.once()
        assert len(calls) == 1
        assert calls[0].headers["Idempotency-Key"].startswith("setup-v1-")
        with tenant_scope(tenant_a):
            async with factory() as db:
                run = await db.scalar(select(CompanySetupRun))
                if actionable:
                    assert run.status == "NEEDS_ACTION"
                    assert run.failure_code == "OWNER_REVIEW_REQUIRED"
                    return
                assert run.status == "RETRY_WAIT"
                assert run.failure_code == "OWNER_NOT_READY"
                assert run.attempt == 1
                assert run.available_at == now + timedelta(seconds=2)
            async with factory.begin() as db:
                run = await db.scalar(select(CompanySetupRun))
                run.available_at = now
        assert await worker.once()
        with tenant_scope(tenant_a):
            async with factory() as db:
                run = await db.scalar(select(CompanySetupRun))
                assert run.attempt == 2
                assert run.available_at == now + timedelta(seconds=4)
        assert calls[0].headers["Idempotency-Key"] == calls[1].headers["Idempotency-Key"]


async def test_signed_report_enrollment_separates_collection_and_retained(
    client, session, app, tenant_a, tenant_b
) -> None:
    from billing_platform.db import unfiltered
    from billing_platform.db.types import utcnow
    from pydantic import SecretStr
    from reporting_contract.enrollment import EnrollmentSource, discover, enrolled

    from identity.config import ReportEnrollmentCredential
    from identity.models import PlatformInstallation

    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    with unfiltered():
        session.add(
            PlatformInstallation(
                id=uuid7(), key="platform", tenant_id=tenant_a, completed_at=utcnow()
            )
        )
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.create", "company.read"])]
    )
    response = await client.post("/v1/companies", json=_valid_company_body(), headers=headers)
    assert response.status_code == 201, response.text
    company = uuid.UUID(response.json()["id"])
    secret = SecretStr(secrets.token_hex(32))
    app.state.settings.report_enrollment_credentials = {
        "reports": ReportEnrollmentCredential(
            secret=secret, requester="reports", allow_enrolled_companies=True
        )
    }
    source = EnrollmentSource(
        origin="https://identity.test",
        key_id="reports",
        secret=secret,
        allow_enrolled_companies=True,
    )
    assert (await client.post("/internal/v1/report-enrollments", json={})).status_code == 403
    assert await enrolled(client, source, tenant_a, company)
    assert not await enrolled(client, source, tenant_b, company)
    assert len(await discover(client, source)) == 1
    with tenant_scope(tenant_a):
        row = await session.get(Company, company)
        row.status = "closed"
        await session.commit()
    assert not await enrolled(client, source, tenant_a, company)
    assert await enrolled(client, source, tenant_a, company, retained=True)


@pytest.mark.parametrize(
    "choice,inventory,period_status",
    [
        ("DECIDE_LATER", False, "FUTURE"),
        ("IMPORT_EXISTING", True, "FUTURE"),
        ("ZERO_CONFIRMED", False, "FUTURE"),
        ("DECIDE_LATER", False, "CLOSED"),
    ],
)
async def test_all_setup_steps_finish_without_a_browser_and_do_not_assume_zero(
    client, session, factory, app, tenant_a, tenant_b, choice, inventory, period_status, monkeypatch
) -> None:
    from billing_platform.db.types import utcnow
    from billing_platform.gateway import decode_actor_context

    from identity.tasks.company_setup import Worker
    from tests.api_support import ACTOR_SECRET
    from tests.factories import build_user

    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    user = build_user(tenant_id=tenant_a)
    with tenant_scope(tenant_a):
        session.add(user)
        await session.commit()
    current = actor_headers(
        tenant_id=tenant_a, user_id=user.id, grants=[grant(["company.create", "company.read"])]
    )
    body = _valid_company_body()
    body["setup"] = {"features": ["inventory"] if inventory else [], "opening_choice": choice}
    if choice == "ZERO_CONFIRMED":
        body["setup"]["opening_reason"] = "New acceptance company with no opening balances."
    response = await client.post("/v1/companies", json=body, headers=current)
    assert response.status_code == 201, response.text
    company = response.json()["id"]
    # The first committed Identity snapshot must already contain the selected
    # capabilities, before either company's background worker can run.
    from identity.models import CompanyFeature

    with tenant_scope(tenant_a):
        async with factory() as db:
            selected = set(
                await db.scalars(
                    select(CompanyFeature.feature_key).where(
                        CompanyFeature.company_id == uuid.UUID(company),
                        CompanyFeature.is_enabled.is_(True),
                    )
                )
            )
            assert ("inventory" in selected) is inventory
    year, period, product = str(uuid7()), str(uuid7()), str(uuid7())
    calls = []

    def owner(request):
        calls.append(request)
        actor = decode_actor_context(
            request.headers["x-actor-context"],
            request.headers["x-actor-signature"],
            ACTOR_SECRET.encode(),
        )
        assert actor.tenant_id == tenant_a and actor.user_id == user.id
        path = request.url.path
        setup_budget = (
            45
            if path.endswith(("accounting-setup/initialize", "financial-setup/initialize"))
            else 15
        )
        assert request.extensions["timeout"]["read"] == setup_budget
        if path.endswith("unit-defaults/bootstrap"):
            result = {"status": "READY", "inventory_enabled": inventory, "company_id": company}
        elif path.endswith("voucher-type-defaults/bootstrap"):
            result = {"status": "READY", "company_id": company}
        elif path.endswith("fiscal-years/generate"):
            result = {"id": year}
        elif path.endswith("fiscal-periods"):
            result = {
                "items": [
                    {
                        "id": period,
                        "start_date": "2026-04-01",
                        "end_date": "2026-04-30",
                        "status": period_status,
                        "row_version": 1,
                    },
                    {
                        "id": str(uuid7()),
                        "start_date": "2026-03-01",
                        "end_date": "2026-03-31",
                        "status": "FUTURE",
                        "row_version": 1,
                    },
                    {
                        "id": str(uuid7()),
                        "start_date": "2026-05-01",
                        "end_date": "2026-05-31",
                        "status": "FUTURE",
                        "row_version": 1,
                    },
                    {
                        "id": str(uuid7()),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "status": "CLOSED",
                        "row_version": 1,
                    },
                ]
            }
        elif path.endswith("product-types") or path.endswith("item-groups"):
            result = {
                "items": [
                    {"id": product, "is_active": True, "kind": "BOTH", "allowed_kind": "BOTH"}
                ]
            }
        elif path.endswith("revisions") or path.endswith("price-plans"):
            result = {"items": [{"id": product}]}
        elif path.endswith("product-configuration-scopes"):
            result = {"items": [{"id": product, "owner_id": company, "latest_revision": 1}]}
        elif path.endswith("product-configuration/effective"):
            result = {
                "company_id": company,
                "kind": request.url.params["kind"],
                "as_of": request.url.params["as_of"],
                "sources": [{"revision_id": product}],
            }
        elif path.endswith("company-pricing-policies"):
            result = {"items": [{"id": product}]}
        elif path.endswith("source-readiness"):
            if sum(r.url.path.endswith("source-readiness") for r in calls) == 1:
                return httpx.Response(503)
            result = {"state": "CURRENT", "generation_id": year, "company_id": company}
        elif path.endswith("zero-opening-review"):
            result = {"eligible": True, "expected_setup_version": 1}
        elif path.endswith("stock/openings/readiness"):
            result = {"status": "NOT_STARTED", "expected_generation": 1}
        else:
            result = {"company_id": company}
        return httpx.Response(200, json=result)

    settings = app.state.settings.model_copy(
        update={
            "company_setup_origins": {
                s: "http://127.0.0.1" for s in ("catalog", "accounting", "vouchers", "reports")
            }
        }
    )
    now = utcnow()
    monkeypatch.setattr("identity.tasks.company_setup.utcnow", lambda: now)
    async with httpx.AsyncClient(transport=httpx.MockTransport(owner)) as wire:
        worker = Worker(factory, settings, wire)
        for _ in range(8):
            if not await worker.once():
                break
        if period_status != "CLOSED":
            with tenant_scope(tenant_a):
                async with factory.begin() as db:
                    run = await db.scalar(select(CompanySetupRun))
                    assert run.status == "RETRY_WAIT"
                    # Successful earlier steps must not inflate this step's first
                    # dependency retry to the maximum backoff.
                    assert run.attempt == 1
                    assert run.available_at == now + timedelta(seconds=2)
                    run.available_at = now
            assert await worker.once()
        assert not await worker.once()
    with tenant_scope(tenant_a):
        async with factory() as db:
            run = await db.scalar(select(CompanySetupRun))
            if period_status == "CLOSED":
                assert (
                    run.status == "NEEDS_ACTION"
                    and run.failure_code == "BOOKS_PERIOD_REVIEW_REQUIRED"
                )
                assert not any(r.url.path.endswith("/transition") for r in calls)
                return
            assert run.status == "COMPLETE"
            assert run.attempt == 0
            opening = await db.scalar(
                select(CompanySetupStep).where(CompanySetupStep.key == "opening")
            )
            assert opening.status == ("READY" if choice == "ZERO_CONFIRMED" else "AWAITING_OPENING")
    assert sum("confirm-zero" in r.url.path for r in calls) == (
        (2 if inventory else 1) if choice == "ZERO_CONFIRMED" else 0
    )
    assert sum(r.url.path.endswith("/transition") for r in calls) == 2
