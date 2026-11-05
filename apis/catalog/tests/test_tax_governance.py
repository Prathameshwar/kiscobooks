"""Synthetic end-to-end schedule correction, evidence and future readiness checks."""

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Outbox
from catalog.models.tax import CatalogTaxBinding, TaxClassification, TaxRate, TaxRelease
from catalog.tasks import activation
from tests.pricing_factories import guard
from tests.product_review_factories import changed
from tests.tax_factories import DATE, EVIDENCE, components, query, seed_tax
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")
CONTEXTS = ("INTRA_STATE", "INTRA_UT", "INTER_STATE")


def rates(
    ids: dict[str, uuid.UUID], generation: dict[str, Any], total: str = "12", version: int = 1
) -> list[dict[str, Any]]:
    return [
        {
            "key": context,
            "kind": "RATE",
            "definition": {
                **generation,
                **EVIDENCE,
                "series_id": str(ids["series_" + context]),
                "valid_from": "2091-01-01",
                "supersedes_id": str(ids["rate_" + context]),
                "expected_previous_version": version,
                "components": components(context, total),
            },
        }
        for context in CONTEXTS
    ]


async def release(
    client: httpx.AsyncClient, root: str, auth: dict[str, str], body: dict[str, Any]
) -> dict[str, Any]:
    preview = await client.post(root + "/tax-release-previews", headers=auth, json=body)
    assert preview.status_code == 200, preview.text
    request = command_headers(auth)
    commit = {**body, "preview_token": preview.json()["preview_token"]}
    result = await client.post(root + "/tax-releases", headers=request, json=commit)
    assert result.status_code == 201, result.text
    replay = await client.post(root + "/tax-releases", headers=request, json=commit)
    assert (
        replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    ), replay.text
    return dict(result.json())


async def test_coordinated_rates_preview_rolls_back_and_future_correction_retains_history(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    current = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    generation = guard(current.json())
    changes = rates(ids, generation)
    with tenant_scope(tenant_a):
        async with factory() as db:
            audit_before = await db.scalar(select(func.count(Outbox.id)))
    invalid = await client.post(
        root + "/tax-rates", headers=command_headers(auth), json=changes[0]["definition"]
    )
    assert invalid.status_code == 409, invalid.text
    body = {**generation, "change_reason": "Synthetic coordinated revision", "changes": changes}
    preview = await client.post(root + "/tax-release-previews", headers=auth, json=body)
    assert preview.status_code == 200, preview.text
    assert str(ids["item"]) in preview.json()["affected_item_ids"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(TaxRate.id))) == 3
            assert await db.scalar(select(func.count(TaxRelease.id))) == 1
            assert await db.scalar(select(func.count(Outbox.id))) == audit_before
    published = await release(client, root, auth, body)
    actions = await client.get(
        root + "/tax-history-actions", headers=auth, params={"release_id": published["id"]}
    )
    assert actions.status_code == 200, actions.text
    targets = [entry["target_id"] for entry in actions.json()["items"]]
    assert len(targets) == 3
    generation = guard(published)
    withdrawals = [
        {
            "key": "remove" + str(index),
            "kind": "WITHDRAWAL",
            "definition": {
                **generation,
                "resource": "tax_rate",
                "target_id": target,
                "expected_version": 1,
                "reason": "Correct future schedule",
                "restore_predecessor": True,
            },
        }
        for index, target in enumerate(targets)
    ]
    await release(
        client,
        root,
        auth,
        {
            **generation,
            "change_reason": "Correct same start date",
            "changes": withdrawals + rates(ids, generation, "18", version=3),
        },
    )
    effective = await client.post(
        root + "/tax-configurations/resolve", headers=auth, json=query(ids, as_of="2091-01-01")
    )
    assert effective.status_code == 200 and effective.json()["status"] == "COMPLETE", effective.text
    interstate = next(
        entry for entry in effective.json()["rates"] if entry["applicability"] == "INTER_STATE"
    )
    assert interstate["components"][0]["percentage"] == "18.0000"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(TaxRate.id))) == 9


async def test_classification_transition_requires_coordinated_dependent_bindings(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    current = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    generation = guard(current.json())
    classification = {
        **generation,
        **EVIDENCE,
        "valid_from": "2091-01-01",
        "code_system": "HSN",
        "code": "1234",
        "item_kind": "GOODS",
        "description": "Revised evidence",
        "supersedes_id": str(ids["tax_classification"]),
        "expected_previous_version": 1,
    }
    invalid = await client.post(
        root + "/tax-classifications", headers=command_headers(auth), json=classification
    )
    assert invalid.status_code == 409, invalid.text
    changes = [{"key": "classification", "kind": "CLASSIFICATION", "definition": classification}]
    changes += [
        {
            "key": direction,
            "kind": "BINDING",
            "definition": {
                **generation,
                "valid_from": "2091-01-01",
                "scope_id": str(ids["catalog_tax_scope"]),
                "direction": direction,
                "bundle": "CLASSIFICATION",
                "mode": "OVERRIDE",
                "classification_id": {"key": "classification"},
                "supersedes_id": str(ids["binding_" + direction + "_CLASSIFICATION"]),
                "expected_previous_version": 1,
            },
        }
        for direction in ("SALE", "PURCHASE")
    ]
    await release(
        client,
        root,
        auth,
        {**generation, "change_reason": "Classification transition", "changes": changes},
    )
    result = await client.post(
        root + "/tax-configurations/resolve", headers=auth, json=query(ids, as_of="2091-01-01")
    )
    assert result.status_code == 200 and result.json()["status"] == "COMPLETE", result.text
    assert result.json()["classification_id"] != str(ids["tax_classification"])


async def test_release_preview_cannot_authorize_changed_input(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    current = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    generation = guard(current.json())
    body = {**generation, "change_reason": "Synthetic revision", "changes": rates(ids, generation)}
    preview = await client.post(root + "/tax-release-previews", headers=auth, json=body)
    assert preview.status_code == 200, preview.text
    body["changes"] = rates(ids, generation, "18")
    result = await client.post(
        root + "/tax-releases",
        headers=command_headers(auth),
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert result.status_code == 409, result.text


async def test_future_classification_expiry_blocks_activation(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    with tenant_scope(tenant_a):
        async with factory() as db, db.begin():
            for model, key in (
                (TaxClassification, "tax_classification"),
                (CatalogTaxBinding, "binding_SALE_CLASSIFICATION"),
                (CatalogTaxBinding, "binding_PURCHASE_CLASSIFICATION"),
            ):
                value = await db.get(model, ids[key])
                assert isinstance(value, TaxClassification | CatalogTaxBinding)
                value.valid_to = DATE
    result = await client.post(
        root + "/items/" + str(ids["item"]) + "/activation-preview",
        headers=auth,
        json={"as_of": str(DATE)},
    )
    assert result.status_code == 200 and not result.json()["eligible"], result.text
    assert "tax:SALE:2090-01-02:classification" in result.json()["missing"]


async def test_native_classification_applicability_rejects_unrelated_code(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    async with changed(
        factory, tenant_a, TaxClassification, ids["tax_classification"], code="5678"
    ):
        result = await client.post(
            root + "/tax-configurations/resolve", headers=auth, json=query(ids)
        )
        assert result.status_code == 409, result.text
