"""Operation-policy revisions, policy inheritance on create, and the activity defaults action.

docs/catalog-warehouses.md §2, §3 and §5. This module writes what
``domain/warehouse_resolution`` reads: one numbered revision per change, never an edit of the
row a document already resolved against.

There are no drafts. A publish inserts a revision that is already in force and closes its
predecessor's window in the same transaction, so "immutable once published" is structural
rather than a rule something has to remember — no route can rewrite one. The window is
server-assigned for the same reason resolution ignores it: these are live controls, and a
caller-supplied start would be a backdated permission change (§5).

Writing a revision needs ``warehouse.manage``; *publishing* one adds ``warehouse.publish`` at
the command boundary. The split is what lets a new location inherit Main's reviewed policy on
create without its creator holding publish rights.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.gateway import Actor
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.policy_release import combined_state
from catalog.domain.warehouse_resolution import (
    ACTIVITY_DEFAULTS,
    Acknowledgement,
    Location,
    allowed_flags,
    assert_can_serve,
)
from catalog.domain.warehouses import OPERATION_FLAGS, TRANSIT_CODE
from catalog.models.classification import CatalogPolicyState
from catalog.models.pricing import PricingRow
from catalog.models.warehouses import (
    CompanyWarehouseConfiguration,
    Warehouse,
    WarehouseOperationPolicyRevision,
)
from catalog.schemas.warehouses import (
    ActivityDefaultsInput,
    OperationFlagsInput,
    OperationPolicyInput,
    OperationPolicyPreview,
    OperationPolicyRevisionDetail,
    OperationPolicyView,
    PolicyIssue,
)
from catalog.tasks.acknowledgements import location_claims
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import MANAGE_PERMISSIONS, FieldContext, load_field_context
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import PricingWork, protected, row
from catalog.tasks.warehouses import ensure_locations

ENTITY = "catalog.warehouse_operation_policy_revision"
#: The command framework resolves a receipt's row against this tuple: a publish answers with
#: the revision it wrote, a defaults change with the configuration singleton it repointed.
POLICY_MODELS: tuple[type[PricingRow], ...] = (
    WarehouseOperationPolicyRevision,
    CompanyWarehouseConfiguration,
)
#: Main is provisioned permitting every operation. Anything less would contradict the
#: bootstrap, which points all four company activity defaults at Main: a default that cannot
#: serve its own operation is an error, so the company would start unable to trade (§2, §3).
#: Company capabilities still gate what is reachable — a flag is not a feature.
MAIN_FLAGS: Mapping[str, bool] = dict.fromkeys(OPERATION_FLAGS, True)
#: Transit custody is only ever a transfer leg, and resolution refuses to select it at all.
#: These flags are what a typed transfer handler checks when it reaches the row directly (§4).
TRANSIT_FLAGS: Mapping[str, bool] = {
    flag: flag in {"allow_transfer_in", "allow_transfer_out"} for flag in OPERATION_FLAGS
}
#: A detail read stays bounded like every list (docs/api-conventions.md). The complete trail of
#: who changed which flag and when is the audit log's, not this projection's.
HISTORY_LIMIT = 50


class WarehouseWork(PricingWork):
    """``PricingWork`` with the publication check moved off ``PricePlan``.

    The base class would resolve the expectation check through pricing's field context, which
    demands ``price_plan.read`` from a location administrator. Only the entity whose context is
    loaded changes: the generation is the company's and ``source_version`` is the Identity
    checkpoint, so both expectations mean exactly what they mean everywhere else.
    """

    entity_model: type[PricingRow] = CompanyWarehouseConfiguration
    policy_subject = "location policy"


def flag_values(source: object) -> dict[str, bool]:
    """The eight booleans of a stored revision or a proposal body, in declaration order.

    One reader for both sides of a publish: the proposal and the revision in force are compared
    field by field, and a second inline comprehension that walked a different flag list — or
    forgot the ``bool`` around a column that reads as ``0``/``1`` — would compare unequal
    things and write a revision that changed nothing.
    """
    return {flag: bool(getattr(source, flag)) for flag in OPERATION_FLAGS}


def reserved(warehouse: Warehouse) -> bool:
    """Is this location's operation policy Catalog's rather than a client's?

    Only internal transit. Main's policy *is* editable: §2 lets a company block an activity
    even at its built-in location, and answering "no eligible location" is the documented
    outcome of having done so.
    """
    return warehouse.is_system and warehouse.code == TRANSIT_CODE


async def policy_context(work: PricingWork) -> FieldContext:
    """Load the revision's write context once per unit of work.

    Memoized deliberately: ``ConfigurationAccess.context`` reloads whenever an explicit
    permission is passed, and the bootstrap catch-up would otherwise resolve the same field
    policy twice for one command.
    """
    if ENTITY in work.access.contexts:
        return work.access.contexts[ENTITY]
    context = await work.access.context(
        WarehouseOperationPolicyRevision, MANAGE_PERMISSIONS[ENTITY]
    )
    await protected(work.access, WarehouseOperationPolicyRevision)
    return context


async def open_revision(
    db: AsyncSession, company: uuid.UUID, warehouse_id: uuid.UUID
) -> WarehouseOperationPolicyRevision | None:
    """The revision in force: the one whose window is still open, or ``None`` if unreviewed.

    The one-location form of ``open_revisions``, and only that: at most one window per location
    is open at a time, and two would make "what is allowed here" ambiguous — which has to fail
    loudly rather than resolve to whichever row sorted first. Stating that rule once means the
    batch path and this one cannot come to different conclusions about the same location.
    """
    return (await open_revisions(db, company, [warehouse_id])).get(warehouse_id)


async def open_revisions(
    db: AsyncSession, company: uuid.UUID, warehouse_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, WarehouseOperationPolicyRevision]:
    """``open_revision`` for many locations in one query.

    A product policy validates every location it names against that location's own reviewed
    revision, so the per-location form would be one query per named location — the pattern
    docs/api-conventions.md exists to keep out of a request. The same ambiguity check still
    fires: two open windows anywhere in the batch is a loud conflict, detected by comparing
    the row count with the number of distinct locations they cover.
    """
    keys = set(warehouse_ids)
    if not keys:
        return {}
    rows = list(
        await db.scalars(
            select(WarehouseOperationPolicyRevision)
            .where(
                WarehouseOperationPolicyRevision.company_id == company,
                WarehouseOperationPolicyRevision.warehouse_id.in_(keys),
                WarehouseOperationPolicyRevision.effective_to.is_(None),
            )
            .limit(len(keys) + 1)
        )
    )
    current = {revision.warehouse_id: revision for revision in rows}
    if len(current) != len(rows):
        raise ConflictError("ambiguous stock-location operation policy")
    return current


async def next_number(db: AsyncSession, company: uuid.UUID, warehouse_id: uuid.UUID) -> int:
    """One past the highest number ever used here, so a closed revision is never reused."""
    latest = await db.scalar(
        select(func.max(WarehouseOperationPolicyRevision.revision)).where(
            WarehouseOperationPolicyRevision.company_id == company,
            WarehouseOperationPolicyRevision.warehouse_id == warehouse_id,
        )
    )
    return int(latest or 0) + 1


async def write_revision(
    work: PricingWork, warehouse_id: uuid.UUID, flags: Mapping[str, bool]
) -> WarehouseOperationPolicyRevision:
    """Close the open window and open the next one, at one instant, under the company lock.

    A proposal identical to the revision in force writes nothing and answers with that
    revision. History records reviewed *changes*; a numbered row that changed nothing would
    make the trail longer and "when did this become allowed" harder to answer.

    The predecessor's ``effective_to`` equals the successor's ``effective_from``, so the two
    windows meet with no interval in which nothing was in force.
    """
    await policy_context(work)
    now = utcnow()
    current = await open_revision(work.db, work.company, warehouse_id)
    if current is not None:
        if flag_values(current) == dict(flags):
            return current
        await work.update(current, current.row_version, effective_to=now)
    return await work.new(
        WarehouseOperationPolicyRevision,
        warehouse_id=warehouse_id,
        revision=await next_number(work.db, work.company, warehouse_id),
        effective_from=now,
        effective_to=None,
        **flags,
    )


async def ensure_policies(work: PricingWork, config: CompanyWarehouseConfiguration) -> None:
    """Provision the built-in locations' policies, once per company, with catch-up.

    Reached from ``ensure_locations``, so every location command runs it: a company
    bootstrapped before this shipped acquires its built-in policies on first use instead of
    resolving to "no reviewed policy", which would block trading at Main over a configuration
    Catalog created itself.
    """
    from catalog.tasks.warehouse_foundation import policies

    async def authorize_create() -> None:
        await policy_context(work)

    await policies(work.db, work.company, config, work.new, before_create=authorize_create)


async def publish_policy(
    work: PricingWork, body: OperationPolicyInput, object_id: uuid.UUID | None
) -> PricingRow:
    """Command handler: publish the whole eight-flag policy for one location.

    All eight flags are stated together on purpose. An omitted flag could neither quietly keep
    nor quietly drop what it replaces, and the reviewer approving the change sees the same set
    the resolver will read (§2).
    """
    assert object_id is not None
    await ensure_locations(work)
    await work.publication(body)
    warehouse = await row(work.access, Warehouse, object_id)
    if reserved(warehouse):
        raise ConflictError("internal transit custody has a reserved operation policy")
    return await write_revision(work, warehouse.id, flag_values(body))


def location_state(
    warehouse: Warehouse,
    config: CompanyWarehouseConfiguration,
    revision: WarehouseOperationPolicyRevision | None,
) -> Location:
    """A stored location and its reviewed revision, as the pure resolver expects them.

    ``authorized`` is ``True`` because every caller reached this row through ``row()``, which
    resolved the actor's object-level scope against it first. Resolution refuses to *ignore*
    that decision; it does not make it.

    Kept in one place deliberately: a second mapping that forgot ``is_main`` or defaulted
    ``flags`` to "everything" for an unreviewed location would be a silent widening, and
    nothing downstream could tell.
    """
    return Location(
        id=warehouse.id,
        kind=warehouse.kind,
        is_main=warehouse.id == config.main_warehouse_id,
        is_active=warehouse.is_active,
        authorized=True,
        revision=None if revision is None else revision.revision,
        flags=frozenset() if revision is None else allowed_flags(flag_values(revision)),
    )


async def location_facts(
    access: ConfigurationAccess, warehouse: Warehouse, config: CompanyWarehouseConfiguration
) -> Location:
    """``location_state`` for one location, reading its open window first."""
    current = await open_revision(access.db, access.company, warehouse.id)
    return location_state(warehouse, config, current)


async def set_defaults(
    work: PricingWork, body: ActivityDefaultsInput, object_id: uuid.UUID | None
) -> PricingRow:
    """Command handler: repoint the company's four activity defaults as one reviewed action.

    Each pointer is validated against *its own* operation, so a location that cannot issue
    sales cannot become the sale default and fail weeks later on a document. ``None`` clears a
    default, and resolution then reaches the built-in Main.

    Nothing here moves stock or touches a quantity: it changes which location a later
    operation resolves to, and only among locations already allowed to perform it.

    Concurrency is the generation check in ``publication`` plus the company policy lock, not a
    row version: the caller previewed the configuration as a whole, and any competing write to
    it bumps that generation.
    """
    config = await ensure_locations(work)
    await work.publication(body)
    context = await work.access.context(CompanyWarehouseConfiguration)
    pointers: dict[str, uuid.UUID | None] = {}
    # One location commonly answers for several of the four — after the bootstrap all four are
    # Main — and it is the same row and the same open window each time. Resolving it once per
    # named location keeps every operation checked in its own right, which is the rule here,
    # without four identical reads of the row and its policy.
    candidates: dict[uuid.UUID, Location] = {}
    for column, operation in ACTIVITY_DEFAULTS.items():
        requested: uuid.UUID | None = getattr(body, column)
        if requested is None:
            pointers[column] = None
            continue
        if requested not in candidates:
            warehouse = await row(work.access, Warehouse, requested)
            candidates[requested] = await location_facts(work.access, warehouse, config)
        assert_can_serve(candidates[requested], operation=operation, features=context.features)
        pointers[column] = requested
    await work.update(config, config.row_version, **pointers)
    return config


async def inherit_policy(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    state: CatalogPolicyState,
    warehouse: Warehouse,
) -> frozenset[str]:
    """Give a newly created location Main's reviewed policy, in the create transaction.

    A location with no policy can do nothing, and one that quietly allowed everything would
    infer permissions from the fact that somebody named it — which §2 forbids. Main's current
    revision is the company's own reviewed answer to what a location here may do, so it is the
    template; the new row is a revision 1 of its own and diverges from then on.

    Returns the changed field set so the classification command can authorize a replay against
    it, exactly as identifier requirements do.
    """
    work = PricingWork(ConfigurationAccess(db, actor, company), state)
    config = await ensure_locations(work)
    template = await open_revision(db, company, config.main_warehouse_id)
    if template is None:
        raise ConflictError("the built-in location has no reviewed operation policy")
    await write_revision(work, warehouse.id, flag_values(template))
    return frozenset(work.changed.get(ENTITY, set()))


async def authorize_policy_replay(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    warehouse_id: uuid.UUID,
    changed: frozenset[str],
) -> None:
    """Re-authorize the inherited revision when a retained create receipt is replayed."""
    context = await load_field_context(
        db, actor, company, ENTITY, permission=MANAGE_PERMISSIONS[ENTITY]
    )
    # Revision 1 is the row the original command wrote, and revisions are immutable apart from
    # the window a successor closes. Re-evaluating the predicates against its stored values
    # beats treating every conditional deny as active on a retry.
    inherited = await db.scalar(
        select(WarehouseOperationPolicyRevision).where(
            WarehouseOperationPolicyRevision.company_id == company,
            WarehouseOperationPolicyRevision.warehouse_id == warehouse_id,
            WarehouseOperationPolicyRevision.revision == 1,
        )
    )
    if inherited is None:
        raise ConflictError("the location's inherited operation policy is unavailable")
    values = {field: getattr(inherited, field) for field in context.native.fields}
    context.assert_writable(changed, before={}, after=values)


def revision_detail(
    revision: WarehouseOperationPolicyRevision,
    context: FieldContext,
    values: Mapping[str, Any],
    claims: Mapping[str, Acknowledgement],
) -> OperationPolicyRevisionDetail:
    """Project one revision through the caller's read policy.

    ``delivery_state`` is computed rather than stored: Catalog cannot assert that its own
    revision is being enforced, only that it published it. ``claims`` is every trusted
    consumer's latest word about this location, so a revision newer than what any consumer
    confirmed reads ``PENDING`` — including the one Catalog just wrote (§5).
    """
    readable = context.readable(values)
    return OperationPolicyRevisionDetail.model_validate(
        {
            "id": revision.id,
            "delivery_state": combined_state(revision.revision, claims),
            **{
                key: value
                for key, value in values.items()
                if key in readable and key in OperationPolicyRevisionDetail.model_fields
            },
        }
    )


async def policy_view(
    db: AsyncSession, actor: Actor, company: uuid.UUID, warehouse_id: uuid.UUID
) -> OperationPolicyView:
    """What this location may do now, and what it was allowed to do before.

    History is returned rather than summarized: a reader auditing a movement needs the revision
    that was in force then, not today's flags.
    """
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(WarehouseOperationPolicyRevision)
    warehouse = await company_object(db, Warehouse, warehouse_id, company_id=company)
    revisions = await db.scalars(
        select(WarehouseOperationPolicyRevision)
        .where(
            WarehouseOperationPolicyRevision.company_id == company,
            WarehouseOperationPolicyRevision.warehouse_id == warehouse.id,
        )
        .order_by(WarehouseOperationPolicyRevision.revision.desc())
        .limit(HISTORY_LIMIT)
    )
    claims = await location_claims(db, company, warehouse.id)
    history: list[OperationPolicyRevisionDetail] = []
    current: OperationPolicyRevisionDetail | None = None
    for revision in revisions:
        detail = revision_detail(revision, context, await access.values(revision), claims)
        history.append(detail)
        if revision.effective_to is None:
            current = detail
    state = await policy_state(db, actor, company)
    return OperationPolicyView(
        warehouse_id=warehouse.id,
        policy_generation=state.generation if state else 1,
        source_version=context.source_version,
        current=current,
        history=history,
    )


async def preview(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    warehouse_id: uuid.UUID,
    body: OperationFlagsInput,
) -> OperationPolicyPreview:
    """A dry run of a publish. Writes nothing, allocates nothing, reserves nothing.

    The proposal travels in a body rather than a query string: eight booleans and a reviewer's
    intent do not belong in an access log. Previewing needs only read access, so ``publishable``
    describes the change and never the caller's authority to make it.
    """
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(WarehouseOperationPolicyRevision)
    warehouse = await company_object(db, Warehouse, warehouse_id, company_id=company)
    current = await open_revision(db, company, warehouse.id)
    issues: list[PolicyIssue] = []
    if reserved(warehouse):
        issues.append(
            PolicyIssue(
                code="RESERVED_LOCATION",
                message="internal transit custody has a reserved operation policy",
            )
        )
    proposed = flag_values(body)
    changed = frozenset(
        flag
        for flag, value in proposed.items()
        if current is None or bool(getattr(current, flag)) != value
    )
    if current is not None and not changed:
        issues.append(
            PolicyIssue(
                code="NO_CHANGE",
                message="the proposal matches the revision in force; publishing keeps it",
            )
        )
    number = (
        current.revision
        if current is not None and not changed
        else await next_number(db, company, warehouse.id)
    )
    state = await policy_state(db, actor, company)
    return OperationPolicyPreview(
        warehouse_id=warehouse.id,
        revision=number,
        expected_generation=state.generation if state else 1,
        expected_source_version=context.source_version,
        # What a consumer enforces *today*, against the number this publish would produce. A
        # preview that showed the proposal as applied would be reassuring and wrong: nothing has
        # acknowledged a revision that does not exist yet.
        delivery_state=combined_state(number, await location_claims(db, company, warehouse.id)),
        # `NO_CHANGE` is advisory: that publish is accepted and answers with the revision
        # already in force. A reserved location is the one refusal.
        publishable=not any(issue.code == "RESERVED_LOCATION" for issue in issues),
        changed=sorted(changed & context.readable()),
        issues=issues,
    )
