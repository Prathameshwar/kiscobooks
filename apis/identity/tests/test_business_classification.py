"""Classification selection, reference bindings, security and audit regression tests."""

from __future__ import annotations

import copy
import json
import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.business_classification import normalize_business_roles
from identity.models import (
    BusinessCategory,
    BusinessRole,
    Company,
    CompanyBusinessRole,
    Outbox,
    StoreFormat,
)
from identity.schemas.company import CompanyCreate, CompanyUpdate
from identity.seeds.business_classifications import SEED_PATH, seed_business_classifications
from identity.seeds.roles import seed_system_roles
from tests.api_support import actor_headers, grant
from tests.factories import build_company, seed_two_companies, seed_two_tenants
from tests.test_api_companies import _admin_headers, _valid_company_body

CLASSIFICATION = {
    "business_category_code": "pharmaceutical",
    "business_roles": ["wholesaler", "distributor"],
    "store_format_code": "mart",
}


def test_roles_are_order_independent_and_unique() -> None:
    assert normalize_business_roles(["wholesaler", "distributor"]) == [
        "distributor",
        "wholesaler",
    ]
    with pytest.raises(ValueError, match="duplicates"):
        normalize_business_roles(["retailer", "retailer"])


def test_create_defaults_and_patch_omission_are_backward_compatible() -> None:
    body = CompanyCreate.model_validate(_valid_company_body())
    assert body.business_category_code is None
    assert body.store_format_code is None
    assert body.business_roles == []
    assert CompanyUpdate().model_dump(exclude_unset=True) == {}
    assert CompanyUpdate(business_roles=[]).model_dump(exclude_unset=True) == {"business_roles": []}
    assert CompanyUpdate(business_category_code=None).model_dump(exclude_unset=True) == {
        "business_category_code": None,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"business_roles": None},
        {"business_roles": "retailer"},
        {"business_roles": ["retailer", "retailer"]},
        {"business_roles": [1]},
        {"business_category_code": ""},
        {"business_category_code": "X" * 33},
        {"store_format_code": "Mart"},
    ],
)
def test_schema_rejects_malformed_selection(payload: dict[str, object]) -> None:
    for model, base in ((CompanyCreate, _valid_company_body()), (CompanyUpdate, {})):
        with pytest.raises(ValidationError):
            model.model_validate(base | payload)


async def test_create_read_update_clear_and_audit(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    headers = _admin_headers(tenant_a)
    response = await client.post(
        "/v1/companies",
        headers=headers,
        json=_valid_company_body() | CLASSIFICATION,
    )
    assert response.status_code == 201, response.text
    company_id = uuid.UUID(response.json()["id"])
    url = f"/v1/companies/{company_id}"
    response = await client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json()["business_roles"] == ["distributor", "wholesaler"]
    assert response.json()["business_category_code"] == "pharmaceutical"
    assert response.json()["store_format_code"] == "mart"
    with tenant_scope(tenant_a):
        bindings = list(await session.scalars(select(CompanyBusinessRole)))
        assert {row.tenant_id for row in bindings} == {tenant_a}
        retained_id = next(row.id for row in bindings if row.business_role_code == "distributor")
    response = await client.patch(
        url, headers=headers, json={"business_roles": ["retailer", "distributor"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["business_roles"] == ["distributor", "retailer"]
    with tenant_scope(tenant_a):
        session.expire_all()
        bindings = list(await session.scalars(select(CompanyBusinessRole)))
        assert (
            next(row.id for row in bindings if row.business_role_code == "distributor")
            == retained_id
        )
        audit = (
            await session.scalars(
                select(Outbox).where(
                    Outbox.event_type == "company.updated",
                    Outbox.aggregate_id == company_id,
                )
            )
        ).one()
        assert audit.payload["changes"]["business_roles"] == {
            "from": ["distributor", "wholesaler"],
            "to": ["distributor", "retailer"],
        }
    # Omitted classifications survive unrelated changes, including after first posting.
    response = await client.patch(url, headers=headers, json={"display_name": "Renamed"})
    assert response.json()["business_roles"] == ["distributor", "retailer"]
    response = await client.patch(
        url,
        headers=headers,
        json={
            "business_category_code": None,
            "store_format_code": None,
            "business_roles": [],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["business_roles"] == []
    assert response.json()["business_category_code"] is None
    assert response.json()["store_format_code"] is None
    with tenant_scope(tenant_a):
        assert await session.scalar(select(func.count(CompanyBusinessRole.id))) == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("business_category_code", "unknown"),
        ("store_format_code", "unknown"),
        ("business_roles", ["unknown"]),
        ("business_roles", ["point_of_sale"]),
        ("business_roles", ["mart"]),
    ],
)
async def test_unknown_references_fail_create_and_patch_atomically(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    field: str,
    value: object,
) -> None:
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _admin_headers(tenant_a)
    response = await client.post(
        "/v1/companies", headers=headers, json=_valid_company_body("NEW") | {field: value}
    )
    assert response.status_code == 422, response.text
    response = await client.patch(
        f"/v1/companies/{company_id}",
        headers=headers,
        json={
            field: value,
            "display_name": "Must not persist",
        },
    )
    assert response.status_code == 422, response.text
    with tenant_scope(tenant_a):
        row = await session.get(Company, company_id)
        assert row is not None and row.display_name == "Alpha Ltd"
        assert await session.scalar(select(func.count(Company.id))) == 1
        assert await session.scalar(select(func.count(Outbox.id))) == 0


async def test_reference_seed_is_repeatable_and_withdrawal_preserves_bindings(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    headers = _admin_headers(tenant_a)
    response = await client.post(
        "/v1/companies", headers=headers, json=_valid_company_body() | CLASSIFICATION
    )
    assert response.status_code == 201, response.text
    url = "/v1/companies/" + response.json()["id"]
    await seed_business_classifications(session)
    await session.commit()
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    reduced = copy.deepcopy(data)
    reduced["business_categories"] = [
        r for r in reduced["business_categories"] if r["code"] != "pharmaceutical"
    ]
    reduced["business_roles"] = [r for r in reduced["business_roles"] if r["code"] != "distributor"]
    reduced["store_formats"] = [r for r in reduced["store_formats"] if r["code"] != "mart"]
    await seed_business_classifications(session, data=reduced)
    await session.commit()
    response = await client.get("/v1/company-classifications", headers=headers)
    assert response.status_code == 200
    assert "distributor" not in {r["code"] for r in response.json()["business_roles"]}
    response = await client.post(
        "/v1/companies", headers=headers, json=_valid_company_body("NEW") | CLASSIFICATION
    )
    assert response.status_code == 422
    response = await client.patch(url, headers=headers, json=CLASSIFICATION)
    assert response.status_code == 200, response.text
    assert response.json()["business_roles"] == ["distributor", "wholesaler"]
    await seed_business_classifications(session)
    await session.commit()
    for model, key in (
        (BusinessCategory, "business_categories"),
        (BusinessRole, "business_roles"),
        (StoreFormat, "store_formats"),
    ):
        assert await session.scalar(select(func.count()).select_from(model)) == len(data[key])


async def test_lookup_requires_permission_and_has_no_crud(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    url = "/v1/company-classifications"
    assert (await client.get(url)).status_code == 401
    denied = actor_headers(tenant_id=tenant_a, user_id=uuid7())
    assert (await client.get(url, headers=denied)).status_code == 403
    for permission in ("company.create", "company.read", "company.update"):
        headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant([permission])])
        response = await client.get(url, headers=headers)
        assert response.status_code == 200, response.text
        assert [r["code"] for r in response.json()["business_categories"]] == [
            "general",
            "mobile_electronics",
            "pharmaceutical",
            "fmcg",
            "apparel",
            "other",
        ]
    for method in ("post", "patch", "put", "delete"):
        assert (
            await client.request(method, url, headers=_admin_headers(tenant_a))
        ).status_code == 405
    response = await client.get(
        "/v1/entities/identity.company/field-set", headers=_admin_headers(tenant_a)
    )
    assert {"business_category_code", "business_roles", "store_format_code"} <= {
        f["key"] for f in response.json()["fields"]
    }


async def test_cross_tenant_and_wrong_company_updates_are_rejected(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _admin_headers(tenant_a)
    assert (
        await client.patch(f"/v1/companies/{company_b}", headers=headers, json=CLASSIFICATION)
    ).status_code == 404
    other_id = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_company(tenant_id=tenant_a, company_id=other_id, code="OTHER"))
        await session.commit()
    scoped = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[
            grant(["company.update"], scope_type="company", scope_id=company_a),
        ],
    )
    assert (
        await client.patch(f"/v1/companies/{other_id}", headers=scoped, json=CLASSIFICATION)
    ).status_code == 403
    assert (
        await client.patch(f"/v1/companies/{company_a}", json=CLASSIFICATION)
    ).status_code == 401
    denied = actor_headers(tenant_id=tenant_a, user_id=uuid7())
    assert (
        await client.patch(f"/v1/companies/{company_a}", headers=denied, json=CLASSIFICATION)
    ).status_code == 403


async def test_binding_reads_are_tenant_filtered_and_parent_tenant_must_match(
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    with unfiltered():
        session.add_all(
            [
                CompanyBusinessRole(
                    tenant_id=tenant_a, company_id=company_a, business_role_code="retailer"
                ),
                CompanyBusinessRole(
                    tenant_id=tenant_b, company_id=company_b, business_role_code="retailer"
                ),
            ]
        )
        await session.commit()
    with tenant_scope(tenant_a):
        rows = list(await session.scalars(select(CompanyBusinessRole)))
        assert len(rows) == 1 and rows[0].company_id == company_a
    with unfiltered():
        session.add(
            CompanyBusinessRole(
                tenant_id=tenant_a, company_id=company_b, business_role_code="stockist"
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


@pytest.mark.parametrize("invalid", ["category", "format", "role", "duplicate"])
async def test_database_rejects_invalid_reference_or_duplicate_binding(
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    invalid: str,
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        row = await session.get(Company, company_a)
        assert row is not None
        if invalid == "category":
            row.business_category_code = "unknown"
        elif invalid == "format":
            row.store_format_code = "unknown"
        else:
            for _ in range(2 if invalid == "duplicate" else 1):
                session.add(
                    CompanyBusinessRole(
                        tenant_id=tenant_a,
                        company_id=company_a,
                        business_role_code="retailer" if invalid == "duplicate" else "unknown",
                    )
                )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


async def test_point_of_sale_uses_existing_audited_feature_routes(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _admin_headers(tenant_a)
    base = f"/v1/companies/{company_id}"
    response = await client.post(base + "/features/point_of_sale/enable", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["is_enabled"] is True
    response = await client.get(base + "/features", headers=headers)
    assert "point_of_sale" in response.json()["enabled"]
    response = await client.get(base, headers=headers)
    assert response.json()["business_roles"] == []
    response = await client.post(base + "/features/point_of_sale/disable", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["is_enabled"] is False


async def test_role_order_noop_and_classification_changes_after_posting(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    from billing_platform.db.types import utcnow

    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    headers = _admin_headers(tenant_a)
    response = await client.post(
        "/v1/companies", headers=headers, json=_valid_company_body() | CLASSIFICATION
    )
    assert response.status_code == 201, response.text
    company_id = uuid.UUID(response.json()["id"])
    with tenant_scope(tenant_a):
        row = await session.get(Company, company_id)
        assert row is not None
        row.first_posted_at = utcnow()
        await session.commit()
    url = f"/v1/companies/{company_id}"
    response = await client.patch(
        url, headers=headers, json={"business_roles": ["distributor", "wholesaler"]}
    )
    assert response.status_code == 200, response.text
    with tenant_scope(tenant_a):
        assert (
            await session.scalar(
                select(func.count(Outbox.id)).where(Outbox.event_type == "company.updated")
            )
            == 0
        )
    response = await client.patch(url, headers=headers, json={"business_category_code": "apparel"})
    assert response.status_code == 200, response.text
    assert response.json()["business_category_code"] == "apparel"


async def test_online_and_store_roles_are_available_and_bindable(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    headers = _admin_headers(tenant_a)
    choices = (await client.get("/v1/company-classifications", headers=headers)).json()
    assert {"online", "store"} <= {row["code"] for row in choices["business_roles"]}
    assert "online" in {row["code"] for row in choices["store_formats"]}
    response = await client.post(
        "/v1/companies",
        headers=headers,
        json=_valid_company_body()
        | {
            "business_roles": ["store", "online"],
            "store_format_code": "online",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["business_roles"] == ["online", "store"]
    assert response.json()["store_format_code"] == "online"
    response = await client.get("/v1/companies/" + response.json()["id"], headers=headers)
    assert response.status_code == 200
    assert response.json()["business_roles"] == ["online", "store"]
    assert response.json()["store_format_code"] == "online"
