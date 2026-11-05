"""Product custom-field regression coverage."""

import json
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.custom_fields import CustomDefinition, validate_values
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.tasks.index_rebuilds import build_chunk, permissions
from tests.product_factories import setup_product
from tests.source_factories import all_facts
from tests.tax_factories import seed_tax
from tests.test_actor_authorization import proof
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers
from tests.test_scheme_governance import active_product, clock

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")
ENTITY = "catalog.item"


def custom_facts(
    company: uuid.UUID, user: uuid.UUID, definitions: list[dict[str, Any]]
) -> tuple[SnapshotRecord, ...]:
    base = all_facts(company, user)
    template = next(row for row in base if row.kind == "custom_definition")
    return (
        *(row for row in base if row.kind not in {"custom_definition", "field_config"}),
        *(
            SnapshotRecord(
                kind="custom_definition", id=uuid7(), data={**template.data, **definition}
            )
            for definition in definitions
        ),
    )


async def install(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    definitions: list[dict[str, Any]],
    version: int = 3,
) -> None:
    await setup_source(
        factory,
        tenant,
        company,
        user,
        facts=custom_facts(company, user, definitions),
        version=version,
    )


@pytest.mark.parametrize(
    "kind,default",
    [
        ("integer", 7),
        ("text", "hello"),
        ("decimal", "1.25"),
        ("date", "2026-09-15"),
        ("select", "red"),
    ],
)
async def test_identity_encoded_default_survives_product_creation(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    kind: str,
    default: Any,
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    definition: dict[str, Any] = {"data_type": kind, "default_value": json.dumps(default)}
    if kind == "select":
        definition["options"] = {"choices": [{"value": "red", "label": "Red"}]}
    await install(factory, tenant_a, company, user, [definition])
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code == 201, result.text
    expected = "1.2500" if kind == "decimal" else default
    assert result.json()["default_item"]["custom_fields"]["cf_note"] == expected


async def test_integer_layout_default_has_declared_type(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    facts = list(custom_facts(company, user, [{"data_type": "integer"}]))
    definition = next(row for row in facts if row.kind == "custom_definition")
    layout = next(row for row in all_facts(company, user) if row.kind == "field_config")
    facts.append(
        SnapshotRecord(
            kind="field_config",
            id=uuid7(),
            data={
                **layout.data,
                "definition_id": str(definition.id),
                "default_value": "7",
            },
        )
    )
    await setup_source(factory, tenant_a, company, user, facts=tuple(facts), version=3)
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code == 201, result.text
    assert result.json()["default_item"]["custom_fields"]["cf_note"] == 7


async def test_unique_optional_field_does_not_disable_all_product_creation(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    await install(
        factory,
        tenant_a,
        company,
        user,
        [
            {
                "is_searchable": True,
                "validation": {"unique_within": "company"},
            }
        ],
    )
    # Even a product omitting the optional value must remain authorable.
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code == 201, result.text


async def test_unique_index_can_be_prepared(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, _, _ = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(permissions(ENTITY)))
    await install(
        factory,
        tenant_a,
        company,
        user,
        [
            {
                "is_searchable": True,
                "validation": {"unique_within": "company"},
            }
        ],
    )
    result = await client.post(
        f"/v1/companies/{company}/entities/{ENTITY}/field-indexes/cf_note/rebuilds",
        headers=command_headers(auth),
        json={"expected_version": 0},
    )
    assert result.status_code == 201, result.text


async def test_active_product_allows_descriptive_custom_field_edit(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids, _ = await active_product(client, factory, tenant_a, monkeypatch)
    path = root + "/items/" + str(ids["item"])
    current = await client.get(path, headers=auth)
    assert current.status_code == 200, current.text
    result = await client.patch(
        path,
        headers=command_headers(auth),
        json={
            "expected_version": current.json()["row_version"],
            "custom_fields": {"cf_note": "updated"},
        },
    )
    assert result.status_code == 200, result.text


@pytest.mark.parametrize("entity", ["catalog.item", "catalog.product_family"])
async def test_activation_checks_current_required_custom_fields(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    entity: str,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    clock(monkeypatch)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await install(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        [
            {
                "entity_type": entity,
                "validation": {"required": True},
            }
        ],
        version=50,
    )
    route = root + "/items/" + str(ids["item"])
    preview = await client.post(
        route + "/activation-preview", headers=auth, json={"as_of": "2090-01-01"}
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["eligible"] is False, preview.text


async def test_native_uuid_condition_enforces_requiredness(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    await install(
        factory,
        tenant_a,
        company,
        user,
        [
            {
                "validation": {"required": True},
                "visibility": {
                    "field": "base_unit_id",
                    "cmp": "eq",
                    "value": body["default_item"]["base_unit_id"],
                },
            }
        ],
    )
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code == 422, result.text


@pytest.mark.parametrize("operand", [[1], ["1.00"]])
async def test_decimal_membership_condition_uses_numeric_equality(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    operand: list[Any],
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    await install(
        factory,
        tenant_a,
        company,
        user,
        [
            {"key": "cf_amount", "data_type": "decimal"},
            {
                "key": "cf_note",
                "validation": {"required": True},
                "visibility": {"field": "cf_amount", "cmp": "in", "value": operand},
            },
        ],
    )
    body["default_item"]["custom_fields"] = {"cf_amount": "1.00"}
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code == 422, result.text


async def test_conditional_required_field_can_be_indexed_when_hidden(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    definitions = [
        {
            "validation": {"required": True},
            "visibility": {"field": "sellable", "cmp": "eq", "value": False},
        }
    ]
    await install(factory, tenant_a, company, user, definitions)
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code == 201, result.text
    definitions[0]["is_searchable"] = True
    await install(factory, tenant_a, company, user, definitions, version=4)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(permissions(ENTITY)))
    result = await client.post(
        f"/v1/companies/{company}/entities/{ENTITY}/field-indexes/cf_note/rebuilds",
        headers=command_headers(auth),
        json={"expected_version": 0},
    )
    assert result.status_code == 201, result.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            final = await build_chunk(
                db,
                proof(tenant_a, company, user, source_version=4, permissions=permissions(ENTITY)),
                company=company,
                entity=ENTITY,
                key="cf_note",
                job_id=uuid.UUID(result.json()["id"]),
            )
    assert final.status == "succeeded"


def test_invalid_currency_type_returns_validation_error() -> None:
    definition = CustomDefinition(key="cf_amount", data_type="currency_amount")
    with pytest.raises(ValidationFailedError):
        validate_values(
            (definition,),
            {"cf_amount": {"amount": "1", "currency": []}},
            previous={},
            native_values={},
            previous_native_values={},
            creating=True,
            readable_condition_fields=frozenset(),
            currencies=frozenset({"INR"}),
            resolve_options=lambda *_: frozenset(),
        )


async def test_permission_and_atomic_rollback_controls(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    facts = list(custom_facts(company, user, [{}]))
    template = next(row for row in facts if row.kind == "field_policy")
    facts.append(
        SnapshotRecord(
            kind="field_policy",
            id=uuid7(),
            data={
                **template.data,
                "entity_type": ENTITY,
                "field_key": "custom_field:cf_note",
                "subject_type": "user",
                "subject_id": str(user),
                "access": "write",
            },
        )
    )
    await setup_source(factory, tenant_a, company, user, facts=tuple(facts), version=3)
    body["default_item"]["custom_fields"] = {"cf_note": "private"}
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code == 403, result.text
    page = await client.get(f"/v1/companies/{company}/product-families", headers=auth)
    assert page.status_code == 200 and page.json()["items"] == []
