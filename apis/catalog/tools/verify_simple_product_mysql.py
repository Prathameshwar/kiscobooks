"""Verify simple products and authoring migrations in a disposable loopback schema."""

import asyncio
import uuid

import httpx
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from pydantic import SecretStr
from sqlalchemy import Connection

from catalog.config import Settings
from catalog.main import create_app
from catalog.metadata import service_metadata
from tests.attribute_factories import seed_attributes
from tests.conftest import ACTOR_SECRET
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_product_mode import (
    set_mode,
    test_mode_default_read_does_not_insert_and_transition_replays,
)
from tests.test_product_mode_seed import test_roster_seed_dry_run_resume_and_tenant_isolation
from tests.test_simple_product_features import (
    test_simple_initial_units_and_single_metadata,
    test_simple_specs_work_but_axes_are_blocked,
)
from tests.test_simple_products import simple_input, test_simple_create_read_edit_and_replay
from tools.mysql_smoke import run_verifier


async def mode_axis_race(client, factory) -> None:
    tenant = uuid7()
    company, user, _, legacy = await setup_product(factory, tenant, advanced=False)
    auth = headers(company, tenant=tenant, user=user, permission=sorted(CATALOG_PERMISSIONS))
    ids = await seed_attributes(factory, tenant, company)
    root = f"/v1/companies/{company}"
    created = await client.post(
        root + "/products", headers=command_headers(auth), json=simple_input(legacy)
    )
    assert created.status_code == 201, created.text
    product = created.json()
    switched, _, _ = await set_mode(client, company, auth, True)
    assert switched.status_code == 200, switched.text
    mode_path = root + "/product-configuration/authoring"
    latest = (await client.get(mode_path, headers=auth)).json()
    disabled = {
        "expected_version": latest["row_version"],
        "expected_generation": latest["policy_generation"],
        "product_family_sku_enabled": False,
        "change_reason": "Concurrent mode change",
    }
    preview = await client.post(mode_path + "/preview", headers=auth, json=disabled)
    assert preview.status_code == 200, preview.text
    result = await asyncio.gather(
        client.patch(
            mode_path,
            headers=command_headers(auth),
            json={**disabled, "preview_token": preview.json()["preview_token"]},
        ),
        client.put(
            root + "/products/" + product["id"] + "/attributes",
            headers=command_headers(auth),
            json={
                "revision": product["revision"],
                "authoring_version": latest["row_version"],
                "attributes": [
                    {
                        "definition_id": str(ids["attribute_definition"]),
                        "is_axis": True,
                        "is_required": True,
                        "position": 0,
                        "options": [str(ids["attribute_option"])],
                    }
                ],
                "values": [
                    {
                        "definition_id": str(ids["attribute_definition"]),
                        "value_type": "TEXT",
                        "option_id": str(ids["attribute_option"]),
                    }
                ],
            },
        ),
    )
    assert sorted(response.status_code for response in result) == [200, 409], [
        response.text for response in result
    ]


async def verify(url: str) -> dict[str, object]:
    app = create_app(Settings(database_url=url, actor_signing_secret=SecretStr(ACTOR_SECRET)))
    try:
        async with app.router.lifespan_context(app):
            async with app.state.engine.connect() as connection:

                def differences(sync: Connection) -> list[object]:
                    return list(
                        compare_metadata(MigrationContext.configure(sync), service_metadata())
                    )

                drift = await connection.run_sync(differences)
                if drift:
                    raise AssertionError(f"migration/model drift: {drift}")
            factory = app.state.session_factory
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://catalog.test"
            ) as client:
                await test_mode_default_read_does_not_insert_and_transition_replays(
                    client, factory, uuid7()
                )
                await test_simple_create_read_edit_and_replay(client, factory, uuid7(), "GOODS")
                await test_simple_create_read_edit_and_replay(client, factory, uuid7(), "SERVICE")
                await test_simple_initial_units_and_single_metadata(client, factory, uuid7())
                await test_simple_specs_work_but_axes_are_blocked(client, factory, uuid7())
                await test_roster_seed_dry_run_resume_and_tenant_isolation(
                    factory, uuid7(), uuid7()
                )
                tenant = uuid7()
                company, _, auth, legacy = await setup_product(factory, tenant, advanced=False)
                route = f"/v1/companies/{company}/products"
                receipt, body = command_headers(auth), simple_input(legacy)
                results = await asyncio.gather(
                    *(client.post(route, headers=receipt, json=body) for _ in range(2))
                )
                assert [response.status_code for response in results] == [201, 201], [
                    response.text for response in results
                ]
                assert uuid.UUID(results[0].json()["id"]) == uuid.UUID(results[1].json()["id"])
                assert {response.headers["Idempotency-Replayed"] for response in results} == {
                    "true",
                    "false",
                }
                for _ in range(3):
                    await mode_axis_race(client, factory)
        return {
            "model_parity": "PASS",
            "simple_product_workflows": 7,
            "concurrent_idempotency": "PASS",
            "mode_axis_races": 3,
        }
    finally:
        await app.state.engine.dispose()


if __name__ == "__main__":
    run_verifier(verify)
