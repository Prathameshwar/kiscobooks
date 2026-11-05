import uuid
from typing import Any

import httpx
import pytest
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.pricing_factories import create, foundation, publish_price, setup_pricing
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_pricing_resolution import query, reference

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_approval_guard_cannot_relax_a_blocking_minimum(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    _, published = await publish_price(client, root, auth, setup)
    minimum = await create(
        client,
        root,
        auth,
        "/commercial-guard-rules",
        reference(ids, setup, published, amount="110", rule_kind="FIXED_MIN"),
    )
    await create(
        client,
        root,
        auth,
        "/commercial-guard-rules",
        reference(
            ids, setup, minimum, amount="200", rule_kind="FIXED_MAX", severity="REQUIRE_APPROVAL"
        ),
    )
    blocked = await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
    assert blocked.status_code == 409, blocked.text


async def test_sale_draft_edit_does_not_require_purchase_permission(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    permissions = sorted(
        CATALOG_PERMISSIONS
        - {
            "purchase_price.read",
            "purchase_price.manage",
            "reference_cost.read",
            "reference_cost.manage",
        }
    )
    sale = headers(
        uuid.UUID(root.rsplit("/", 1)[1]),
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=permissions,
    )
    body = {
        "series_id": setup["series"]["id"],
        "numeric_revision_id": setup["numeric"]["id"],
        "valid_from": "2090-01-01",
        "price_method": "FIXED",
        "amount": "100",
        "price_basis_quantity": "1",
    }
    draft = await create(client, root, sale, "/price-drafts", body)
    updated = await client.put(
        root + "/price-drafts/" + draft["id"],
        headers=command_headers(sale),
        json={**body, "expected_version": 1, "amount": "101"},
    )
    assert updated.status_code == 200, updated.text


async def test_purchase_reference_is_not_blocked_by_sale_minimum(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids, purpose="PURCHASE")
    _, published = await publish_price(client, root, auth, setup, amount="72")
    await create(
        client,
        root,
        auth,
        "/commercial-guard-rules",
        reference(ids, setup, published, amount="100", rule_kind="FIXED_MIN"),
    )
    result = await client.post(
        root + "/prices/resolve", headers=auth, json=query(ids, purpose="PURCHASE")
    )
    assert result.status_code == 200, result.text
    assert result.json()["amount"] == "72.0000" and result.json()["guard_ids"] == []


async def test_price_pages_do_not_fetch_full_price_details(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from sqlalchemy import event

    from tests.pricing_storage_factories import seed_pricing

    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    engine = factory.kw["bind"].sync_engine
    statements: list[str] = []

    def capture(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = await client.get(f"/v1/companies/{company}/prices", headers=auth)
        assert result.status_code == 200, result.text
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not any("item_price.source_reference" in statement for statement in statements)


async def test_forward_publication_uses_company_business_date(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import datetime as dt

    from catalog.tasks import pricing_commands

    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    # It is already January 2 in this company's Asia/Kolkata timezone.
    monkeypatch.setattr(
        pricing_commands, "utcnow", lambda: dt.datetime(2090, 1, 1, 20, tzinfo=dt.UTC)
    )
    attempted = await client.post(
        root + "/product-mrps",
        headers=command_headers(auth),
        json=reference(ids, setup, setup["series"], jurisdiction="IN"),
    )
    assert attempted.status_code == 409, attempted.text


@pytest.mark.parametrize("field", ["supersedes_id", "expected_previous_version"])
def test_publish_requires_complete_predecessor_reference(field: str) -> None:
    from pydantic import ValidationError

    from catalog.schemas.pricing import PublishInput

    values = {"supersedes_id": str(uuid.uuid4()), "expected_previous_version": 1}
    with pytest.raises(ValidationError, match="predecessor"):
        PublishInput.model_validate(
            {
                "expected_version": 1,
                "expected_generation": 1,
                "expected_source_version": 1,
                field: values[field],
            }
        )


async def test_commercial_scope_detail_requires_its_owner_authority(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from tests.test_master_reference_policy import policy

    root, auth, ids = await setup_pricing(factory, tenant_a)
    scope = await create(
        client,
        root,
        auth,
        "/commercial-policy-scopes",
        {
            "owner_kind": "GROUP",
            "group_id": str(ids["item_group"]),
        },
    )
    await policy(
        factory,
        tenant_a,
        uuid.UUID(root.rsplit("/", 1)[1]),
        ids["actor_user"],
        "catalog.item_group",
        "name",
        "read",
        version=3,
    )
    response = await client.get(root + "/commercial-policy-scopes/" + scope["id"], headers=auth)
    assert response.status_code == 403, response.text


async def test_tier_authority_loading_is_bounded_per_command(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from sqlalchemy import event

    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    engine = factory.kw["bind"].sync_engine
    checks = []

    def capture(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if "FROM field_policy_projection" in statement and "catalog.item_price_tier" in str(
            parameters
        ):
            checks.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        await create(
            client,
            root,
            auth,
            "/price-drafts",
            {
                "series_id": setup["series"]["id"],
                "numeric_revision_id": setup["numeric"]["id"],
                "valid_from": "2090-01-01",
                "price_method": "TIERS",
                "price_basis_quantity": "1",
                "tiers": [
                    {
                        "min_quantity": str(index),
                        "max_quantity": str(index + 1) if index < 3 else None,
                        "amount": "100",
                    }
                    for index in range(4)
                ],
            },
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    # One current context for mutation and a separate current-authority receipt check.
    assert len(checks) <= 2, len(checks)


async def test_maximum_tier_book_publishes_with_original_quantity_selection(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    _, price = await publish_price(
        client,
        root,
        auth,
        setup,
        price_method="TIERS",
        amount=None,
        tiers=[
            {
                "min_quantity": str(index),
                "max_quantity": str(index + 1) if index < 63 else None,
                "amount": str(100 - index),
            }
            for index in range(64)
        ],
    )
    result = await client.post(
        root + "/prices/resolve", headers=auth, json=query(ids, quantity="64")
    )
    assert result.status_code == 200 and result.json()["amount"] == "37.0000", result.text
    assert result.json()["price_id"] == price["id"]


async def test_administrative_selection_authorizes_purchase_book_before_comparing_terms(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from billing_platform.db import tenant_scope
    from sqlalchemy import select

    from catalog.models.pricing import PricePlan
    from tests.pricing_storage_factories import seed_pricing

    company, ids = await seed_pricing(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory() as db:
            purchase = await db.scalar(select(PricePlan).where(PricePlan.purpose == "PURCHASE"))
            assert purchase is not None
            plan_id = str(purchase.id)
    auth = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"purchase_price.read", "purchase_price.manage"}),
    )
    response = await client.post(
        f"/v1/companies/{company}/prices/resolve",
        headers=auth,
        json=query(ids, purpose="SALE", plan_id=plan_id, override_reason="Administrative review"),
    )
    assert response.status_code == 403, response.text
