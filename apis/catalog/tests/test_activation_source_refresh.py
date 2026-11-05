"""Equivalent Identity refreshes must not make reviewed activation impossible."""

import datetime as dt

import pytest

from catalog.tasks import activation, activation_tax, product_adoption
from tests.tax_factories import DATE, seed_tax
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("operation", ["activation", "adoption"])
@pytest.mark.parametrize("change", ["none", "policy", "values"])
async def test_activation_rechecks_values_after_source_refresh(
    client, factory, tenant_a, monkeypatch, change, operation
):
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    owner = activation if operation == "activation" else product_adoption
    original = owner.requirements
    calls = 0

    async def refreshed(*args, **kwargs):
        nonlocal calls
        definition, config = await original(*args, **kwargs)
        calls += 1
        updates = {"source_version": config.source_version + calls}
        if change == "policy" and calls > 1:
            updates["policy_generation"] = config.policy_generation + 1
        if change == "values" and calls > 1:
            updates["options"] = config.options.model_copy(
                update={"barcode_default": not config.options.barcode_default}
            )
        return definition, config.model_copy(update=updates)

    monkeypatch.setattr(owner, "requirements", refreshed)
    if operation == "activation":
        original_tax = activation_tax.resolve

        async def refreshed_tax(*args, **kwargs):
            result = await original_tax(*args, **kwargs)
            return result.model_copy(update={"source_version": result.source_version + calls})

        monkeypatch.setattr(activation_tax, "resolve", refreshed_tax)
    route = root + "/items/" + str(ids["item"])
    preview = (
        await client.post(route + "/activation-preview", headers=auth, json={"as_of": str(DATE)})
        if operation == "activation"
        else await client.get(
            route + "/configuration-adoption/preview", headers=auth, params={"as_of": str(DATE)}
        )
    )
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    keys = ["expected_version", "preview_token"]
    if operation == "activation":
        keys.append("expected_family_version")
    body = {"as_of": str(DATE), **{key: preview.json()[key] for key in keys}}
    response = await client.post(
        route + ("/activate" if operation == "activation" else "/configuration-adoption"),
        headers=command_headers(auth),
        json=body,
    )
    assert response.status_code == (200 if change == "none" else 409), response.text
    detail = await client.get(route, headers=auth)
    assert detail.json()["status"] == (
        "ACTIVE" if change == "none" and operation == "activation" else "DRAFT"
    )
