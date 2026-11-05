"""Publishing a numbered stock-location policy release, and reading what is enforced.

docs/catalog-warehouses.md §5. A release is a *delivery boundary*, not a new authority: every
flag in it was already reviewed on its own location's operation-policy revision. What the release
adds is one number a consumer can name — "I enforce release 7" — plus a digest it can check that
claim against.

Three things this module refuses to do, each the opposite of the convenient behaviour:

* **It never takes the manifest from the caller.** A body that could state which locations a
  release covers could omit the one location it just changed, and the consumer reading it would
  enforce a policy the company never approved. Catalog builds the manifest from its own rows.
* **It never publishes a configuration that cannot trade.** Every configured activity default is
  re-resolved through the same chain a document uses, so a release cannot deliver a default that
  will fail later, on a document, in another service.
* **It never says its own release is enforced.** ``delivery_state`` is computed from
  acknowledgements on every read, and a company with no trusted consumer reads ``PENDING``
  forever — which is the honest answer, not a gap to be filled in.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.gateway import Actor
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.policy_release import (
    MANIFEST_LIMIT,
    ManifestEntry,
    assert_effective_date,
    combined_state,
    manifest_digest,
)
from catalog.domain.warehouse_resolution import (
    ACTIVITY_DEFAULTS,
    REJECTED,
    Acknowledgement,
    Location,
    allowed_flags,
    resolve,
)
from catalog.models.pricing import PricingRow
from catalog.models.releases import CatalogPolicyConsumerAck, CatalogPolicyRelease
from catalog.models.warehouses import CompanyWarehouseConfiguration, Warehouse
from catalog.schemas.releases import (
    AcknowledgementDetail,
    PolicyReleaseInput,
    ReleaseDetail,
    ReleaseListItem,
    ReleaseView,
)
from catalog.tasks.acknowledgements import by_release, claims_of, release_rows
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import FieldContext
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import PricingWork, business_date, protected
from catalog.tasks.stock_policy_delivery import acknowledge
from catalog.tasks.warehouse_operations import flag_values, location_state, open_revisions
from catalog.tasks.warehouses import ensure_locations

ENTITY = "catalog.catalog_policy_release"
#: The command framework resolves a receipt's row against this tuple. Only the release is here:
#: an acknowledgement is never written by a command, so no receipt can ever name one.
RELEASE_MODELS: tuple[type[PricingRow], ...] = (CatalogPolicyRelease,)
#: A read stays bounded like every other (docs/api-conventions.md). The complete series lives in
#: the audit log; this projection answers "what is in force, and what came before it".
HISTORY_LIMIT = 50


async def latest_release(db: AsyncSession, company: uuid.UUID) -> CatalogPolicyRelease | None:
    """The highest-numbered release, in force or scheduled.

    This is the numbering and dating predecessor, deliberately including a future-dated release:
    a company that scheduled release 8 for next month cannot publish a 9 that takes force before
    it, or the two would apply in the opposite order to the one they were reviewed in.
    """
    rows = await db.scalars(
        select(CatalogPolicyRelease)
        .where(CatalogPolicyRelease.company_id == company)
        .order_by(CatalogPolicyRelease.revision.desc())
        .limit(1)
    )
    return rows.first()


async def release_in_force(
    db: AsyncSession, company: uuid.UUID, today: dt.date
) -> CatalogPolicyRelease | None:
    """The release actually in effect: the highest-numbered one that has reached its date.

    A scheduled release is not in force, and the retirement fence uses this rather than the
    newest row — a clearance checked against a policy that takes effect next month would not be
    evidence about the policy operating today.
    """
    rows = await db.scalars(
        select(CatalogPolicyRelease)
        .where(
            CatalogPolicyRelease.company_id == company,
            CatalogPolicyRelease.effective_date <= today,
        )
        .order_by(CatalogPolicyRelease.revision.desc())
        .limit(1)
    )
    return rows.first()


async def active_locations(access: ConfigurationAccess, company: uuid.UUID) -> list[Warehouse]:
    """Every active location of the company, bounded by the release limit.

    Bounded rather than paged: a release is a delivery contract, so exceeding the limit is a loud
    failure and not a projection that quietly covers the first page (docs/api-conventions.md).
    Each row is read through the caller's field policy — a publisher who may not read a location
    cannot honestly publish a manifest that covers it.
    """
    await protected(access, Warehouse)
    rows = list(
        await access.db.scalars(
            select(Warehouse)
            .where(Warehouse.company_id == company, Warehouse.is_active.is_(True))
            .order_by(Warehouse.id)
            .limit(MANIFEST_LIMIT + 1)
        )
    )
    for row in rows:
        await access.require(row)
    return rows


async def build_manifest(
    access: ConfigurationAccess,
    config: CompanyWarehouseConfiguration,
    context: FieldContext,
) -> tuple[list[ManifestEntry], dict[str, uuid.UUID | None]]:
    """The location facts this release asks consumers to enforce, from Catalog's own rows.

    Internal transit is included. Resolution never selects it, but its two transfer flags are
    exactly what a typed transfer handler checks when it reaches the row directly (§4), so
    omitting it would leave the one location every transfer touches outside the delivered policy.
    Inactive locations are excluded: a retired location's flags are history, and its disappearance
    from the manifest is how the digest records the retirement.

    Every included location must have a reviewed policy. Publishing a release with an unreviewed
    location in it would deliver "this location may do nothing" as though it had been approved.
    """
    warehouses = await active_locations(access, access.company)
    revisions = await open_revisions(access.db, access.company, [row.id for row in warehouses])
    entries: list[ManifestEntry] = []
    candidates: dict[uuid.UUID, Location] = {}
    for warehouse in warehouses:
        current = revisions.get(warehouse.id)
        if current is None:
            raise ConflictError("review this location's operation policy before publishing")
        entries.append(
            ManifestEntry(
                warehouse_id=warehouse.id,
                revision=current.revision,
                flags=allowed_flags(flag_values(current)),
            )
        )
        candidates[warehouse.id] = location_state(warehouse, config, current)
    defaults: dict[str, uuid.UUID | None] = {}
    for column, operation in ACTIVITY_DEFAULTS.items():
        pointer: uuid.UUID | None = getattr(config, column)
        defaults[column] = pointer
        if pointer is not None:
            # The same chain a document will use, so a default that cannot serve its operation
            # is refused here rather than weeks later. A *cleared* default is deliberately not
            # validated: falling through to Main is the documented behaviour, and an activity
            # blocked even at Main legitimately resolves to no eligible location (§2, §3).
            resolve(
                operation,
                features=context.features,
                candidates=candidates,
                main_warehouse_id=config.main_warehouse_id,
                company_default=pointer,
            )
    return entries, defaults


async def next_release_number(db: AsyncSession, company: uuid.UUID) -> int:
    """One past the highest number ever used, so a release number is never reused."""
    latest = await db.scalar(
        select(func.max(CatalogPolicyRelease.revision)).where(
            CatalogPolicyRelease.company_id == company
        )
    )
    return int(latest or 0) + 1


async def delivery(db: AsyncSession, company: uuid.UUID, release: CatalogPolicyRelease) -> str:
    """One release's delivery state, from every trusted consumer's claim about it."""
    return combined_state(
        release.revision, claims_of(await release_rows(db, company, [release.id]))
    )


async def publish(
    work: PricingWork, body: PolicyReleaseInput, object_id: uuid.UUID | None
) -> PricingRow:
    """Command handler: publish the company's stock-location policy as one numbered release.

    Republishing an unchanged policy on the same date writes nothing and answers with the release
    already in force, the same way an unchanged operation policy does: a numbered row that
    changed nothing would make "when did this become the policy" harder to answer.

    A *rejected* predecessor is the exception. A refusal can be about transient consumer state —
    an open transfer, an unavailable source — so asking again is a legitimate reviewed action,
    and the new number is what lets the consumer tell the second request from a redelivery of the
    first.
    """
    assert object_id is None
    config = await ensure_locations(work)
    await work.publication(body)
    context = await work.access.context(CompanyWarehouseConfiguration)
    entries, defaults = await build_manifest(work.access, config, context)
    digest = manifest_digest(entries, defaults)
    latest = await latest_release(work.db, work.company)
    assert_effective_date(
        body.effective_date,
        today=business_date(context.company.timezone),
        predecessor=None if latest is None else latest.effective_date,
    )
    if (
        latest is not None
        and latest.manifest_digest == digest
        and latest.effective_date == body.effective_date
        and await delivery(work.db, work.company, latest) != REJECTED
    ):
        await acknowledge(
            work, latest, entries, defaults, today=business_date(context.company.timezone)
        )
        return latest
    release = await work.new(
        CatalogPolicyRelease,
        "publish",  # the audited action: a release exists only by being published
        revision=await next_release_number(work.db, work.company),
        effective_date=body.effective_date,
        published_at=utcnow(),
        change_reason=body.change_reason,
        policy_generation=work.state.generation,
        source_version=context.source_version,
        location_count=len(entries),
        default_count=sum(1 for value in defaults.values() if value is not None),
        manifest_digest=digest,
    )
    await work.db.flush()
    await acknowledge(
        work, release, entries, defaults, today=business_date(context.company.timezone)
    )
    return release


def list_item(
    release: CatalogPolicyRelease,
    context: FieldContext,
    values: Mapping[str, Any],
    claims: Mapping[str, Acknowledgement],
) -> ReleaseListItem:
    """Project one release for the history list, through the caller's read policy."""
    readable = context.readable(values)
    return ReleaseListItem.model_validate(
        {
            "id": release.id,
            "revision": release.revision,
            "delivery_state": combined_state(release.revision, claims),
            **{
                key: value
                for key, value in values.items()
                if key in readable and key in ReleaseListItem.model_fields
            },
        }
    )


async def detail(
    access: ConfigurationAccess,
    release: CatalogPolicyRelease,
    context: FieldContext,
    claimed_rows: Sequence[CatalogPolicyConsumerAck],
) -> ReleaseDetail:
    """One release in full, with the acknowledgements that speak about it.

    The rows arrive from the caller, which has already read them for the delivery state: this
    projection and that state are two views of one set of claims, and re-reading them here
    would make a single release read two queries that can disagree.

    The acknowledgements are read through their own entity's context, so the release read and the
    enforcement claims are two separate authority checks rather than one implying the other.
    """
    values = await access.values(release)
    readable = context.readable(values)
    acknowledgements: list[AcknowledgementDetail] = []
    for row in sorted(claimed_rows, key=order):
        await access.require(row)
        claimed = await access.values(row)
        acknowledgements.append(
            AcknowledgementDetail.model_validate(
                {
                    "id": row.id,
                    **{
                        key: value
                        for key, value in claimed.items()
                        if key in AcknowledgementDetail.model_fields
                    },
                }
            )
        )
    return ReleaseDetail.model_validate(
        {
            "id": release.id,
            "revision": release.revision,
            "delivery_state": combined_state(release.revision, claims_of(claimed_rows)),
            "acknowledgements": acknowledgements,
            **{
                key: value
                for key, value in values.items()
                if key in readable and key in ReleaseDetail.model_fields
            },
        }
    )


def order(row: CatalogPolicyConsumerAck) -> str:
    """Stable ordering for the acknowledgements of one release, by the consumer's name."""
    return row.consumer


async def release_view(db: AsyncSession, actor: Actor, company: uuid.UUID) -> ReleaseView:
    """What is in force now, and what came before it.

    ``current`` is the release that has reached its effective date, not the newest row: a release
    scheduled for next month appears in the history and is not yet what any consumer should be
    enforcing. History is returned rather than summarized for the same reason an operation
    policy's is — a reader investigating what was enforced last week needs the release that was
    in force then.
    """
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(CatalogPolicyRelease)
    releases = list(
        await db.scalars(
            select(CatalogPolicyRelease)
            .where(CatalogPolicyRelease.company_id == company)
            .order_by(CatalogPolicyRelease.revision.desc())
            .limit(HISTORY_LIMIT)
        )
    )
    claimed = by_release(await release_rows(db, company, [release.id for release in releases]))
    today = business_date(context.company.timezone)
    current: ReleaseDetail | None = None
    history: list[ReleaseListItem] = []
    for release in releases:
        values = await access.values(release)
        rows = claimed.get(release.id, [])
        history.append(list_item(release, context, values, claims_of(rows)))
        if current is None and release.effective_date <= today:
            current = await detail(access, release, context, rows)
    state = await policy_state(db, actor, company)
    return ReleaseView(
        policy_generation=state.generation if state else 1,
        source_version=context.source_version,
        current=current,
        history=history,
    )


async def release_detail(
    db: AsyncSession, actor: Actor, company: uuid.UUID, object_id: uuid.UUID
) -> ReleaseDetail:
    """One release by id, whether or not it is the one in force."""
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(CatalogPolicyRelease)
    release = await company_object(db, CatalogPolicyRelease, object_id, company_id=company)
    await access.require(release)
    return await detail(access, release, context, await release_rows(db, company, [release.id]))
