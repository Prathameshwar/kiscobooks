"""Chunked background impact reviews let a large company publish a reviewed tax release."""

import copy
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, Outbox, ProductFamily
from catalog.models.classification import CatalogPolicyState
from catalog.models.tax_governance import TaxImpactReview
from catalog.tasks import tax_review_worker
from catalog.tasks.identity_source import IdentitySourceSettings
from tests.bulk_factories import proofs
from tests.conftest import ACTOR_SECRET
from tests.tax_factories import seed_tax
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_tax_governance import rates
from tests.test_tax_item_kind import add_services

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")
GUARD = {"expected_generation": 1, "expected_source_version": 2}


def release(ids: dict[str, uuid.UUID]) -> dict[str, Any]:
    return {**GUARD, "change_reason": "Synthetic company-wide rate", "changes": rates(ids, GUARD)}


async def add_items(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    ids: dict[str, uuid.UUID],
    count: int,
) -> None:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            family = await db.get(ProductFamily, ids["product_family"])
            assert family is not None
            db.add_all(
                Item(
                    tenant_id=tenant,
                    company_id=family.company_id,
                    family_id=family.id,
                    default_slot=None,
                    sku=f"BULK-{number:04d}",
                    name=f"Bulk {number}",
                    base_unit_id=ids["unit_of_measure"],
                    sellable=True,
                    purchasable=True,
                    status="DRAFT",
                    row_version=1,
                )
                for number in range(count)
            )


async def start(
    client: httpx.AsyncClient, root: str, auth: dict[str, str], body: dict[str, Any]
) -> dict[str, Any]:
    request = command_headers(auth)
    result = await client.post(root + "/tax-impact-reviews", headers=request, json=body)
    assert result.status_code == 201, result.text
    replay = await client.post(root + "/tax-impact-reviews", headers=request, json=body)
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["id"] == result.json()["id"]
    return dict(result.json())


async def drain(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    root: str,
    ids: dict[str, uuid.UUID],
    review: str,
    **denied: Any,
) -> str:
    company = uuid.UUID(root.rsplit("/", 1)[1])
    for _ in range(40):
        status = await tax_review_worker.step(
            factory,
            proofs(tenant, company, ids["actor_user"], **denied),
            tenant,
            company,
            ids["actor_user"],
            uuid.UUID(review),
        )
        if status != "PENDING":
            return status
    raise AssertionError("tax impact review did not finish within its test bound")


async def events(factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID) -> list[str]:
    with tenant_scope(tenant):
        async with factory() as db:
            return list(
                await db.scalars(
                    select(Outbox.event_type)
                    .where(Outbox.aggregate_type == "catalog.tax_impact_review")
                    .order_by(Outbox.id)
                )
            )


async def test_300_sku_company_publishes_a_rate_through_a_background_review(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    await add_items(factory, tenant_a, ids, 300)
    body = release(ids)
    preview = await client.post(root + "/tax-release-previews", headers=auth, json=body)
    assert preview.status_code == 409 and "background impact review" in preview.text
    review = await start(client, root, auth, body)
    assert review["status"] == "PENDING" and review["item_count"] == 0
    assert "request" not in review
    assert await drain(factory, tenant_a, root, ids, review["id"]) == "COMPLETE"
    detail = await client.get(root + "/tax-impact-reviews/" + review["id"], headers=auth)
    assert detail.status_code == 200, detail.text
    report = detail.json()
    assert report["item_count"] == 301 and report["blocking_count"] == 0
    assert report["checked_count"] >= 301 * 2 and report["completed_at"] is not None
    # The bulk drafts have no SKU-level tax yet, and the seeded definitions start in 2090:
    # reported as missing, but a draft never blocks publication.
    assert report["finding_count"] >= 600
    path = root + "/tax-impact-reviews/" + review["id"] + "/findings"
    seen: list[str] = []
    params: dict[str, Any] = {"limit": 200}
    while True:
        listed = await client.get(path, headers=auth, params=params)
        assert listed.status_code == 200, listed.text
        page = listed.json()
        assert {entry["status"] for entry in page["items"]} == {"MISSING"}
        assert not any(entry["blocking"] for entry in page["items"])
        seen += [entry["id"] for entry in page["items"]]
        if not page["page"]["has_more"]:
            break
        params = {"limit": 200, "cursor": page["page"]["next_cursor"]}
    assert len(seen) == len(set(seen)) == report["finding_count"] and seen == sorted(seen)
    blocking = await client.get(path, headers=auth, params={"blocking": "true"})
    assert blocking.status_code == 200 and blocking.json()["items"] == [], blocking.text
    recorded = await events(factory, tenant_a)
    assert recorded[0] == "catalog.tax_impact_review.start"
    # 301 products in chunks of 16: eighteen full chunks and one short, completing chunk.
    assert set(recorded[1:]) == {"catalog.tax_impact_review.chunk"} and len(recorded) == 20
    request = command_headers(auth)
    commit = {**body, "impact_review_id": review["id"]}
    published = await client.post(root + "/tax-releases", headers=request, json=commit)
    assert published.status_code == 201, published.text
    assert published.json()["policy_generation"] == 2
    # The publication advanced the generation, so the same report cannot publish again.
    again = await client.post(
        root + "/tax-releases",
        headers=command_headers(auth),
        json={**commit, "expected_generation": 2},
    )
    assert again.status_code in {409, 422}, again.text


async def test_policy_change_marks_a_review_stale_and_blocks_publication(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    body = release(ids)
    pending = await start(client, root, auth, body)
    early = await client.post(
        root + "/tax-releases",
        headers=command_headers(auth),
        json={**body, "impact_review_id": pending["id"]},
    )
    assert early.status_code == 409 and "not complete" in early.text
    assert await drain(factory, tenant_a, root, ids, pending["id"]) == "COMPLETE"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            state = await db.scalar(select(CatalogPolicyState))
            assert state is not None
            state.generation += 1
    changed = {**copy.deepcopy(body), "expected_generation": 2}
    for change in changed["changes"]:
        change["definition"]["expected_generation"] = 2
    late = await client.post(
        root + "/tax-releases",
        headers=command_headers(auth),
        json={**changed, "impact_review_id": pending["id"]},
    )
    assert late.status_code == 409, late.text
    # A review still running when the policy moves is invalidated by its next chunk.
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            state = await db.scalar(select(CatalogPolicyState))
            assert state is not None
            state.generation = 1
    second = await start(client, root, auth, {**body, "change_reason": "Second review"})
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            state = await db.scalar(select(CatalogPolicyState))
            assert state is not None
            state.generation = 5
    assert await drain(factory, tenant_a, root, ids, second["id"]) == "STALE"
    stale = await client.get(root + "/tax-impact-reviews/" + second["id"], headers=auth)
    assert stale.json()["reason_code"] == "policy_changed"
    assert "catalog.tax_impact_review.stale" in await events(factory, tenant_a)


async def test_blocking_findings_are_listed_and_prevent_publication(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    services = await add_services(factory, tenant_a, ids)
    body = release(ids)
    review = await start(client, root, auth, body)
    assert await drain(factory, tenant_a, root, ids, review["id"]) == "COMPLETE"
    detail = (await client.get(root + "/tax-impact-reviews/" + review["id"], headers=auth)).json()
    assert detail["blocking_count"] >= 1 and detail["finding_count"] >= 1
    path = root + "/tax-impact-reviews/" + review["id"] + "/findings"
    listed = await client.get(path, headers=auth, params={"blocking": "true", "limit": 1})
    assert listed.status_code == 200, listed.text
    page = listed.json()
    assert [entry["item_id"] for entry in page["items"]] == [str(services["item"])]
    assert page["items"][0]["status"] == "INVALID" and page["items"][0]["blocking"] is True
    if page["page"]["has_more"]:
        following = await client.get(
            path,
            headers=auth,
            params={"blocking": "true", "limit": 1, "cursor": page["page"]["next_cursor"]},
        )
        assert following.status_code == 200, following.text
    blocked = await client.post(
        root + "/tax-releases",
        headers=command_headers(auth),
        json={**body, "impact_review_id": review["id"]},
    )
    assert blocked.status_code == 409 and "incomplete" in blocked.text


async def test_review_permissions_input_and_company_scope(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    foreign_root, foreign_auth, foreign_ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    body = release(ids)
    unauthenticated = await client.post(root + "/tax-impact-reviews", json=body)
    assert unauthenticated.status_code == 401
    for missing in ("tax_rule.publish", "tax_rule.manage"):
        denied = headers(
            company,
            tenant=tenant_a,
            user=ids["actor_user"],
            permission=sorted(CATALOG_PERMISSIONS - {missing}),
        )
        result = await client.post(
            root + "/tax-impact-reviews", headers=command_headers(denied), json=body
        )
        assert result.status_code == 403, result.text
    invalid = await client.post(
        root + "/tax-impact-reviews", headers=command_headers(auth), json={**body, "changes": []}
    )
    assert invalid.status_code == 422, invalid.text
    stale = {**copy.deepcopy(body), "expected_generation": 7}
    for change in stale["changes"]:
        change["definition"]["expected_generation"] = 7
    conflict = await client.post(
        root + "/tax-impact-reviews", headers=command_headers(auth), json=stale
    )
    assert conflict.status_code == 409, conflict.text
    review = await start(client, root, auth, body)
    for both in ({"preview_token": "x", "impact_review_id": review["id"]}, {}):
        result = await client.post(
            root + "/tax-releases", headers=command_headers(auth), json={**body, **both}
        )
        assert result.status_code == 422, result.text
    # Another company's report is never readable or publishable from this company.
    foreign = await start(client, foreign_root, foreign_auth, release(foreign_ids))
    for path in ("", "/findings"):
        result = await client.get(
            root + "/tax-impact-reviews/" + foreign["id"] + path, headers=auth
        )
        assert result.status_code in {403, 404}, result.text
    crossed = await client.post(
        root + "/tax-releases",
        headers=command_headers(auth),
        json={**body, "impact_review_id": foreign["id"]},
    )
    assert crossed.status_code in {403, 404}, crossed.text
    no_items = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"item.read"}),
    )
    hidden = await client.get(
        root + "/tax-impact-reviews/" + review["id"] + "/findings", headers=no_items
    )
    assert hidden.status_code == 403, hidden.text
    searched = await client.get(
        root + "/tax-impact-reviews/" + review["id"] + "/findings",
        headers=auth,
        params={"q": "x"},
    )
    assert searched.status_code == 422, searched.text


async def test_worker_runs_pending_reviews_and_stops_a_denied_requester(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    review = await start(client, root, auth, release(ids))
    settings = tax_review_worker.TaxReviewWorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        identity_source=IdentitySourceSettings(
            base_url="http://127.0.0.1:1",
            request_secret=SecretStr(ACTOR_SECRET),
            response_secrets={"current": SecretStr(ACTOR_SECRET)},
        ),
        source_subscriptions=(CompanyServiceScope(tenant_id=tenant_a, company_id=company),),
    )
    denied: set[str] = set()

    async def fetch(_: Any, **kwargs: Any) -> Any:
        issued = proofs(kwargs["tenant_id"], kwargs["company_id"], kwargs["user_id"])
        chunk = next(proof for proof in issued if proof.permissions == kwargs["permissions"])
        return chunk.model_copy(update={"permissions": chunk.permissions - denied})

    monkeypatch.setattr(tax_review_worker, "fetch_actor_authorization", fetch)
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    assert await tax_review_worker.run_once(factory, settings, cursors) == 1

    async def status(review_id: str) -> tuple[str, str | None]:
        with tenant_scope(tenant_a):
            async with factory() as db:
                row = await db.get(TaxImpactReview, uuid.UUID(review_id))
                assert row is not None
                return row.status, row.reason_code

    assert await status(review["id"]) == ("COMPLETE", None)
    assert await tax_review_worker.run_once(factory, settings, cursors) == 0
    second = await start(client, root, auth, {**release(ids), "change_reason": "Denied run"})
    denied.add("tax_rule.publish")
    assert await tax_review_worker.run_once(factory, settings, cursors) == 0
    assert await status(second["id"]) == ("FAILED", "actor_denied")
    assert "catalog.tax_impact_review.failed" in await events(factory, tenant_a)
