"""Native authoring controls and publication field access used by the Console."""

import json
from pathlib import Path

import pytest
from billing_platform.ids import uuid7

from tests.attribute_factories import auth
from tests.test_api import headers
from tests.test_unit_api import policy, seed_context


async def test_attribute_controls_and_capture(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    captured = {}
    for entity in (
        "attribute_definition",
        "attribute_option",
        "attribute_set",
        "attribute_set_revision",
        "attribute_set_member",
    ):
        for operation in (
            "create",
            "update",
            *(["publish"] if entity in {"attribute_set_revision", "attribute_set_member"} else []),
        ):
            response = await client.get(
                f"/v1/companies/{company}/entities/catalog.{entity}/field-set",
                params={"operation": operation},
                headers=current,
            )
            assert response.status_code == 200, response.text
            captured[entity + ":" + operation] = response.json()
    options = {row["key"]: row for row in captured["attribute_option:create"]["fields"]}
    definitions = {
        row["key"]: row for row in captured["attribute_definition:create"]["fields"]
    }
    assert {
        choice["value"]
        for choice in definitions["measurement_dimension"]["control"]["choices"]
    } == {"COUNT", "MASS", "VOLUME", "LENGTH", "AREA", "TIME", "JOB"}
    assert options["value_integer"]["control"]["kind"] == "text"
    assert options["value_decimal"]["control"]["kind"] == "text"
    assert options["definition_id"]["control"]["reference_source"] == "attribute-definitions"
    assert options["value_date"]["control"]["kind"] == "date"
    for entity in ("attribute_definition", "attribute_option", "attribute_set"):
        assert not next(
            row for row in captured[entity + ":update"]["fields"] if row["key"] == "is_active"
        )["writable"]
    updated = {row["key"]: row for row in captured["attribute_option:update"]["fields"]}
    assert not updated["definition_id"]["writable"] and not updated["value_type"]["writable"]
    publish = {row["key"]: row for row in captured["attribute_set_revision:publish"]["fields"]}
    assert publish["published_at"]["writable"]
    destination = Path(__file__).resolve().parents[3] / ".tools/attribute-review/native-fields.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(captured, indent=2), encoding="utf-8")


async def test_publish_metadata_uses_publish_authority(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/entities/catalog.attribute_set_member/field-set"
    publisher = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=["attribute_set.read", "attribute_set.publish"],
    )
    manager = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=["attribute_set.read", "attribute_set.manage"],
    )
    for current, expected in ((publisher, True), (manager, False)):
        response = await client.get(route, params={"operation": "publish"}, headers=current)
        assert response.status_code == 200
        assert all(row["writable"] is expected for row in response.json()["fields"])
    response = await client.get(route, params={"operation": "update"}, headers=publisher)
    assert not any(row["writable"] for row in response.json()["fields"])


@pytest.mark.parametrize(
    "entity", ["attribute_definition", "attribute_option", "attribute_set", "unit_of_measure"]
)
async def test_reject_unsupported_publication_metadata(client, factory, tenant_a, entity):
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    response = await client.get(
        f"/v1/companies/{company}/entities/catalog.{entity}/field-set?operation=publish",
        headers=current,
    )
    assert response.status_code == 422


@pytest.mark.parametrize("access", ["read", "write"])
async def test_publish_metadata_preserves_field_denies(client, factory, tenant_a, access):
    company, user = uuid7(), uuid7()
    entity = "catalog.attribute_set_member"
    await seed_context(
        factory, tenant_a, company, user, [policy(user, "is_required", access, entity=entity)]
    )
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=["attribute_set.read", "attribute_set.publish"],
    )
    response = await client.get(
        f"/v1/companies/{company}/entities/{entity}/field-set?operation=publish", headers=current
    )
    assert response.status_code == 200
    field = next((row for row in response.json()["fields"] if row["key"] == "is_required"), None)
    assert field is None if access == "read" else field and not field["writable"]


async def test_metadata_rejects_duplicate_queries_and_other_company(client, factory, tenant_a):
    company, other, user = uuid7(), uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    await auth(factory, tenant_a, other, user)
    route = f"/v1/companies/{company}/entities/catalog.attribute_set/field-set"
    assert (await client.get(route)).status_code == 401
    assert (
        await client.get(route + "?operation=create&operation=update", headers=current)
    ).status_code == 422
    assert (await client.get(route + "?unexpected=true", headers=current)).status_code == 422
    assert (
        await client.get(route.replace(str(company), str(other)), headers=current)
    ).status_code == 403
