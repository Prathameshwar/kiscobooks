import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.configuration import (
    NumericDefault,
    OptionSetting,
    narrow_quantity_default,
    resolve_option,
)
from catalog.domain.units import QuantityRule
from catalog.models.configuration import CONFIGURATION_MODELS, ProductConfigurationRevision
from catalog.schemas.configuration import EntryOptions, NumericInput, ScopeCreate
from tests.configuration_factories import setup_configuration
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_configuration_publication_resolution_and_replay(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, _ = await setup_configuration(factory, tenant_a)
    base = f"/v1/companies/{company}"
    scope = await client.post(
        base + "/product-configuration-scopes",
        headers=command_headers(auth),
        json={"scope_kind": "COMPANY"},
    )
    assert scope.status_code == 201, scope.text
    body = {
        "scope_id": scope.json()["id"],
        "effective_from": "2090-01-01",
        "change_reason": "Initial defaults",
        "options": {"brand_mode": "REQUIRED"},
        "numeric_defaults": [
            {"dimension": "COUNT", "quantity_decimal_places": 0, "quantity_increment": "1"}
        ],
    }
    receipt = command_headers(auth)
    draft = await client.post(base + "/product-configurations", headers=receipt, json=body)
    assert draft.status_code == 201, draft.text
    assert (
        await client.post(base + "/product-configurations", headers=receipt, json=body)
    ).headers["Idempotency-Replayed"] == "true"
    path = base + "/product-configurations/" + draft.json()["id"]
    preview = await client.get(path + "/preview", headers=auth)
    assert preview.status_code == 200, preview.text
    token = preview.json()
    publish = {
        "expected_version": token["draft_version"],
        "expected_generation": token["policy_generation"],
        "expected_source_version": token["source_version"],
    }
    receipt = command_headers(auth)
    revision = await client.post(path + "/publish", headers=receipt, json=publish)
    assert revision.status_code == 201, revision.text
    assert (await client.post(path + "/publish", headers=receipt, json=publish)).headers[
        "Idempotency-Replayed"
    ] == "true"
    effective = await client.get(
        base + "/product-configuration/effective",
        headers=auth,
        params={"as_of": "2090-01-01", "kind": "GOODS"},
    )
    assert effective.status_code == 200, effective.text
    assert effective.json()["options"]["brand_mode"] == "REQUIRED"
    assert effective.json()["sources"][0]["revision_id"] == revision.json()["id"]
    assert effective.json()["activation_available"] is True
    before = await client.get(
        base + "/catalog-defaults", headers=auth, params={"as_of": "2089-12-31", "kind": "GOODS"}
    )
    assert before.status_code == 200 and before.json()["sources"] == []
    assert (
        await client.patch(
            path,
            headers=command_headers(auth),
            json={"expected_version": 2, "change_reason": "Rewrite history"},
        )
    ).status_code == 409
    for route in (
        "/product-configuration-scopes",
        "/product-configuration-scopes/" + scope.json()["id"] + "/drafts",
        "/product-configuration-scopes/" + scope.json()["id"] + "/revisions",
    ):
        page = await client.get(base + route, headers=auth, params={"limit": 1})
        assert page.status_code == 200, page.text
        assert "options" not in page.json()["items"][0]
    with tenant_scope(tenant_a):
        async with factory() as db:
            for model in CONFIGURATION_MODELS:
                count = await db.scalar(select(func.count(model.id)))
                assert count is not None and count >= (
                    0 if model.__tablename__ == "product_numeric_default" else 1
                )
            assert await db.scalar(select(func.count(ProductConfigurationRevision.id))) == 1


async def test_configuration_scope_auth_and_stale_publication(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, product = await setup_configuration(factory, tenant_a)
    other, _, foreign, _ = await setup_configuration(factory, tenant_a)
    base = f"/v1/companies/{company}"
    assert (
        await client.post(
            base + "/product-configuration-scopes",
            json={"scope_kind": "COMPANY"},
            headers={"Idempotency-Key": str(uuid7())},
        )
    ).status_code == 401
    read_only = headers(
        company, tenant=tenant_a, user=user, permission=["product_configuration.read"]
    )
    assert (
        await client.post(
            base + "/product-configuration-scopes",
            json={"scope_kind": "COMPANY"},
            headers=command_headers(read_only),
        )
    ).status_code == 403
    invalid = await client.post(
        base + "/product-configuration-scopes",
        headers=command_headers(auth),
        json={"scope_kind": "SKU", "item_id": product["product_type_revision_id"]},
    )
    assert invalid.status_code == 422  # Retired ownership is rejected before resolving an owner.
    scope = await client.post(
        base + "/product-configuration-scopes",
        headers=command_headers(auth),
        json={"scope_kind": "COMPANY"},
    )
    assert scope.status_code == 201, scope.text
    foreign_read = await client.get(
        f"/v1/companies/{other}/product-configuration-scopes/{scope.json()['id']}", headers=foreign
    )
    assert foreign_read.status_code == 403
    draft = await client.post(
        base + "/product-configurations",
        headers=command_headers(auth),
        json={
            "scope_id": scope.json()["id"],
            "effective_from": "2090-01-01",
            "change_reason": "Initial",
        },
    )
    assert draft.status_code == 201, draft.text
    path = base + "/product-configurations/" + draft.json()["id"]
    token = (await client.get(path + "/preview", headers=auth)).json()
    updated = await client.patch(
        path,
        headers=command_headers(auth),
        json={"expected_version": 1, "options": {"brand_mode": "REQUIRED"}},
    )
    assert updated.status_code == 200, updated.text
    stale = await client.post(
        path + "/publish",
        headers=command_headers(auth),
        json={
            "expected_version": 2,
            "expected_generation": token["policy_generation"],
            "expected_source_version": token["source_version"],
        },
    )
    assert stale.status_code == 409
    bad = await client.patch(
        path,
        headers=command_headers(auth),
        json={
            "expected_version": 2,
            "numeric_defaults": [
                {"dimension": "COUNT", "quantity_decimal_places": 0, "quantity_increment": "0.5"}
            ],
        },
    )
    assert bad.status_code == 422


def test_configuration_native_requirements_and_exact_grids() -> None:
    assert (
        resolve_option((OptionSetting("OPTIONAL", False),), baseline=OptionSetting("REQUIRED")).mode
        == "REQUIRED"
    )
    from billing_platform.errors import ValidationFailedError

    with pytest.raises(ValidationFailedError):
        resolve_option((OptionSetting("DISABLED"),), baseline=OptionSetting("REQUIRED"))
    assert narrow_quantity_default(
        QuantityRule(2, Decimal("0.20")), QuantityRule(2, Decimal("0.25"))
    ).increment == Decimal("1")
    assert NumericDefault("COUNT").dimension == "COUNT"
    from pydantic import ValidationError

    with pytest.raises((ValidationError, ValidationFailedError)):
        EntryOptions(brand_mode="OPTIONAL")
    with pytest.raises(ValidationError):
        ScopeCreate.model_validate({"scope_kind": "COMPANY", "family_id": uuid7()})
    with pytest.raises(ValueError):
        NumericInput.model_validate(
            {"dimension": "TIME", "quantity_decimal_places": 2, "quantity_increment": 0.25}
        )
