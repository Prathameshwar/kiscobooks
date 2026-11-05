import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.gateway import decode_actor_context
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    ItemGroup,
    ItemGroupParent,
    ProductEntryOptionPolicy,
    ProductFamily,
    ProductTypeRevision,
)
from catalog.schemas.configuration import EffectiveQuery
from catalog.tasks.configuration_resolution import resolve
from tests.configuration_factories import publish_configuration
from tests.conftest import ACTOR_SECRET
from tests.product_definition_factories import seed_definitions
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_configuration_provenance_checks_type_ancestry_and_unique_source_pins(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    path = root + "/product-configuration/effective"
    params = {"as_of": "2090-01-01", "kind": "GOODS"}
    with tenant_scope(tenant_a):
        async with factory() as db:
            family = await db.get(ProductFamily, ids["product_family"])
            assert family is not None
            revision = await db.get(ProductTypeRevision, family.product_type_revision_id)
            assert revision is not None
            revision_id, type_id = revision.id, revision.product_type_id
    for extra, status in (
        ({"family_id": str(ids["product_family"]), "product_type_id": str(uuid7())}, 403),
        ({"product_type_id": str(type_id), "kind": "SERVICE"}, 409),
        ({"group_id": str(ids["item_group"]), "as_of": "2089-01-01"}, 409),
    ):
        response = await client.get(path, headers=auth, params={**params, **extra})
        assert response.status_code == status, response.text
    async with changed(
        factory,
        tenant_a,
        ProductTypeRevision,
        revision_id,
        require_brand=True,
        require_manufacturer=True,
        allow_variants=False,
    ):
        required = await client.get(
            path, headers=auth, params={**params, "family_id": str(ids["product_family"])}
        )
        assert required.status_code == 200, required.text
        assert required.json()["options"]["brand_mode"] == "REQUIRED"
        assert required.json()["options"]["manufacturer_mode"] == "REQUIRED"
        assert required.json()["options"]["variants_mode"] == "DISABLED"
    async with changed(factory, tenant_a, ProductTypeRevision, revision_id, published_at=None):
        response = await client.get(
            path, headers=auth, params={**params, "product_type_id": str(type_id)}
        )
        assert (
            response.status_code == 409 and "no published requirements" in response.text
        ), response.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            other = ItemGroup(
                tenant_id=tenant_a,
                company_id=company,
                code="CYCLE",
                name="Cycle",
                allowed_kind="GOODS",
            )
            db.add(other)
            await db.flush()
            db.add(
                ItemGroupParent(
                    tenant_id=tenant_a,
                    company_id=company,
                    group_id=other.id,
                    parent_group_id=ids["item_group"],
                    valid_from=dt.date(2090, 1, 1),
                )
            )
            other_id = other.id
    async with changed(
        factory, tenant_a, ItemGroupParent, ids["item_group_parent"], parent_group_id=other_id
    ):
        response = await client.get(
            path, headers=auth, params={**params, "group_id": str(ids["item_group"])}
        )
        assert response.status_code == 409 and "cyclic" in response.text, response.text
    _, second = await publish_configuration(
        client,
        root,
        auth,
        scope_id=str(ids["product_configuration_scope"]),
        effective_from="2091-01-01",
    )
    actor = decode_actor_context(
        auth["x-actor-context"], auth["x-actor-signature"], ACTOR_SECRET.encode()
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            with pytest.raises(ConflictError, match="conflicting configuration revisions"):
                await resolve(
                    db,
                    actor,
                    company,
                    EffectiveQuery(as_of=dt.date(2091, 1, 1), kind="GOODS"),
                    revisions=(ids["product_configuration_revision"], uuid.UUID(second["id"])),
                )
    await policy(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        "catalog.product_configuration_scope",
        "owner_id",
        "read",
    )
    denied = await client.get(
        root + f"/product-configuration-scopes/{ids['product_configuration_scope']}", headers=auth
    )
    assert denied.status_code == 403, denied.text


async def test_incomplete_native_configuration_is_never_rendered_as_complete(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.get(ProductEntryOptionPolicy, ids["product_entry_option_policy"])
            assert row is not None
            await db.delete(row)
    response = await client.get(
        f"/v1/companies/{company}/product-configuration-revisions/{ids['product_configuration_revision']}",
        headers=auth,
    )
    assert response.status_code == 409 and "incomplete" in response.text, response.text
