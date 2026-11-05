"""Location fixtures. Feature sets are explicit: location mode is what these tests turn."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Collection, Sequence
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.policy_release import RETIREMENT_AGGREGATE
from catalog.domain.warehouse_resolution import APPLIED
from catalog.schemas.acknowledgements import CONTRACT_VERSION
from catalog.tasks.acknowledgement_worker import EVENT_TYPE, handle_acknowledgement
from catalog.tasks.pricing_commands import business_date
from catalog.tasks.warehouse_operations import open_revision
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers

PERMISSIONS = ("warehouse.read", "warehouse.manage")
#: Retiring a location costs its own key, and reaching the coordinated half of the fence costs
#: the publish and release-read keys too (docs/catalog-warehouses.md §5, CLAUDE.md §5.1).
RETIRE: tuple[str, ...] = (
    *PERMISSIONS,
    "warehouse.deactivate",
    "warehouse.publish",
    "catalog.release.read",
)
MULTI: tuple[str, ...] = ("inventory", "multi_godown")
#: The timezone every seeded company carries (``tests/source_factories``). The release date is
#: the company's business date, not the runner's, so the two must agree or a fixture publishing
#: at 05:00 UTC would date the release yesterday.
COMPANY_TIMEZONE = "Asia/Kolkata"


def feature_facts(company: uuid.UUID, enabled: Collection[str]) -> tuple[SnapshotRecord, ...]:
    return tuple(
        SnapshotRecord(
            kind="feature",
            id=uuid7(),
            data={
                "company_id": str(company),
                "feature_key": key,
                "is_enabled": True,
                "locked_at": None,
            },
        )
        for key in sorted(enabled)
    )


def company_facts(
    company: uuid.UUID, user: uuid.UUID, enabled: Collection[str]
) -> tuple[SnapshotRecord, ...]:
    """`all_facts` always enables inventory, so a metadata-only company drops its features."""
    return (
        *(row for row in all_facts(company, user) if row.kind != "feature"),
        *feature_facts(company, enabled),
    )


async def auth(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    *,
    features: Collection[str] = MULTI,
    permission: Sequence[str] = PERMISSIONS,
    version: int = 2,
    extra: Sequence[SnapshotRecord] = (),
) -> dict[str, str]:
    """``extra`` carries the field policies a test needs; they are Identity's facts, not ours."""
    await setup_source(
        factory,
        tenant,
        company,
        user,
        version=version,
        facts=(*company_facts(company, user, features), *extra),
    )
    return headers(company, tenant=tenant, user=user, permission=list(permission))


async def publish_release(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    current: dict[str, str],
    *,
    effective_date: dt.date | None = None,
    change_reason: str = "fixture release",
) -> dict[str, Any]:
    """Publish the company's whole stock-location policy and return the release as read back.

    The expectations come from the read, as a reviewer's would: the fixture never invents a
    generation, so a test that changed the policy after previewing it still gets the 409.
    """
    route = f"/v1/companies/{company}/policy-releases"
    view = await client.get(route, headers=current)
    assert view.status_code == 200, view.text
    preview = view.json()
    published = await client.post(
        route,
        headers=command_headers(current),
        json={
            "expected_generation": preview["policy_generation"],
            "expected_source_version": preview["source_version"],
            "effective_date": (effective_date or business_date(COMPANY_TIMEZONE)).isoformat(),
            "change_reason": change_reason,
        },
    )
    assert published.status_code == 201, published.text
    detail = await client.get(route + "/" + published.json()["id"], headers=current)
    assert detail.status_code == 200, detail.text
    return dict(detail.json())


def ack_payload(
    tenant: uuid.UUID,
    company: uuid.UUID,
    *,
    aggregate: str,
    aggregate_id: uuid.UUID,
    release_id: uuid.UUID,
    release_revision: int,
    enforced_revision: int,
    result: str = APPLIED,
    reason_code: str | None = None,
) -> dict[str, Any]:
    """One consumer's claim as it travels: no ``consumer`` field, by design (§5)."""
    return {
        "tenant_id": str(tenant),
        "company_id": str(company),
        "release_id": str(release_id),
        "release_revision": release_revision,
        "aggregate": aggregate,
        "aggregate_id": str(aggregate_id),
        "enforced_revision": enforced_revision,
        "result": result,
        "reason_code": reason_code,
        "acknowledged_at": utcnow().isoformat(),
    }


def ack_envelope(
    tenant: uuid.UUID,
    payload: dict[str, Any],
    *,
    message_id: uuid.UUID | None = None,
    event_type: str = EVENT_TYPE,
    schema_version: int = CONTRACT_VERSION,
) -> MessageEnvelope:
    return MessageEnvelope(
        message_id=message_id or uuid7(),
        tenant_id=tenant,
        event_type=event_type,
        schema_version=schema_version,
        occurred_at=utcnow(),
        payload=payload,
    )


async def deliver(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    envelope: MessageEnvelope,
    *,
    companies: dict[uuid.UUID, frozenset[uuid.UUID]],
) -> None:
    """Hand one envelope to the worker's own handler, in its own transaction.

    There is no route that writes an acknowledgement, by design (docs/catalog-warehouses.md §5),
    so a fixture that inserted the row directly would assert against a state the real producer
    cannot reach. Signature verification lives one layer further out, in ``receive_one``.
    """
    with tenant_scope(tenant):
        async with factory() as db:
            await handle_acknowledgement(db, envelope, companies=companies)
            await db.commit()


async def acknowledge(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    *,
    message_id: uuid.UUID | None = None,
    **claim: Any,
) -> None:
    """Deliver one Billing acknowledgement about this company through that path."""
    await deliver(
        factory,
        tenant,
        ack_envelope(tenant, ack_payload(tenant, company, **claim), message_id=message_id),
        companies={tenant: frozenset({company})},
    )


async def clear_retirement(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    warehouse: uuid.UUID,
    *,
    release: dict[str, Any],
    result: str = APPLIED,
    reason_code: str | None = None,
) -> None:
    """Record Billing's verdict on retiring one location, against the policy in force.

    The enforced revision is read from Catalog's own rows rather than passed in: a clearance
    naming a revision Catalog never wrote is refused on ingestion, which is the behaviour the
    fence depends on and not something a fixture should have to restate.
    """
    with tenant_scope(tenant):
        async with factory() as db:
            revision = await open_revision(db, company, warehouse)
            assert revision is not None
    await acknowledge(
        factory,
        tenant,
        company,
        aggregate=RETIREMENT_AGGREGATE,
        aggregate_id=warehouse,
        release_id=uuid.UUID(release["id"]),
        release_revision=int(release["revision"]),
        enforced_revision=revision.revision,
        result=result,
        reason_code=reason_code,
    )


async def retire(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    warehouse: str,
    current: dict[str, str],
    *,
    expected_version: int = 1,
) -> httpx.Response:
    """Take a location through both halves of the fence: publish, clear, then retire."""
    release = await publish_release(client, company, current)
    await clear_retirement(factory, tenant, company, uuid.UUID(warehouse), release=release)
    return await client.post(
        f"/v1/companies/{company}/warehouses/{warehouse}/deactivate",
        headers=command_headers(current),
        json={"expected_version": expected_version},
    )
