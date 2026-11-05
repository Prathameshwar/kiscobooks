from __future__ import annotations

import uuid
from typing import Any

import httpx
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.attribute_factories import auth
from tests.source_factories import all_facts
from tests.test_attribute_sets_api import setup_template
from tests.test_classification_api import create
from tests.test_commercial_api import command_headers


async def test_type_template_binding_lifecycle_and_scopes(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, current, route, members = await setup_template(client, factory, tenant_a)
    draft = await client.post(route, headers=command_headers(current), json={"members": members})
    assert draft.status_code == 201, draft.text
    revision = draft.json()["id"]
    product_type = (
        await create(
            client,
            company,
            current,
            "product-types",
            {"code": "CLOTH", "name": "Clothing", "kind": "GOODS"},
        )
    ).json()
    type_route = f"/v1/companies/{company}/product-types/{product_type['id']}"
    revisions = type_route + "/revisions"
    body: dict[str, Any] = {
        "inventory_modes": ["STOCK"],
        "tracking_modes": ["NONE"],
        "unit_dimensions": ["COUNT"],
        "attribute_set_revision_id": revision,
    }
    assert (
        await client.post(revisions, headers=command_headers(current), json=body)
    ).status_code == 409
    assert (
        await client.post(
            route + "/" + revision + "/publish",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    created = await client.post(revisions, headers=command_headers(current), json=body)
    assert created.status_code == 201, created.text
    assert created.json()["attribute_set_revision_id"] == revision
    detail = revisions + "/" + created.json()["id"]
    noop = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 1, "attribute_set_revision_id": revision},
    )
    assert noop.status_code == 200 and noop.json()["row_version"] == 1, noop.text
    page = await client.get(revisions, headers=current)
    assert "attribute_set_revision_id" not in page.json()["items"][0]
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    template = route.rsplit("/", 1)[0]
    assert (
        await client.post(
            template + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 409
    other_company = uuid7()
    other = await auth(factory, tenant_a, other_company, user)
    other_type = (
        await create(
            client,
            other_company,
            other,
            "product-types",
            {"code": "OTHER", "name": "Other", "kind": "GOODS"},
        )
    ).json()
    other_revisions = f"/v1/companies/{other_company}/product-types/{other_type['id']}/revisions"
    assert (
        await client.post(other_revisions, headers=command_headers(other), json=body)
    ).status_code == 403
    assert (
        await client.post(
            revisions,
            headers=command_headers(current),
            json={**body, "attribute_set_revision_id": str(uuid7())},
        )
    ).status_code == 404
    assert (
        await client.post(
            type_route + "/deactivate",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    assert (
        await client.post(
            template + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    assert (
        await client.post(
            type_route + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 409
    definition = f"/v1/companies/{company}/attribute-definitions/{members[0]['definition_id']}"
    assert (
        await client.post(
            definition + "/deactivate",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    assert (
        await client.post(
            template + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 409
    assert (
        await client.post(
            definition + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 200
    assert (
        await client.post(
            template + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 200
    assert (
        await client.post(
            type_route + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 200


async def test_optional_template_field_denial_only_protects_actual_binding(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, current, route, members = await setup_template(client, factory, tenant_a)
    draft = await client.post(route, headers=command_headers(current), json={"members": members})
    revision = draft.json()["id"]
    assert (
        await client.post(
            route + "/" + revision + "/publish",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    product_type = (
        await create(
            client,
            company,
            current,
            "product-types",
            {"code": "TYPE", "name": "Type", "kind": "GOODS"},
        )
    ).json()
    revisions = f"/v1/companies/{company}/product-types/{product_type['id']}/revisions"
    facts = all_facts(company, user)
    policy = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.product_type_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "attribute_set_revision_id",
            "access": "write",
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    body = {"inventory_modes": ["STOCK"], "tracking_modes": ["NONE"], "unit_dimensions": ["COUNT"]}
    receipt = command_headers(current)
    created = await client.post(revisions, headers=receipt, json=body)
    assert created.status_code == 201, created.text
    assert (await client.post(revisions, headers=receipt, json=body)).headers[
        "Idempotency-Replayed"
    ] == "true"
    detail = revisions + "/" + created.json()["id"]
    assert (
        await client.post(
            revisions,
            headers=command_headers(current),
            json={**body, "attribute_set_revision_id": revision},
        )
    ).status_code == 403
    assert (
        await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 1, "attribute_set_revision_id": revision},
        )
    ).status_code == 403
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
