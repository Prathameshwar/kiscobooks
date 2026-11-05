import datetime as dt
import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.tax import ACTIVATION_MODELS, TAX_MODELS, TaxRateComponent
from catalog.tasks import activation
from tests.tax_factories import DATE, query, seed_tax
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")
PATHS = (
    "tax-classifications",
    "tax-categories",
    "tax-rules",
    "tax-rate-series",
    "tax-rates",
    "tax-rate-components",
    "tax-scopes",
    "tax-bindings",
    "tax-rule-applicabilities",
    "tax-releases",
    "tax-history-actions",
    "item-activations",
    "item-activation-sources",
    "item-inventory-profiles",
)
MODELS = (*TAX_MODELS, *ACTIVATION_MODELS)


async def activated(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> tuple[str, dict[str, str], dict[str, uuid.UUID]]:
    root, auth, ids = await seed_tax(factory, tenant)
    path = root + "/items/" + str(ids["item"])
    preview = await client.post(
        path + "/activation-preview", headers=auth, json={"as_of": str(DATE)}
    )
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    body = {
        key: preview.json()[key]
        for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
    }
    result = await client.post(path + "/activate", headers=command_headers(auth), json=body)
    assert result.status_code == 200, result.text
    with tenant_scope(tenant):
        async with factory() as db:
            for model in ACTIVATION_MODELS:
                value = await db.scalar(
                    select(model).where(model.company_id == uuid.UUID(root.rsplit("/", 1)[1]))
                )
                assert value is not None
                ids[model.__tablename__] = value.id
    return root, auth, ids


async def test_all_eleven_tables_are_tenant_isolated_and_decimal(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    _, _, a = await activated(client, factory, tenant_a)
    _, _, b = await activated(client, factory, tenant_b)
    for tenant, own, foreign in ((tenant_a, a, b), (tenant_b, b, a)):
        with tenant_scope(tenant):
            async with factory() as db:
                for model in MODELS:
                    ids = set(await db.scalars(select(model.id)))
                    assert own[model.__tablename__] in ids
                    assert foreign[model.__tablename__] not in ids
                component = await db.get(TaxRateComponent, own["tax_rate_component"])
                assert component is not None and isinstance(component.percentage, Decimal)


async def test_every_tax_and_activation_read_checks_scope_and_lean_contract(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    root, auth, a = await activated(client, factory, tenant_a)
    other, _, b = await activated(client, factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    denied = headers(
        company, tenant=tenant_a, user=a["actor_user"], permission=["catalog.readiness.read"]
    )
    for model, path in zip(MODELS, PATHS, strict=True):
        url = root + "/" + path
        detail = await client.get(url + "/" + str(a[model.__tablename__]), headers=auth)
        assert detail.status_code == 200, (path, detail.text)
        page = await client.get(url, headers=auth, params={"limit": 1})
        assert page.status_code == 200 and page.json()["items"], (path, page.text)
        assert "source_reference" not in page.json()["items"][0]
        assert (await client.get(url, headers=denied)).status_code == 403
        assert (await client.get(url)).status_code == 401
        assert (await client.get(url, headers=auth, params={"unknown": "x"})).status_code == 422
        foreign = await client.get(url + "/" + str(b[model.__tablename__]), headers=auth)
        assert foreign.status_code == 403, foreign.text
        assert (await client.get(other + "/" + path, headers=auth)).status_code == 403
    for path, params, status in (
        ("tax-categories", {"q": "TEST", "sort": "code,id"}, 200),
        ("tax-classifications", {"q": "123", "as_of": str(DATE)}, 200),
        ("tax-rates", {"series_id": str(a["tax_rate_series"]), "as_of": str(DATE)}, 200),
        ("tax-categories", {"as_of": str(DATE)}, 422),
        ("tax-rates", {"q": "x"}, 422),
        ("tax-categories", {"series_id": str(a["tax_rate_series"])}, 422),
    ):
        result = await client.get(root + "/" + path, headers=auth, params=params)
        assert result.status_code == status, result.text


async def test_fixed_cess_resolution_rechecks_unit_field_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = TaxRateComponent(
                tenant_id=tenant_a,
                company_id=company,
                rate_id=ids["rate_INTER_STATE"],
                component_key="CESS",
                component="CESS",
                kind="FIXED_PER_UNIT",
                percentage=None,
                amount=Decimal("1"),
                currency="INR",
                unit_id=ids["unit_of_measure"],
                basis_quantity=Decimal("1"),
                rounding_mode="HALF_UP",
                position=1,
                row_version=1,
            )
            db.add(row)
            await db.flush()
            component_id = row.id
            for context in ("INTRA_STATE", "INTRA_UT"):
                db.add(
                    TaxRateComponent(
                        tenant_id=tenant_a,
                        company_id=company,
                        rate_id=ids["rate_" + context],
                        component_key="CESS",
                        component="CESS",
                        kind="FIXED_PER_UNIT",
                        percentage=None,
                        amount=Decimal("1"),
                        currency="INR",
                        unit_id=ids["unit_of_measure"],
                        basis_quantity=Decimal("1"),
                        rounding_mode="HALF_UP",
                        position=2,
                        row_version=1,
                    )
                )
    ok = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    assert ok.status_code == 200, ok.text
    await policy(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        "catalog.unit_of_measure",
        "decimal_places",
        "read",
        version=3,
    )
    result = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    assert result.status_code == 403, result.text
    result = await client.get(root + "/tax-rate-components/" + str(component_id), headers=auth)
    assert result.status_code == 403, result.text
