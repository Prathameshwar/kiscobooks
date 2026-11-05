"""Bulk attribute imports retain native child-version and review protections."""

import uuid

import pytest
from billing_platform.errors import ConflictError
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.attribute_factories import seed_attributes
from tests.bulk_factories import post, run
from tests.test_product_authoring import create_product
from tests.test_product_integrity_fixes import put

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("edit_after_review", [False, True])
async def test_bulk_family_attributes_respect_default_sku_version(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    edit_after_review: bool,
) -> None:
    company, user, auth, product = await create_product(client, factory, tenant_a)
    ids = await seed_attributes(factory, tenant_a, company)
    root = f"/v1/companies/{company}"
    family = root + f"/product-families/{product['family']['id']}/attributes"
    item = root + f"/items/{product['default_item']['id']}/attributes"
    declaration = {"definition_id": str(ids["attribute_definition"]), "position": 0}
    value = {
        "definition_id": str(ids["attribute_definition"]),
        "value_type": "TEXT",
        "value_text": "Reviewed",
    }
    await put(client, family, auth, {"expected_version": 1, "attributes": [declaration]})
    jobs = root + "/bulk-jobs"
    job = await post(
        client,
        jobs,
        auth,
        "",
        {
            "format": "JSON",
            "mode": "UPDATE_ONLY",
            "records": [
                {
                    "key": "attributes",
                    "change_set": "family",
                    "resource": "product_family",
                    "action": "CONFIGURE_ATTRIBUTES",
                    "target": {"id": product["family"]["id"]},
                    "data": {
                        "attributes": [declaration],
                        "default_item_attributes": [value],
                        "expected_default_item_version": 1,
                    },
                }
            ],
        },
    )
    await post(
        client, jobs, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "READY"
    reviewed = (await client.get(jobs + "/" + job["id"], headers=auth)).json()
    if edit_after_review:
        await put(
            client,
            item,
            auth,
            {"expected_version": 1, "attributes": [{**value, "value_text": "New edit"}]},
        )
    await post(
        client,
        jobs,
        auth,
        f"/{job['id']}/commit",
        {
            "expected_version": reviewed["row_version"],
            "selection_digest": reviewed["selection_digest"],
        },
    )
    if edit_after_review:
        # API edits invalidate the entire reviewed generation before record execution.
        with pytest.raises(ConflictError, match="review again"):
            await run(factory, tenant_a, company, user, job["id"])
    else:
        assert await run(factory, tenant_a, company, user, job["id"]) == "SUCCEEDED"
    rows = (await client.get(item, headers=auth)).json()["items"]
    detail = (await client.get(item + "/" + rows[0]["id"], headers=auth)).json()
    assert detail["value_text"] == ("New edit" if edit_after_review else "Reviewed")
