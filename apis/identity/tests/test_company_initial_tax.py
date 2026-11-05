"""Initial registration is part of the idempotent company creation transaction."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.outbox import Outbox
from sqlalchemy import func, select

from identity.models import Company, CompanySetupRun, CompanyTaxRegistration
from identity.seeds.roles import seed_system_roles
from tests.api_support import actor_headers, grant
from tests.factories import build_country, build_currency, build_state, seed_two_tenants
from tests.test_api_companies import _valid_company_body

pytestmark = pytest.mark.asyncio
REGISTRATION = {"regime": "regular", "number": "27AAAPA1234A1ZT", "valid_from": "2026-04-01"}


async def prepare(session, tenant_a, tenant_b):
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    return actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.create", "company.read"])]
    ) | {"Idempotency-Key": "company-with-registration"}


async def test_create_registration_and_replay_without_duplicate(
    client, session, tenant_a, tenant_b
):
    headers = await prepare(session, tenant_a, tenant_b)
    body = _valid_company_body() | {"initial_tax_registration": REGISTRATION}
    first = await client.post("/v1/companies", json=body, headers=headers)
    assert first.status_code == 201, first.text
    second = await client.post("/v1/companies", json=body, headers=headers)
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    with tenant_scope(tenant_a):
        registrations = list(await session.scalars(select(CompanyTaxRegistration)))
        assert len(registrations) == 1
        row = registrations[0]
        assert row.company_id == uuid.UUID(first.json()["id"])
        assert (row.tax_system, row.jurisdiction_code, row.regime) == ("gst_in", "MH", "regular")
        assert row.number == REGISTRATION["number"]
        assert str(row.valid_from) == REGISTRATION["valid_from"]
        assert row.is_primary and row.registration_class == "supplier"
        events = list(await session.scalars(select(Outbox)))
        assert sum(e.event_type == "company.tax_registration_added" for e in events) == 1
        assert REGISTRATION["number"] not in str([e.payload for e in events])
    with tenant_scope(tenant_b):
        assert await session.scalar(select(func.count(CompanyTaxRegistration.id))) == 0
    changed = await client.post(
        "/v1/companies",
        headers=headers,
        json=body | {"initial_tax_registration": REGISTRATION | {"regime": "composition"}},
    )
    assert changed.status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"number": "27AAAPA1234A1Z0"},  # invalid checksum
        {"number": "29AAAPA1234A1ZP"},  # another state
        {"regime": "unknown"},
        {"valid_from": "not-a-date"},
        {"company_id": "01990000-0000-7000-8000-000000000001"},
    ],
)
async def test_invalid_registration_rolls_back_company_and_audit(
    client,
    session,
    tenant_a,
    tenant_b,
    changes,
):
    headers = await prepare(session, tenant_a, tenant_b)
    response = await client.post(
        "/v1/companies",
        headers=headers,
        json=_valid_company_body() | {"initial_tax_registration": REGISTRATION | changes},
    )
    assert response.status_code == 422, response.text
    assert any("initial_tax_registration" in k for k in response.json()["error"]["fields"])
    with tenant_scope(tenant_a):
        for model in (Company, CompanyTaxRegistration, CompanySetupRun, Outbox):
            assert await session.scalar(select(func.count(model.id))) == 0


async def test_initial_registration_requires_tenant_creation_authority(
    client, session, tenant_a, tenant_b
):
    await prepare(session, tenant_a, tenant_b)
    body = _valid_company_body() | {"initial_tax_registration": REGISTRATION}
    anonymous = await client.post("/v1/companies", json=body)
    assert anonymous.status_code == 401
    for permissions, scope in [
        (["company.read"], {}),
        (["company.create"], {"scope_type": "company", "scope_id": uuid7()}),
    ]:
        response = await client.post(
            "/v1/companies",
            json=body,
            headers=actor_headers(
                tenant_id=tenant_a,
                user_id=uuid7(),
                grants=[grant(permissions, **scope)],
            ),
        )
        assert response.status_code == 403


async def test_country_choices_supply_registration_fields(client, session, tenant_a, tenant_b):
    headers = await prepare(session, tenant_a, tenant_b)
    response = await client.get("/v1/reference/countries", headers=headers)
    assert response.status_code == 200
    india = next(c for c in response.json() if c["code"] == "IN")
    gst = next(r for r in india["tax_registration_options"] if r["tax_system"] == "gst_in")
    assert gst["number_label"] == "GSTIN"
    assert any(r["value"] == "regular" for r in gst["regimes"])
    assert not any(r["value"] == "unregistered" for r in gst["regimes"])


async def test_initial_vat_uses_country_scope(client, session, tenant_a, tenant_b):
    headers = await prepare(session, tenant_a, tenant_b)
    session.add(build_currency("GBP", numeric_code="826"))
    await session.flush()
    session.add(build_country("GB", "GBP", iso3="GBR", numeric_code="826", name="United Kingdom"))
    await session.flush()
    session.add(build_state("ENG", "GB", tax_jurisdiction_code=None))
    await session.commit()
    response = await client.post(
        "/v1/companies",
        headers=headers,
        json=_valid_company_body()
        | {
            "country_code": "GB",
            "state_code": "ENG",
            "base_currency": "GBP",
            "default_tax_system": "vat_gb",
            "initial_tax_registration": REGISTRATION
            | {"regime": "standard", "number": "GB123456789"},
        },
    )
    assert response.status_code == 201, response.text
    with tenant_scope(tenant_a):
        row = (await session.scalars(select(CompanyTaxRegistration))).one()
        assert (row.tax_system, row.jurisdiction_code, row.number) == (
            "vat_gb",
            "GB",
            "GB123456789",
        )
    choices = await client.get("/v1/reference/countries", headers=headers)
    uk = next(c for c in choices.json() if c["code"] == "GB")
    assert uk["tax_registration_options"][0]["number_label"] == "VAT registration number"
    assert uk["tax_registration_options"][0]["jurisdiction_scope"] == "country"


async def test_requests_without_registration_keep_the_previous_receipt_hash(tenant_a):
    import hashlib

    from billing_platform.idempotency import canonical_json

    from identity.api.auth import Actor
    from identity.schemas.company import CompanyCreate
    from identity.services.company_setup import identity

    body = CompanyCreate.model_validate(_valid_company_body())
    old_shape = body.model_dump(mode="json", exclude={"initial_tax_registration"})
    _, digest = identity(Actor(tenant_a, uuid7()), body, "old-browser-command")
    assert digest == hashlib.sha256(canonical_json(old_shape)).hexdigest()


async def test_initial_registration_reaches_first_automatic_books_command(
    client,
    session,
    factory,
    app,
    tenant_a,
    tenant_b,
):
    import httpx
    from billing_platform.company_context import verify_company_context

    from identity.models import CompanySetupStep
    from identity.tasks.company_setup import Worker
    from tests.api_support import ACTOR_SECRET
    from tests.factories import build_user

    await prepare(session, tenant_a, tenant_b)
    user = build_user(tenant_id=tenant_a)
    with tenant_scope(tenant_a):
        session.add(user)
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a, user_id=user.id, grants=[grant(["company.create", "company.read"])]
    )
    result = await client.post(
        "/v1/companies",
        headers=headers,
        json=_valid_company_body() | {"initial_tax_registration": REGISTRATION},
    )
    assert result.status_code == 201, result.text
    company = uuid.UUID(result.json()["id"])
    registrations = await client.get(f"/v1/companies/{company}/tax-registrations", headers=headers)
    assert registrations.status_code == 200, registrations.text
    registration = registrations.json()["items"][0]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            for step in await db.scalars(select(CompanySetupStep)):
                step.status = "PENDING" if step.key == "books" else "READY"
    calls = []

    def accounting(request):
        calls.append(request)
        return httpx.Response(200, json={"company_id": str(company)})

    settings = app.state.settings.model_copy(
        update={
            "company_setup_origins": {"accounting": "http://127.0.0.1"},
        }
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(accounting)) as owners:
        worker = Worker(factory, settings, owners)
        assert await worker.once()
        assert not await worker.once()
    assert len(calls) == 1
    assert calls[0].url.path == f"/v1/companies/{company}/financial-setup/initialize"
    context = verify_company_context(
        calls[0].headers["X-Company-Context"],
        calls[0].headers["X-Company-Signature"],
        ACTOR_SECRET.encode(),
    )
    assert context.company_id == company
    assert len(context.registrations) == 1
    assert context.registrations[0]["id"] == registration["id"]
    assert context.registrations[0]["number"] == REGISTRATION["number"]
    assert context.registrations[0]["valid_from"] == REGISTRATION["valid_from"]
