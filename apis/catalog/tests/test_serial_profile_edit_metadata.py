import uuid

import httpx
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.profile_factories import auth


async def test_identifier_profile_code_is_readonly_only_on_update(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    path = f"/v1/companies/{company}/entities/catalog.identifier_profile/field-set"
    for operation, writable in (("create", True), ("update", False)):
        response = await client.get(path, headers=current, params={"operation": operation})
        assert response.status_code == 200, response.text
        code = next(field for field in response.json()["fields"] if field["key"] == "code")
        assert code["writable"] is writable
