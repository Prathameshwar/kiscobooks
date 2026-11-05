"""Numbered policy releases over HTTP, and the acknowledgements that arrive on the wire.

docs/catalog-warehouses.md §5. Four claims carry this surface, and each is asserted as a refusal
rather than as a convenience:

* the **manifest is Catalog's**, never the caller's — a body cannot narrow what a release covers;
* a release **never takes force behind its publication** or ahead of the one it supersedes;
* Catalog **never reports its own release as enforced**: a company with no trusted consumer reads
  ``PENDING`` forever, and only a signed claim from that consumer changes it;
* retiring a location needs **both halves of the fence**, and the half Catalog does not own is
  reported as *pending* rather than assumed to be permission.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.policy_release import (
    MAX_FUTURE_DAYS,
    OPERATION_POLICY_AGGREGATE,
    RELEASE_AGGREGATE,
    RETIREMENT_AGGREGATE,
)
from catalog.domain.warehouse_resolution import APPLIED, PENDING, REJECTED
from catalog.domain.warehouses import OPERATION_FLAGS
from catalog.events.audit_contract import AUDIT_EVENTS
from catalog.models import Outbox
from catalog.models.releases import CatalogPolicyConsumerAck, CatalogPolicyRelease
from catalog.models.warehouses import Warehouse
from catalog.tasks.pricing_commands import business_date
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.warehouse_factories import (
    COMPANY_TIMEZONE,
    MULTI,
    RETIRE,
    ack_envelope,
    ack_payload,
    acknowledge,
    auth,
    clear_retirement,
    deliver,
    publish_release,
)

#: A reviewer who may read what was delivered and publish nothing.
READER: tuple[str, ...] = ("catalog.release.read",)
ALL_TRUE: dict[str, bool] = dict.fromkeys(OPERATION_FLAGS, True)


def route(company: uuid.UUID) -> str:
    return f"/v1/companies/{company}/policy-releases"


async def provision(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    *,
    godowns: Sequence[str] = (),
    permission: Sequence[str] = RETIRE,
    features: Sequence[str] = MULTI,
) -> dict[str, Any]:
    """A company with its built-in locations, their policies, and ``godowns`` besides."""
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant, company, user, features=features, permission=permission)
    created = await client.post(
        f"/v1/companies/{company}/warehouse-configuration/bootstrap",
        headers=command_headers(current),
        json={},
    )
    assert created.status_code == 201, created.text
    config = await client.get(f"/v1/companies/{company}/warehouse-configuration", headers=current)
    assert config.status_code == 200, config.text
    locations: dict[str, str] = {}
    for code in godowns:
        made = await client.post(
            f"/v1/companies/{company}/warehouses",
            headers=command_headers(current),
            json={"code": code, "name": code.title(), "kind": "GODOWN"},
        )
        assert made.status_code == 201, made.text
        locations[code] = str(made.json()["id"])
    return {
        "company": company,
        "user": user,
        "current": current,
        "config": config.json(),
        "locations": locations,
    }


async def view(client: httpx.AsyncClient, company: uuid.UUID, current: dict[str, str]) -> Any:
    response = await client.get(route(company), headers=current)
    assert response.status_code == 200, response.text
    return response.json()


def body(source: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """A publish body built from the picture the reviewer read."""
    return {
        "expected_generation": source["policy_generation"],
        "expected_source_version": source["source_version"],
        "effective_date": business_date(COMPANY_TIMEZONE).isoformat(),
        "change_reason": "north godown opened",
        **changes,
    }


async def deactivate(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    warehouse: str,
    current: dict[str, str],
    *,
    expected_version: int = 1,
) -> httpx.Response:
    return await client.post(
        f"/v1/companies/{company}/warehouses/{warehouse}/deactivate",
        headers=command_headers(current),
        json={"expected_version": expected_version},
    )


async def rows(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, model: type[Any]
) -> list[Any]:
    with tenant_scope(tenant):
        async with factory() as db:
            return list(await db.scalars(select(model).order_by(model.id)))


async def emitted(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, entity: str
) -> list[Outbox]:
    with tenant_scope(tenant):
        async with factory() as db:
            return list(
                await db.scalars(
                    select(Outbox)
                    .where(Outbox.tenant_id == tenant, Outbox.aggregate_type == entity)
                    .order_by(Outbox.id)
                )
            )


async def test_a_release_delivers_catalogs_own_manifest_and_never_the_callers(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    fixture = await provision(client, factory, tenant_a, godowns=("GD1",))
    company, current = fixture["company"], fixture["current"]
    godown = fixture["locations"]["GD1"]
    before = await view(client, company, current)
    # A company that has never published reads a real answer, not an empty page.
    assert before["current"] is None and before["history"] == []

    # Nothing in the body may narrow what the release covers: a caller who could state the
    # manifest could omit the one location they just changed.
    refused = await client.post(
        route(company), headers=command_headers(current), json=body(before, locations=[godown])
    )
    assert refused.status_code == 422, refused.text

    receipt = command_headers(current)
    published = await client.post(route(company), headers=receipt, json=body(before))
    assert published.status_code == 201, published.text
    assert published.headers["Idempotency-Replayed"] == "false"
    assert published.headers["Cache-Control"] == "no-store"
    result = published.json()
    assert result["row_version"] == 1
    assert result["policy_generation"] == before["policy_generation"] + 1
    replay = await client.post(route(company), headers=receipt, json=body(before))
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == result

    after = await view(client, company, current)
    release = after["current"]
    assert release["id"] == result["id"] and release["revision"] == 1
    # Catalog can say what it published and nothing more: enforcement is the consumer's word.
    assert release["delivery_state"] == PENDING and release["acknowledgements"] == []
    assert release["change_reason"] == "north godown opened"
    assert release["effective_date"] == business_date(COMPANY_TIMEZONE).isoformat()
    # Main, internal transit and the godown — custody included, because a typed transfer handler
    # reads its two flags directly (§4). Bootstrap points all four activity defaults at Main.
    assert release["location_count"] == 3 and release["default_count"] == 4
    assert len(release["manifest_digest"]) == 64
    assert [entry["revision"] for entry in after["history"]] == [1]

    # Republishing an unchanged policy on the same date answers with the release in force: a
    # numbered row that changed nothing would make "when did this become the policy" harder.
    again = await client.post(route(company), headers=command_headers(current), json=body(after))
    assert again.status_code == 201, again.text
    assert again.json()["id"] == result["id"]
    assert len(await rows(factory, tenant_a, CatalogPolicyRelease)) == 1

    # A reviewed change to any location's policy changes the digest, so the next release is a
    # new number rather than the same delivery restated.
    policy = f"/v1/companies/{company}/warehouses/{godown}/operation-policy"
    reviewed = await client.get(policy, headers=current)
    assert reviewed.status_code == 200, reviewed.text
    narrowed = await client.post(
        policy + "/publish",
        headers=command_headers(current),
        json={
            **ALL_TRUE,
            "allow_sale_issue": False,
            "expected_generation": reviewed.json()["policy_generation"],
            "expected_source_version": reviewed.json()["source_version"],
        },
    )
    assert narrowed.status_code == 201, narrowed.text
    second = await client.post(
        route(company),
        headers=command_headers(current),
        json=body(await view(client, company, current)),
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] != result["id"]
    stored = await rows(factory, tenant_a, CatalogPolicyRelease)
    assert [row.revision for row in stored] == [1, 2]
    assert stored[0].manifest_digest != stored[1].manifest_digest
    # A release is immutable: the predecessor keeps every fact it was published with.
    assert stored[0].location_count == stored[1].location_count == 3

    events = await emitted(factory, tenant_a, "catalog.catalog_policy_release")
    assert [row.event_type for row in events] == ["catalog.catalog_policy_release.publish"] * 2
    assert {row.event_type for row in events} <= AUDIT_EVENTS
    assert events[0].payload["category"] == "admin"
    # The release is what an auditor reads to answer "which policy took force, when, over what",
    # so its own evidence carries those values rather than bare change markers — even though the
    # audited action is named `publish` rather than `create` (docs/audit.md §5.2).
    assert events[0].payload["changes"]["revision"] == {"from": None, "to": "1"}
    assert events[0].payload["changes"]["effective_date"] == {
        "from": None,
        "to": business_date(COMPANY_TIMEZONE).isoformat(),
    }
    assert events[0].payload["changes"]["manifest_digest"] == {
        "from": None,
        "to": stored[0].manifest_digest,
    }
    assert events[1].payload["changes"]["revision"] == {"from": None, "to": "2"}
    assert events[0].payload["company_id"] == str(company)
    assert events[0].payload["actor_type"] == "user"


async def test_a_release_takes_force_on_its_date_and_in_the_reviewed_order(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """A scheduled release is in the history and is not yet what a consumer should enforce."""
    fixture = await provision(client, factory, tenant_a)
    company, current = fixture["company"], fixture["current"]
    today = business_date(COMPANY_TIMEZONE)
    first = await view(client, company, current)
    for date in (today - dt.timedelta(days=1), today + dt.timedelta(days=MAX_FUTURE_DAYS + 1)):
        refused = await client.post(
            route(company),
            headers=command_headers(current),
            json=body(first, effective_date=date.isoformat()),
        )
        assert refused.status_code == 422, (date, refused.text)
    in_force = await publish_release(client, company, current)
    assert in_force["revision"] == 1

    scheduled = await client.post(
        route(company),
        headers=command_headers(current),
        json=body(
            await view(client, company, current),
            effective_date=(today + dt.timedelta(days=30)).isoformat(),
        ),
    )
    assert scheduled.status_code == 201, scheduled.text
    now = await view(client, company, current)
    # The release in force is the one that reached its date, not the newest row.
    assert now["current"]["id"] == in_force["id"] and now["current"]["revision"] == 1
    assert [entry["revision"] for entry in now["history"]] == [2, 1]
    assert now["history"][0]["effective_date"] == (today + dt.timedelta(days=30)).isoformat()

    # Ahead in number, behind in date: the reviewed order and the dated order would disagree.
    for date in (today, today + dt.timedelta(days=29)):
        conflicted = await client.post(
            route(company),
            headers=command_headers(current),
            json=body(now, effective_date=date.isoformat()),
        )
        assert conflicted.status_code == 409, (date, conflicted.text)
        message = conflicted.json()["error"]["message"]
        assert message.startswith("a policy release cannot take force")
    assert len(await rows(factory, tenant_a, CatalogPolicyRelease)) == 2


async def test_a_release_is_pending_until_billing_says_it_enforces_that_revision(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    fixture = await provision(client, factory, tenant_a, godowns=("GD1",))
    company, current = fixture["company"], fixture["current"]
    godown = uuid.UUID(fixture["locations"]["GD1"])
    release = await publish_release(client, company, current)
    identity, revision = uuid.UUID(release["id"]), int(release["revision"])

    claim: dict[str, Any] = {
        "aggregate": RELEASE_AGGREGATE,
        "aggregate_id": identity,
        "release_id": identity,
        "release_revision": revision,
        "enforced_revision": revision,
    }
    await acknowledge(factory, tenant_a, company, **claim)
    enforced = await view(client, company, current)
    assert enforced["current"]["delivery_state"] == APPLIED
    assert [entry["delivery_state"] for entry in enforced["history"]] == [APPLIED]
    spoken = enforced["current"]["acknowledgements"]
    assert [(row["consumer"], row["result"], row["enforced_revision"]) for row in spoken] == [
        ("billing", APPLIED, revision)
    ]
    assert spoken[0]["reason_code"] is None

    # A redelivered or reordered claim is ordinary broker behaviour, so it changes nothing: one
    # row, and no second audit event to make a reader think Billing spoke twice.
    await acknowledge(factory, tenant_a, company, **claim)
    stored = await rows(factory, tenant_a, CatalogPolicyConsumerAck)
    assert len(stored) == 1 and stored[0].row_version == 1
    events = await emitted(factory, tenant_a, "catalog.catalog_policy_consumer_ack")
    assert [row.event_type for row in events] == ["catalog.catalog_policy_consumer_ack.create"]
    assert {row.event_type for row in events} <= AUDIT_EVENTS
    # Nobody authorized this write; a signed event did (docs/audit.md §5.2).
    assert events[0].payload["actor_user_id"] is None
    assert events[0].payload["actor_type"] == "service"
    assert events[0].payload["category"] == "system"

    # At one revision a claim may only weaken: "it works now" needs new evidence.
    await acknowledge(
        factory, tenant_a, company, result=REJECTED, reason_code="STOCK_ON_HAND", **claim
    )
    weakened = await view(client, company, current)
    assert weakened["current"]["delivery_state"] == REJECTED
    assert weakened["current"]["acknowledgements"][0]["reason_code"] == "STOCK_ON_HAND"
    await acknowledge(factory, tenant_a, company, **claim)
    assert (await view(client, company, current))["current"]["delivery_state"] == REJECTED
    advanced = await rows(factory, tenant_a, CatalogPolicyConsumerAck)
    assert len(advanced) == 1 and advanced[0].row_version == 2
    spoke = await emitted(factory, tenant_a, "catalog.catalog_policy_consumer_ack")
    assert [row.event_type.rsplit(".", 1)[1] for row in spoke] == ["create", "update"]

    # A location's own policy read reports the same arithmetic about its own revision.
    policy = f"/v1/companies/{company}/warehouses/{godown}/operation-policy"
    pending = await client.get(policy, headers=current)
    assert pending.json()["current"]["delivery_state"] == PENDING
    await acknowledge(
        factory,
        tenant_a,
        company,
        aggregate=OPERATION_POLICY_AGGREGATE,
        aggregate_id=godown,
        release_id=identity,
        release_revision=revision,
        enforced_revision=1,
    )
    located = await client.get(policy, headers=current)
    assert located.json()["current"]["delivery_state"] == APPLIED
    assert located.json()["history"][0]["delivery_state"] == APPLIED


async def test_an_acknowledgement_about_something_catalog_never_published_is_refused(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    """A consumer is trusted about its own half only: what it enforces, not what exists."""
    fixture = await provision(client, factory, tenant_a, godowns=("GD1",))
    company, current = fixture["company"], fixture["current"]
    godown = fixture["locations"]["GD1"]
    release = await publish_release(client, company, current)
    identity, revision = uuid.UUID(release["id"]), int(release["revision"])
    subscription = {tenant_a: frozenset({company})}

    def payload(**changes: Any) -> dict[str, Any]:
        return {
            **ack_payload(
                tenant_a,
                company,
                aggregate=RELEASE_AGGREGATE,
                aggregate_id=identity,
                release_id=identity,
                release_revision=revision,
                enforced_revision=revision,
            ),
            **changes,
        }

    for changes in (
        # A release Catalog never wrote, and a real release at a number it never had.
        {"release_id": str(uuid7()), "aggregate_id": str(uuid7())},
        {"release_revision": revision + 1},
        # A release-level claim whose subject or enforced number is not that release.
        {"aggregate_id": godown},
        {"enforced_revision": revision + 1},
        # A company this deployment was not given, and a tenant it does not serve.
        {"company_id": str(uuid7())},
        {"tenant_id": str(tenant_b)},
        # A refusal with no reason, and an acceptance carrying one.
        {"result": REJECTED},
        {"reason_code": "STOCK_ON_HAND"},
        # A location claim about a revision Catalog never wrote would make every later revision
        # read as applied for good, from one message.
        {"aggregate": OPERATION_POLICY_AGGREGATE, "aggregate_id": godown, "enforced_revision": 9},
        {"aggregate": RETIREMENT_AGGREGATE, "aggregate_id": str(uuid7())},
    ):
        with pytest.raises(ValidationFailedError):
            await deliver(
                factory,
                tenant_a,
                ack_envelope(tenant_a, payload(**changes)),
                companies=subscription,
            )
    # The contract version is pinned rather than negotiated, and the routing key is not a hint.
    for envelope in (
        ack_envelope(tenant_a, payload(), event_type="billing.something.else"),
        ack_envelope(tenant_a, payload(), schema_version=99),
    ):
        with pytest.raises(ValidationFailedError):
            await deliver(factory, tenant_a, envelope, companies=subscription)

    assert await rows(factory, tenant_a, CatalogPolicyConsumerAck) == []
    assert await emitted(factory, tenant_a, "catalog.catalog_policy_consumer_ack") == []
    # The release itself is untouched by every one of those refusals.
    assert (await view(client, company, current))["current"]["delivery_state"] == PENDING


async def test_retiring_a_location_needs_both_halves_of_the_fence(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    native_retirement,
) -> None:
    """Absence of a clearance is *pending*, never permission (docs/catalog-warehouses.md §5)."""
    fixture = await provision(client, factory, tenant_a, godowns=("GD1", "GD2", "GD3"))
    company, current = fixture["company"], fixture["current"]
    first, second = fixture["locations"]["GD1"], fixture["locations"]["GD2"]
    third = fixture["locations"]["GD3"]

    # Retirement is the one location action that can strand stock, so it carries its own key.
    manager = headers(
        company,
        tenant=tenant_a,
        user=fixture["user"],
        permission=["warehouse.read", "warehouse.manage"],
    )
    unpermitted = await deactivate(client, company, first, manager)
    assert unpermitted.status_code == 403, unpermitted.text
    assert unpermitted.json()["error"]["message"].endswith("warehouse.deactivate")

    unreleased = await deactivate(client, company, first, current)
    assert unreleased.status_code == 409, unreleased.text
    assert unreleased.json()["error"]["message"].startswith("publish a stock-location policy")

    release = await publish_release(client, company, current)
    native_retirement.unavailable = True
    pending = await deactivate(client, company, first, current)
    assert pending.status_code == 503, pending.text
    assert pending.json()["error"]["code"] == "source_unavailable"
    assert "stock retirement" in pending.json()["error"]["message"]
    native_retirement.unavailable = False
    native_retirement.blocked[uuid.UUID(first)] = "STOCK_ON_HAND"

    # A refusal is a 409 carrying its safe reason code: the caller can act on stock on hand.
    await clear_retirement(
        factory,
        tenant_a,
        company,
        uuid.UUID(first),
        release=release,
        result=REJECTED,
        reason_code="STOCK_ON_HAND",
    )
    refused = await deactivate(client, company, first, current)
    assert refused.status_code == 409, refused.text
    assert "physical stock" in refused.json()["error"]["message"]
    # And it does not lift on the same evidence: at one revision a claim may only weaken.
    await clear_retirement(factory, tenant_a, company, uuid.UUID(first), release=release)
    assert (await deactivate(client, company, first, current)).status_code == 409

    # A clearance names one location. GD3's says nothing about GD2.
    await clear_retirement(factory, tenant_a, company, uuid.UUID(third), release=release)
    native_retirement.unavailable_warehouses.add(uuid.UUID(second))
    assert (await deactivate(client, company, second, current)).status_code == 503
    await clear_retirement(factory, tenant_a, company, uuid.UUID(second), release=release)
    # A cached acknowledgement never substitutes for a current native check.
    assert (await deactivate(client, company, second, current)).status_code == 503
    native_retirement.unavailable_warehouses.remove(uuid.UUID(second))
    retired = await deactivate(client, company, second, current)
    assert retired.status_code == 200, retired.text

    # Retiring GD2 changed the manifest, so this is a new number rather than the same delivery
    # restated — and GD3's clearance was never checked against the policy now in force.
    later = await publish_release(client, company, current)
    assert later["revision"] == 2 and later["location_count"] == 4
    native_retirement.unavailable_warehouses.add(uuid.UUID(third))
    stale = await deactivate(client, company, third, current)
    assert stale.status_code == 503, stale.text
    assert "stock retirement" in stale.json()["error"]["message"]
    await clear_retirement(factory, tenant_a, company, uuid.UUID(third), release=later)
    native_retirement.unavailable_warehouses.remove(uuid.UUID(third))
    assert (await deactivate(client, company, third, current)).status_code == 200

    with tenant_scope(tenant_a):
        async with factory() as db:
            active = await db.scalars(select(Warehouse.code).where(Warehouse.is_active.is_(True)))
            assert sorted(active) == ["GD1", "MAIN", "TRANSIT"]


async def test_release_routes_are_permissioned_company_scoped_and_closed(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    fixture = await provision(client, factory, tenant_a)
    company, user, current = fixture["company"], fixture["user"], fixture["current"]
    release = await publish_release(client, company, current)
    target = route(company) + "/" + release["id"]
    latest = await view(client, company, current)

    assert (await client.get(route(company))).status_code == 401
    assert (await client.get(target)).status_code == 401
    assert (await client.post(route(company), json=body(latest))).status_code == 401

    for permission in ("item.read", "warehouse.read"):
        wrong = headers(company, tenant=tenant_a, user=user, permission=permission)
        assert (await client.get(route(company), headers=wrong)).status_code == 403, permission
        assert (await client.get(target, headers=wrong)).status_code == 403, permission
    # Reading what was delivered is its own grant, and it publishes nothing.
    reader = headers(company, tenant=tenant_a, user=user, permission=list(READER))
    assert (await client.get(route(company), headers=reader)).status_code == 200
    assert (await client.get(target, headers=reader)).status_code == 200
    assert (
        await client.post(route(company), headers=command_headers(reader), json=body(latest))
    ).status_code == 403
    # Publishing costs the publish key on top of manage: the flags were reviewed one location
    # at a time, and the release states that the whole set is what consumers must enforce.
    for incomplete in (
        ("warehouse.read", "warehouse.manage", "catalog.release.read"),
        ("warehouse.read", "warehouse.publish", "catalog.release.read"),
    ):
        partial = headers(company, tenant=tenant_a, user=user, permission=list(incomplete))
        response = await client.post(
            route(company), headers=command_headers(partial), json=body(latest)
        )
        assert response.status_code == 403, (incomplete, response.text)

    # Right permission, wrong company: the object is forbidden, not hidden.
    other = await provision(client, factory, tenant_a)
    foreign = other["current"]
    assert (await client.get(route(company), headers=foreign)).status_code == 403
    assert (await client.get(target, headers=foreign)).status_code == 403
    assert (
        await client.post(route(company), headers=command_headers(foreign), json=body(latest))
    ).status_code == 403
    # Its own company, another company's release: forbidden, the same way round. Within one tenant
    # a mismatched company is refused rather than hidden (`company_object`); hiding is the tenant
    # boundary's job, which the next assertion covers.
    assert (
        await client.get(route(other["company"]) + "/" + release["id"], headers=foreign)
    ).status_code == 403
    # Another tenant is not told the release exists.
    alien = await auth(factory, tenant_b, company, uuid7(), permission=RETIRE)
    assert (await client.get(target, headers=alien)).status_code == 404
    unknown = await client.get(route(company) + "/" + str(uuid7()), headers=current)
    assert unknown.status_code == 404, unknown.text

    collection = await client.get(route(company), headers=current, params={"limit": 1})
    assert collection.status_code == 422, collection.text
    assert (await client.get(target, headers=current, params={"as_of": "x"})).status_code == 422
    # A money-free command still takes a receipt: without one the request is not idempotent.
    assert (
        await client.post(route(company), headers=current, json=body(latest))
    ).status_code == 422
    for invalid in (
        {key: value for key, value in body(latest).items() if key != "change_reason"},
        {**body(latest), "change_reason": ""},
        {**body(latest), "change_reason": "x" * 501},
        {**body(latest), "effective_date": "2026-13-01"},
        {**body(latest), "effective_date": None},
        {**body(latest), "expected_generation": 0},
        {**body(latest), "expected_source_version": "3"},
        {**body(latest), "revision": 9},
    ):
        response = await client.post(route(company), headers=command_headers(current), json=invalid)
        assert response.status_code == 422, (invalid, response.text)
    stale = await client.post(
        route(company),
        headers=command_headers(current),
        json=body(latest, expected_generation=latest["policy_generation"] + 1),
    )
    assert stale.status_code == 409, stale.text
    assert len(await rows(factory, tenant_a, CatalogPolicyRelease)) == 1


async def test_releases_and_acknowledgements_are_tenant_isolated(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    """One company identifier, two tenants: neither sees the other's delivery history."""
    company = uuid7()
    published: dict[uuid.UUID, dict[str, Any]] = {}
    for tenant in (tenant_a, tenant_b):
        current = await auth(factory, tenant, company, uuid7(), permission=RETIRE)
        created = await client.post(
            f"/v1/companies/{company}/warehouse-configuration/bootstrap",
            headers=command_headers(current),
            json={},
        )
        assert created.status_code == 201, created.text
        published[tenant] = {
            "release": await publish_release(client, company, current),
            "headers": current,
        }
    # Only one tenant's consumer speaks, so the other must still read its own release as pending.
    spoken = published[tenant_a]["release"]
    identity = uuid.UUID(spoken["id"])
    await acknowledge(
        factory,
        tenant_a,
        company,
        aggregate=RELEASE_AGGREGATE,
        aggregate_id=identity,
        release_id=identity,
        release_revision=int(spoken["revision"]),
        enforced_revision=int(spoken["revision"]),
    )
    # The same number in both tenants, and each reads only its own delivery state.
    assert published[tenant_a]["release"]["id"] != published[tenant_b]["release"]["id"]
    assert published[tenant_a]["release"]["revision"] == 1
    assert published[tenant_b]["release"]["revision"] == 1
    for tenant, state in ((tenant_a, APPLIED), (tenant_b, PENDING)):
        seen = await view(client, company, published[tenant]["headers"])
        assert seen["current"]["delivery_state"] == state
        assert seen["current"]["id"] == published[tenant]["release"]["id"]
    other = published[tenant_b]["release"]["id"]
    assert (
        await client.get(route(company) + "/" + other, headers=published[tenant_a]["headers"])
    ).status_code == 404

    for tenant, acknowledgements in ((tenant_a, 1), (tenant_b, 0)):
        with tenant_scope(tenant):
            async with factory() as db:
                releases = list(await db.scalars(select(CatalogPolicyRelease)))
                assert [row.id for row in releases] == [
                    uuid.UUID(published[tenant]["release"]["id"])
                ]
                assert {row.tenant_id for row in releases} == {tenant}
                counted = await db.scalar(select(func.count(CatalogPolicyConsumerAck.id)))
                assert counted == acknowledgements
