"""Bulk review captures one coherent guard for all members of a tax release."""

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.tax_factories import query, seed_tax
from tests.test_bulk_products_prices import reviewed_commit
from tests.test_tax_governance import rates

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_bulk_tax_release_uses_the_reviewed_generation_for_every_change(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    # Bulk owns version capture, including these nested placeholders.
    placeholder = {"expected_generation": 999, "expected_source_version": 999}
    await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        auth,
        {
            "format": "JSON",
            "records": [
                {
                    "key": "tax",
                    "change_set": "tax",
                    "resource": "tax_release",
                    "action": "PUBLISH",
                    "data": {
                        **placeholder,
                        "change_reason": "Reviewed bulk schedule",
                        "changes": rates(ids, placeholder),
                    },
                }
            ],
        },
    )
    result = await client.post(
        root + "/tax-configurations/resolve", headers=auth, json=query(ids, as_of="2091-01-01")
    )
    assert result.status_code == 200 and result.json()["status"] == "COMPLETE", result.text
    interstate = next(
        entry for entry in result.json()["rates"] if entry["applicability"] == "INTER_STATE"
    )
    assert interstate["components"][0]["percentage"] == "12.0000"
