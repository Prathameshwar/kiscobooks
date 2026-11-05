"""Native authoring and publisher-only metadata consumed by the profile UI."""

import json
from pathlib import Path

import pytest
from billing_platform.ids import uuid7

from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_unit_api import policy, seed_context

ENTITIES = {
    "inventory_profile_template": "inventory_profile_template",
    "warranty_policy": "warranty_policy",
    "return_policy": "return_policy",
    "handling_profile": "handling_profile",
}
pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_profile_controls_capture(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            prefix + "." + verb
            for prefix in ENTITIES.values()
            for verb in ("read", "manage", "publish")
        ],
    )
    captured = {}
    entities = [
        *ENTITIES,
        *(entity + "_revision" for entity in ENTITIES),
        "return_policy_condition",
    ]
    for entity in entities:
        for operation in (
            "read",
            "create",
            "update",
            *(["publish"] if entity not in ENTITIES else []),
        ):
            response = await client.get(
                f"/v1/companies/{company}/entities/catalog.{entity}/field-set",
                headers=current,
                params={} if operation == "read" else {"operation": operation},
            )
            assert response.status_code == 200, response.text
            captured[entity + ":" + operation] = response.json()
    for entity in ENTITIES:
        updated = {field["key"]: field for field in captured[entity + ":update"]["fields"]}
        assert not updated["is_active"]["writable"]
        revised = {
            field["key"]: field for field in captured[entity + "_revision:publish"]["fields"]
        }
        assert revised["published_at"]["writable"]
        assert not revised["revision"]["writable"]
        parent = (
            "template_id"
            if entity == "inventory_profile_template"
            else "profile_id"
            if entity == "handling_profile"
            else "policy_id"
        )
        created = {field["key"]: field for field in captured[entity + "_revision:create"]["fields"]}
        assert created[parent]["writable"]
        assert not revised[parent]["writable"]
    handling = {
        field["key"]: field for field in captured["handling_profile_revision:create"]["fields"]
    }
    assert handling["temperature_min"]["control"]["kind"] == "text"
    assert handling["instructions"]["control"]["max_length"] == 2000
    conditions = {
        field["key"]: field for field in captured["return_policy_condition:update"]["fields"]
    }
    assert conditions["revision_id"]["writable"]
    assert len(conditions["condition_code"]["control"]["choices"]) == 5
    destination = (
        Path(__file__).resolve().parents[3] / ".tools/product-profile-review/native-fields.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(captured, indent=2), encoding="utf-8")


@pytest.mark.parametrize("entity,prefix", ENTITIES.items())
async def test_publish_permission_is_separate(client, factory, tenant_a, entity, prefix):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    root = f"/v1/companies/{company}/entities/catalog.{entity}_revision/field-set"
    for verb in ("manage", "publish"):
        current = headers(
            company, tenant=tenant_a, user=user, permission=[prefix + ".read", prefix + "." + verb]
        )
        for operation in ("update", "publish"):
            response = await client.get(root, headers=current, params={"operation": operation})
            assert response.status_code == 200, response.text
            fields = response.json()["fields"]
            assert any(field["writable"] for field in fields) == (
                verb == ("publish" if operation == "publish" else "manage")
            )


@pytest.mark.parametrize("access", ["read", "write"])
async def test_profile_field_deny(client, factory, tenant_a, access):
    company, user = uuid7(), uuid7()
    await seed_context(
        factory,
        tenant_a,
        company,
        user,
        [policy(user, "published_at", access, entity="catalog.handling_profile_revision")],
    )
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=["handling_profile.read", "handling_profile.publish"],
    )
    response = await client.get(
        f"/v1/companies/{company}/entities/catalog.handling_profile_revision/field-set?operation=publish",
        headers=current,
    )
    assert response.status_code == 200, response.text
    field = next(
        (field for field in response.json()["fields"] if field["key"] == "published_at"), None
    )
    assert field is None if access == "read" else field and not field["writable"]


async def test_profile_metadata_closed_queries_and_scope(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    current = headers(company, tenant=tenant_a, user=user, permission=["handling_profile.read"])
    root = f"/v1/companies/{company}/entities/catalog.handling_profile_revision/field-set"
    assert (await client.get(root)).status_code == 401
    for query in ("extra=true", "operation=publish&operation=update", "object_id=" + str(uuid7())):
        assert (await client.get(root + "?" + query, headers=current)).status_code == 422
    assert (
        await client.get(root.replace(str(company), str(uuid7())), headers=current)
    ).status_code == 403


@pytest.mark.parametrize(
    "entity,parent",
    [
        ("inventory_profile_template_revision", "template_id"),
        ("warranty_policy_revision", "policy_id"),
        ("return_policy_revision", "policy_id"),
        ("handling_profile_revision", "profile_id"),
    ],
)
async def test_profile_generated_parent_respects_write_denies(
    client, factory, tenant_a, entity, parent
):
    company, user = uuid7(), uuid7()
    await seed_context(
        factory,
        tenant_a,
        company,
        user,
        [policy(user, parent, "write", entity="catalog." + entity)],
    )
    prefix = entity.removesuffix("_revision")
    current = headers(
        company, tenant=tenant_a, user=user, permission=[prefix + ".read", prefix + ".manage"]
    )
    response = await client.get(
        f"/v1/companies/{company}/entities/catalog.{entity}/field-set?operation=create",
        headers=current,
    )
    assert response.status_code == 200, response.text
    assert not next(field for field in response.json()["fields"] if field["key"] == parent)[
        "writable"
    ]
