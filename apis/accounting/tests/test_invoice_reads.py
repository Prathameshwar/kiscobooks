"""Native invoice register grain, bounded component reads, field denies and populated isolation."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select

from accounting.metadata import service_metadata
from accounting.models import MODELS
from accounting.models.invoice import INVOICE_MODELS
from accounting.models.invoice_credit import INVOICE_CREDIT_MODELS
from tests.conftest import COMPANY, TENANT
from tests.invoice_helpers import posted_purchase
from tests.test_fiscal_api import BASE
from tests.test_invoice_credit_api import action
from tests.test_voucher_tax import th


async def test_invoice_reads_paging_sparse_facts_and_field_denies(client, app):
    data = await posted_purchase(client, app, components=True)
    identity = str(data["invoice"].id)
    url = BASE + "/invoice-records"
    listing = await client.get(url, headers=th())
    assert listing.status_code == 200, listing.text
    assert listing.headers["cache-control"] == "no-store"
    assert len(listing.json()["items"]) == 1
    assert listing.json()["items"][0]["payable"] == "1180.0000"
    detail = await client.get(url + "/" + identity, headers=th())
    assert (
        detail.status_code == 200
        and detail.json()["calculation_hash"] == data["invoice"].calculation_hash
    )
    assert (await client.get(url, headers={})).status_code == 401
    assert (await client.get(url, headers=th(permissions=set()))).status_code == 403
    assert (
        await client.get(url + "?date_from=2026-05-01&date_to=2026-04-01", headers=th())
    ).status_code == 422
    assert (await client.get(url + "?limit=201", headers=th())).status_code == 422
    assert (await client.get(url + "?cursor=bad", headers=th())).status_code == 422
    for section, count in (
        ("supplies", 1),
        ("components", 2),
        ("allocations", 4),
        ("tax-components", 1),
        ("posting-lines", 3),
    ):
        first = await client.get(url + f"/{identity}/{section}?limit=1", headers=th())
        assert first.status_code == 200, first.text
        value = first.json()
        assert len(value["items"]) == 1 and "source_evidence" not in value["items"][0]
        fact = await client.get(
            url + f"/{identity}/{section}/{value['items'][0]['id']}", headers=th()
        )
        assert fact.status_code == 200 and fact.json()["invoice_id"] == identity, fact.text
        if count > 1:
            cursor = value["page"]["next_cursor"]
            second = await client.get(
                url + f"/{identity}/{section}?limit=1&cursor={cursor}", headers=th()
            )
            assert (
                second.status_code == 200
                and second.json()["items"][0]["id"] != value["items"][0]["id"]
            )
            stolen = await client.get(
                url + f"/{identity}/supplies?limit=2&cursor={cursor}", headers=th()
            )
            assert stolen.status_code == 422
    denied = th(
        policies=[
            {
                "entity_type": "accounting.invoice_record",
                "field_key": "payable",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
    )
    assert "payable" not in (await client.get(url, headers=denied)).json()["items"][0]
    denied_filter = th(
        policies=[
            {
                "entity_type": "accounting.invoice_record",
                "field_key": "kind",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
    )
    assert (await client.get(url + "?kind=PURCHASE", headers=denied_filter)).status_code == 403
    supplies = (await client.get(url + f"/{identity}/supplies", headers=th())).json()["items"]
    masked = await client.get(
        url + f"/{identity}/supplies/{supplies[0]['id']}", headers=denied_filter
    )
    assert masked.status_code == 200 and "source_evidence" not in masked.json()


async def test_all_invoice_tables_have_populated_tenant_and_company_isolation(client, app):
    data = await posted_purchase(client, app, components=True)
    verified = await client.post(
        BASE + "/invoice-credit-actions", json=action(data["component"]), headers=th()
    )
    assert verified.status_code == 201, verified.text
    expected = (*INVOICE_MODELS, *INVOICE_CREDIT_MODELS)
    # Clone the native FK graph, including owner tax replicas, into a second tenant.
    models = {
        model.__tablename__: model
        for model in MODELS
        if hasattr(model, "company_id") and not model.__tablename__.startswith("report_")
    }
    originals = {}
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            for table in service_metadata().sorted_tables:
                if table.name in models:
                    rows = list(await db.scalars(select(models[table.name])))
                    originals[table.name] = [
                        {
                            column.key: getattr(row, column.key)
                            for column in table.columns
                            if column.computed is None
                        }
                        for row in rows
                    ]
    assert all(originals[model.__tablename__] for model in expected)
    for other_tenant in (uuid7(), TENANT):
        other_company = uuid7()
        ids = {TENANT: other_tenant, COMPANY: other_company}

        def remap(value, mapping=ids):
            if isinstance(value, uuid.UUID):
                return mapping.setdefault(value, uuid7())
            if isinstance(value, dict):
                return {key: remap(item, mapping) for key, item in value.items()}
            if isinstance(value, list):
                return [remap(item, mapping) for item in value]
            return value

        with tenant_scope(other_tenant):
            async with app.state.session_factory.begin() as db:
                for name, rows in originals.items():
                    for row in rows:
                        db.add(models[name](**remap(row)))
                        await db.flush()
        with tenant_scope(other_tenant):
            async with app.state.session_factory() as db:
                for model in expected:
                    rows = list(
                        await db.scalars(select(model).where(model.company_id == other_company))
                    )
                    assert len(rows) == len(originals[model.__tablename__]), model.__tablename__
                    assert all(row.tenant_id == other_tenant for row in rows)
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                if other_tenant != TENANT:
                    for model in expected:
                        assert (
                            await db.get(model, ids[originals[model.__tablename__][0]["id"]])
                            is None
                        )
        if other_tenant == TENANT:
            response = await client.get(
                BASE + f"/invoice-records/{ids[data['invoice'].id]}", headers=th()
            )
            assert response.status_code == 403
            response = await client.get(
                BASE + f"/invoice-tax-components/{ids[data['component'].id]}/credit-position",
                headers=th(),
            )
            assert response.status_code == 403
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.get(INVOICE_CREDIT_MODELS[0], uuid.UUID(verified.json()["id"]))
            row.amount = 1
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()
            await db.rollback()
