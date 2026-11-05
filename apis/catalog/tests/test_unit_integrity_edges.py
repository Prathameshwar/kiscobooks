"""Boundary regressions for retained definitions and exact bulk transport."""

import datetime as dt
import uuid
from typing import Any

import pytest
from billing_platform.db import tenant_scope
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ItemUnitBinding, ItemUnitRevision
from catalog.schemas.bulk import RecordPreview, ResourceChange
from catalog.tasks import activation
from tests.source_factories import all_facts
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers
from tests.test_unit_api import access, policy
from tests.unit_integrity_factories import binding_body, latest_revision, new_unit, setup_units

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("resource", ["unit_conversion", "item_unit_revision"])
def test_bulk_ratio_output_preserves_exact_values_without_changing_evidence(resource: str) -> None:
    values = {"numerator": 9007199254740993, "denominator": 1, "revision": 2}
    change = ResourceChange(resource=resource, before=None, after=values)
    preview = RecordPreview(
        id=uuid.uuid4(),
        logical_key="ratio",
        change_set_id=uuid.uuid4(),
        resource=resource,
        action="CREATE",
        source_sheet="",
        source_row=1,
        state="APPLIED",
        error_code=None,
        after=values,
        changes=[change],
        result=values,
    )
    rendered = preview.model_dump(mode="json")
    for result in (rendered["after"], rendered["result"], rendered["changes"][0]["after"]):
        assert result["numerator"] == "9007199254740993"
        assert result["denominator"] == "1"
        assert result["revision"] == 2
    assert values["numerator"] == 9007199254740993
    assert preview.after == values


@pytest.mark.parametrize("closed_conflict", [False, True])
async def test_base_relation_added_last_preserves_closed_product_history(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    closed_conflict: bool,
) -> None:
    root, auth, ids = await setup_units(factory, tenant_a)
    path = root + f"/items/{ids['item']}"
    base = (await client.get(path, headers=auth)).json()["base_unit_id"]
    canonical = await new_unit(client, root, auth, "ROOT")
    dozen = await new_unit(client, root, auth, "DOZEN")
    for source, numerator in ((canonical, "1"), (dozen, "12")):
        result = await client.post(
            root + "/unit-conversions",
            headers=command_headers(auth),
            json={
                "from_unit_id": source,
                "canonical_unit_id": canonical,
                "numerator": numerator,
                "denominator": "1",
            },
        )
        assert result.status_code == 201, result.text
    result = await client.post(
        path + "/unit-bindings",
        headers=command_headers(auth),
        json=binding_body(dozen, numerator=10 if closed_conflict else 12),
    )
    assert result.status_code == 200, result.text
    if closed_conflict:
        old = await latest_revision(client, root, auth, ids["item"], "ALT")
        result = await client.post(
            path + "/unit-revisions",
            headers=command_headers(auth),
            json=binding_body(
                dozen, expected_version=2, binding_id=old["binding_id"], valid_from="2091-01-01"
            ),
        )
        assert result.status_code == 200, result.text
    # A unit-only administrator may check product dependencies without reading products.
    company = uuid.UUID(root.rsplit("/", 1)[1])
    admin = access(tenant_a, company, ids["actor_user"], "unit.manage")
    result = await client.post(
        root + "/unit-conversions",
        headers=command_headers(admin),
        json={
            "from_unit_id": base,
            "canonical_unit_id": canonical,
            "numerator": "1",
            "denominator": "1",
        },
    )
    assert result.status_code == (409 if closed_conflict else 201), result.text


@pytest.mark.parametrize("consumer", ["quantity", "pricing", "activation"])
@pytest.mark.parametrize("measured", [False, True])
async def test_legacy_inconsistent_unit_definitions_fail_closed(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    consumer: str,
    monkeypatch: pytest.MonkeyPatch,
    measured: bool,
) -> None:
    root, auth, ids = await setup_units(factory, tenant_a)
    path = root + f"/items/{ids['item']}"
    base = (await client.get(path, headers=auth)).json()["base_unit_id"]
    alternate = await new_unit(client, root, auth, "ALT")
    if not measured:
        for source, numerator in ((base, "1"), (alternate, "12")):
            result = await client.post(
                root + "/unit-conversions",
                headers=command_headers(auth),
                json={
                    "from_unit_id": source,
                    "canonical_unit_id": base,
                    "numerator": numerator,
                    "denominator": "1",
                },
            )
            assert result.status_code == 201, result.text
    body = binding_body(alternate)
    if measured:
        body.update(
            role="MEASURED",
            conversion_mode="MEASURED",
            numerator=None,
            denominator=None,
            secondary_unit_id=base,
            nominal_ratio="12",
        )
    result = await client.post(path + "/unit-bindings", headers=command_headers(auth), json=body)
    assert result.status_code == 200, result.text
    revision = await latest_revision(client, root, auth, ids["item"], "ALT")
    # Model historical invalid data without using the corrected authoring path.
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.get(ItemUnitRevision, uuid.UUID(revision["id"]))
            assert row is not None
            if measured:
                binding = await db.get(ItemUnitBinding, row.binding_id)
                assert binding is not None
                binding.unit_id = uuid.UUID(base)
            else:
                row.numerator = 10
    request: dict[str, Any] = {"as_of": "2090-01-01"}
    if consumer == "quantity":
        route = path + "/quantity-preview"
        request["components"] = [
            {
                "unit_revision_id": revision["id"],
                "quantity": "1",
                **({"measured_base_quantity": "2"} if measured else {}),
            }
        ]
    elif consumer == "pricing":
        route = root + "/prices/resolve"
        request.update(
            item_id=str(ids["item"]), unit_revision_id=revision["id"], quantity="1", currency="INR"
        )
    else:
        route = path + "/activation-preview"
        monkeypatch.setattr(
            activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC)
        )
    result = await client.post(route, headers=auth, json=request)
    assert result.status_code == (422 if measured else 409), result.text
    assert ("distinct" if measured else "canonical") in result.text, result.text


async def test_canonical_dependency_read_denial_cannot_be_bypassed_by_unit_admin(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await setup_units(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    path = root + f"/items/{ids['item']}"
    base = (await client.get(path, headers=auth)).json()["base_unit_id"]
    alternate = await new_unit(client, root, auth, "ALT")
    result = await client.post(
        root + "/unit-conversions",
        headers=command_headers(auth),
        json={
            "from_unit_id": base,
            "canonical_unit_id": base,
            "numerator": "1",
            "denominator": "1",
        },
    )
    assert result.status_code == 201, result.text
    result = await client.post(
        path + "/unit-bindings", headers=command_headers(auth), json=binding_body(alternate)
    )
    assert result.status_code == 200, result.text
    facts = tuple(
        row for row in all_facts(company, ids["actor_user"]) if row.kind != "field_policy"
    )
    await setup_source(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        version=4,
        facts=(
            *facts,
            policy(ids["actor_user"], "numerator", "read", entity="catalog.item_unit_revision"),
        ),
    )
    admin = access(tenant_a, company, ids["actor_user"], "unit.manage")
    result = await client.post(
        root + "/unit-conversions",
        headers=command_headers(admin),
        json={
            "from_unit_id": alternate,
            "canonical_unit_id": base,
            "numerator": "12",
            "denominator": "1",
        },
    )
    assert result.status_code == 403, result.text


@pytest.mark.parametrize("resource", ["unit_conversion", "item_unit_revision"])
async def test_empty_conversion_dependencies_still_require_read_authority(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    resource: str,
) -> None:
    root, auth, ids = await setup_units(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    path = root + f"/items/{ids['item']}"
    base = (await client.get(path, headers=auth)).json()["base_unit_id"]
    alternate = await new_unit(client, root, auth, "ALT")
    facts = tuple(
        row for row in all_facts(company, ids["actor_user"]) if row.kind != "field_policy"
    )
    await setup_source(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        version=4,
        facts=(
            *facts,
            policy(ids["actor_user"], "numerator", "read", entity="catalog." + resource),
        ),
    )
    if resource == "unit_conversion":
        result = await client.post(
            path + "/unit-bindings", headers=command_headers(auth), json=binding_body(alternate)
        )
    else:
        result = await client.post(
            root + "/unit-conversions",
            headers=command_headers(auth),
            json={
                "from_unit_id": base,
                "canonical_unit_id": base,
                "numerator": "1",
                "denominator": "1",
            },
        )
    assert result.status_code == 403, result.text
