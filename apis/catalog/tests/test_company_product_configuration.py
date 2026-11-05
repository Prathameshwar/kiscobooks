"""Company-only authoring keeps immutable configuration history and native guards."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    Outbox,
    ProductConfigurationAdoption,
    ProductConfigurationAdoptionSource,
    ProductFamily,
    ProductTypeRevision,
)
from catalog.models.configuration import ProductConfigurationDraft, ProductConfigurationScope
from catalog.schemas.configuration import ScopeCreate
from tests.configuration_factories import seed_legacy_configuration, setup_configuration
from tests.product_definition_factories import seed_definitions
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("kind", ["TYPE", "GROUP", "FAMILY", "SKU"])
async def test_retired_configuration_is_history_and_never_a_new_default(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    kind: str,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    with tenant_scope(tenant_a):
        async with factory() as db:
            family = await db.get(ProductFamily, ids["product_family"])
            assert family is not None
            product_type = await db.get(ProductTypeRevision, family.product_type_revision_id)
            assert product_type is not None
            owner = {
                "TYPE": product_type.product_type_id,
                "GROUP": ids["item_group"],
                "FAMILY": family.id,
                "SKU": ids["item"],
            }[kind]
    scope_id, draft_id, revision_id = await seed_legacy_configuration(
        factory,
        tenant_a,
        company,
        kind,
        owner,
        options={"barcode_mode": "OPTIONAL", "barcode_default": True},
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                ProductConfigurationAdoptionSource(
                    tenant_id=tenant_a,
                    company_id=company,
                    adoption_id=ids["product_configuration_adoption"],
                    scope_id=scope_id,
                    revision_id=revision_id,
                )
            )
    query = {"as_of": "2090-01-01", "kind": "GOODS", "item_id": str(ids["item"])}
    current = await client.get(
        root + "/product-configuration/effective", headers=auth, params=query
    )
    assert current.status_code == 200, current.text
    assert [source["scope_kind"] for source in current.json()["sources"]] == ["COMPANY"]
    assert current.json()["options"]["barcode_default"] is False
    pinned = await client.get(
        root + f"/items/{ids['item']}/configuration", headers=auth, params={"as_of": "2090-01-01"}
    )
    assert pinned.status_code == 200, pinned.text
    assert [source["scope_kind"] for source in pinned.json()["sources"]] == ["COMPANY", kind]
    assert pinned.json()["options"]["barcode_default"] is True
    async with changed(
        factory,
        tenant_a,
        ProductConfigurationAdoption,
        ids["product_configuration_adoption"],
        resolution_version=2,
    ):
        invalid = await client.get(
            root + f"/items/{ids['item']}/configuration",
            headers=auth,
            params={"as_of": "2090-01-01"},
        )
        assert invalid.status_code == 409, invalid.text
    for path in (
        f"/product-configurations/{draft_id}",
        f"/product-configuration-revisions/{revision_id}",
        f"/product-configuration-scopes/{scope_id}/revisions",
    ):
        assert (await client.get(root + path, headers=auth)).status_code == 200
    retired = await client.post(
        root + "/product-configurations",
        headers=command_headers(auth),
        json={
            "scope_id": str(scope_id),
            "effective_from": "2091-01-01",
            "change_reason": "Retired write",
        },
    )
    assert retired.status_code == 422, retired.text
    edit = await client.patch(
        root + f"/product-configurations/{draft_id}",
        headers=command_headers(auth),
        json={"expected_version": 1, "change_reason": "Retired edit"},
    )
    assert edit.status_code == 422, edit.text
    publish = await client.post(
        root + f"/product-configurations/{draft_id}/publish",
        headers=command_headers(auth),
        json={"expected_version": 1, "expected_generation": 1, "expected_source_version": 1},
    )
    assert publish.status_code == 422, publish.text
    assert (
        await client.get(root + f"/product-configurations/{draft_id}/preview", headers=auth)
    ).status_code == 422
    listed = await client.get(root + "/product-configuration-scopes", headers=auth)
    assert [row["scope_kind"] for row in listed.json()["items"]] == ["COMPANY"]
    assert (
        await client.get(
            root + "/product-configuration-scopes", headers=auth, params={"scope_kind": kind}
        )
    ).status_code == 422
    proposed = await client.get(
        root + f"/items/{ids['item']}/configuration-adoption/preview",
        headers=auth,
        params={"as_of": "2090-01-01"},
    )
    assert proposed.status_code == 200, proposed.text
    assert str(revision_id) not in proposed.json()["proposed_revision_ids"]
    assert str(revision_id) in proposed.json()["current_revision_ids"]


@pytest.mark.parametrize("kind", ["TYPE", "GROUP", "FAMILY", "SKU"])
def test_retired_configuration_scope_is_rejected(kind: str) -> None:
    field = {
        "TYPE": "product_type_id",
        "GROUP": "group_id",
        "FAMILY": "family_id",
        "SKU": "item_id",
    }[kind]
    with pytest.raises(ValidationError):
        ScopeCreate.model_validate({"scope_kind": kind, field: uuid.uuid4()})


async def test_company_draft_creates_scope_atomically_and_replays(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, auth, _ = await setup_configuration(factory, tenant_a)
    base = f"/v1/companies/{company}"
    body = {"effective_from": "2090-01-01", "change_reason": "Company defaults"}
    receipt = command_headers(auth)
    result = await client.post(base + "/product-configurations/company", headers=receipt, json=body)
    assert result.status_code == 201, result.text
    replay = await client.post(base + "/product-configurations/company", headers=receipt, json=body)
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == result.json()["id"]
    assert replay.headers["Idempotency-Replayed"] == "true"
    scope = await client.get(base + "/product-configuration-scopes", headers=auth)
    assert scope.status_code == 200, scope.text
    assert len(scope.json()["items"]) == 1
    assert scope.json()["items"][0]["scope_kind"] == "COMPANY"
    assert result.json()["scope_id"] == scope.json()["items"][0]["id"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductConfigurationScope.id))) == 1
            assert await db.scalar(select(func.count(ProductConfigurationDraft.id))) == 1

    path = base + "/product-configurations/" + result.json()["id"]
    preview = await client.get(path + "/preview", headers=auth)
    assert preview.status_code == 200, preview.text
    review = preview.json()
    published = await client.post(
        path + "/publish",
        headers=command_headers(auth),
        json={
            "expected_version": review["draft_version"],
            "expected_generation": review["policy_generation"],
            "expected_source_version": review["source_version"],
        },
    )
    assert published.status_code == 201, published.text
    next_draft = await client.post(
        base + "/product-configurations/company",
        headers=command_headers(auth),
        json={**body, "effective_from": "2090-01-02"},
    )
    assert next_draft.status_code == 201, next_draft.text
    assert next_draft.json()["scope_id"] == result.json()["scope_id"]


async def test_company_draft_preserves_authority_and_rolls_back_invalid_references(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth, _ = await setup_configuration(factory, tenant_a)
    other, _, foreign, product = await setup_configuration(factory, tenant_a)
    path = f"/v1/companies/{company}/product-configurations/company"
    body = {"effective_from": "2090-01-01", "change_reason": "Company defaults"}
    assert (await client.post(path, json=body)).status_code == 401
    read_only = headers(
        company, tenant=tenant_a, user=user, permission=["product_configuration.read"]
    )
    assert (
        await client.post(path, headers=command_headers(read_only), json=body)
    ).status_code == 403
    assert (await client.post(path, headers=command_headers(foreign), json=body)).status_code == 403
    invalid = {
        **body,
        "profiles": {
            "goods_type_revision_mode": "VALUE",
            "goods_type_revision_id": product["product_type_revision_id"],
        },
    }
    result = await client.post(path, headers=command_headers(auth), json=invalid)
    assert result.status_code == 403, result.text
    for extra in ({"scope_id": str(other)}, {"scope_kind": "TYPE"}, {"group_id": str(other)}):
        result = await client.post(path, headers=command_headers(auth), json={**body, **extra})
        assert result.status_code == 422, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductConfigurationScope.id))) == 0
            assert await db.scalar(select(func.count(ProductConfigurationDraft.id))) == 0
            assert await db.scalar(select(func.count(Outbox.id))) == 0


async def test_first_company_draft_rechecks_field_denies_and_ignores_retired_owner_fields(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    from tests.test_master_reference_policy import policy

    company, user, auth, _ = await setup_configuration(factory, tenant_a)
    root = f"/v1/companies/{company}"
    body = {"effective_from": "2090-01-01", "change_reason": "Company settings"}
    await policy(
        factory,
        tenant_a,
        company,
        user,
        "catalog.product_entry_option_policy",
        "barcode_mode",
        "write",
    )
    denied = await client.post(
        root + "/product-configurations/company", headers=command_headers(auth), json=body
    )
    assert denied.status_code == 403, denied.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductConfigurationScope.id))) == 0
            assert await db.scalar(select(func.count(ProductConfigurationDraft.id))) == 0
            assert await db.scalar(select(func.count(Outbox.id))) == 0
    # Replacing the signed policy removes the child deny and protects the retired owner field.
    await policy(
        factory,
        tenant_a,
        company,
        user,
        "catalog.product_configuration_scope",
        "group_id",
        "read",
        version=4,
    )
    receipt = command_headers(auth)
    saved = await client.post(root + "/product-configurations/company", headers=receipt, json=body)
    assert saved.status_code == 201, saved.text
    current = await client.get(
        root + "/product-configuration/effective",
        headers=auth,
        params={"kind": "GOODS", "as_of": "2090-01-01"},
    )
    assert current.status_code == 200, current.text
    await policy(
        factory,
        tenant_a,
        company,
        user,
        "catalog.product_entry_option_policy",
        "barcode_mode",
        "write",
        version=5,
    )
    revoked_replay = await client.post(
        root + "/product-configurations/company", headers=receipt, json=body
    )
    assert revoked_replay.status_code == 403, revoked_replay.text
