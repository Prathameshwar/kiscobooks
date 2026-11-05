import os
import re

import pytest_asyncio
from billing_platform.db import create_engine
from sqlalchemy.engine import make_url

from tests.test_api_tax_registration_rules import MANAGE, _create, world  # noqa: F401


@pytest_asyncio.fixture
async def engine():
    url = os.environ.get("GST_OWNER_TEST_URL", "sqlite+aiosqlite:///:memory:")
    if url.startswith("sqlite"):
        from identity.metadata import service_metadata

        database = create_engine(url)
        async with database.begin() as connection:
            await connection.run_sync(service_metadata().create_all)
    else:
        parsed = make_url(url)
        assert parsed.host in {"localhost", "127.0.0.1", "::1"}
        assert re.fullmatch("identity_test_[0-9a-f]{32}", parsed.database)
        database = create_engine(url)
    try:
        yield database
    finally:
        await database.dispose()


async def test_dated_preferences_scope_overlap_and_immutable_close(client, world):  # noqa: F811
    registration = await _create(client, world)
    path = f"/v1/companies/{world.company}/gst-filing-preferences"
    body = {
        "registration_id": registration["id"],
        "frequency": "MONTHLY",
        "valid_from": "2026-10-01",
    }
    created = await client.post(path, headers=world.headers(MANAGE), json=body)
    assert created.status_code == 201, created.text
    overlap = await client.post(path, headers=world.headers(MANAGE), json=body)
    assert overlap.status_code == 409
    foreign = await client.post(
        f"/v1/companies/{world.other_company}/gst-filing-preferences",
        headers=world.headers(MANAGE),
        json=body,
    )
    assert foreign.status_code == 404
    denied = await client.post(path, headers=world.headers("company.read"), json=body)
    assert denied.status_code == 403
    closed = await client.patch(
        path + "/" + created.json()["id"],
        headers=world.headers(MANAGE),
        json={"valid_to": "2027-01-01"},
    )
    assert closed.status_code == 200, closed.text
    rewritten = await client.patch(
        path + "/" + created.json()["id"],
        headers=world.headers(MANAGE),
        json={"valid_to": "2027-02-01"},
    )
    assert rewritten.status_code == 409
    quarterly = await client.post(
        path,
        headers=world.headers(MANAGE),
        json={
            "registration_id": registration["id"],
            "frequency": "QRMP",
            "valid_from": "2027-01-01",
        },
    )
    assert quarterly.status_code == 201, quarterly.text
    await check_setup_metadata_is_scoped_and_readers_cannot_manage(client, world)


async def check_setup_metadata_is_scoped_and_readers_cannot_manage(client, world):  # noqa: F811
    path = f"/v1/companies/{world.company}/gst-registration-setup"
    response = await client.get(path, headers=world.headers("company.read", MANAGE))
    assert response.status_code == 200, response.text
    assert response.json()["can_manage"] is True
    assert response.json()["country_code"] == "IN"
    assert response.json()["regimes"]["regular"]
    assert response.json()["create_schema"]["properties"]["number"]["maxLength"] == 40
    reader = await client.get(path, headers=world.headers("company.read"))
    assert reader.status_code == 200 and reader.json()["can_manage"] is False
    foreign = await client.get(
        f"/v1/companies/{world.other_company}/gst-registration-setup",
        headers=world.headers("company.read", company=world.company),
    )
    assert foreign.status_code == 403
