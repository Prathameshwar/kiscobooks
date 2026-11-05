import uuid

import httpx
import pytest
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.configuration import CONFIGURATION_MODELS
from catalog.models.product_definitions import PRODUCT_DEFINITION_MODELS
from tests.product_definition_factories import seed_definitions
from tests.test_api import headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_native_definition_metadata_keeps_generated_identity_fields_readonly(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    generated = {
        "row_version",
        "owner_id",
        "latest_revision",
        "revision",
        "published_at",
        "source_draft_id",
        "draft_id",
        "revision_id",
        "preview_hash",
        "policy_generation",
        "source_version",
        "primary_slot",
        "combination_hash",
        "canonical_combination",
        "adoption_id",
    }
    for model in (*CONFIGURATION_MODELS, *PRODUCT_DEFINITION_MODELS):
        response = await client.get(
            f"/v1/companies/{company}/entities/catalog.{model.__tablename__}/field-set",
            headers=auth,
        )
        assert response.status_code == 200, response.text
        fields = {row["key"]: row for row in response.json()["fields"]}
        assert fields, model.__tablename__
        for key in generated & fields.keys():
            assert fields[key]["writable"] is False, (model.__tablename__, key)
