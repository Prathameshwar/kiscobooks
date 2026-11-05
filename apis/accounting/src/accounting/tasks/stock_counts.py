"""Protected count snapshots; source calls precede local company transactions."""

import datetime as dt
import hashlib
import uuid
from decimal import Decimal
from fractions import Fraction
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import denied_fields
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    canonical_json,
    execute_idempotent,
    has_retained_command,
)
from billing_platform.ids import uuid7
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from voucher_execution.contracts import DelegatedAuthority
from voucher_execution.quantity import QuantityCapture
from voucher_execution.stock import StockLine
from voucher_execution.stock_facts import StockFenceFacts, StockFenceRequest

from accounting.api.auth import Access
from accounting.domain.stock_costing import CostBucket
from accounting.domain.stock_counting import verified_cost
from accounting.models.stock import (
    StockBalance,
    StockCostLayer,
    StockCostPool,
    StockMovement,
    StockPosition,
    StockPosting,
)
from accounting.models.stock_count import StockCountApplication, StockCountObservation
from accounting.schemas.stock_count import (
    CountDetail,
    CountObservationInput,
    CountScope,
    difference,
)
from accounting.stock_resources import STOCK_MOVEMENT, STOCK_POOL, STOCK_POSITION, STOCK_POSTING
from accounting.tasks.access import authorize, readable, rules, writable
from accounting.tasks.commands import setup_lock
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.stock_effects import permitted
from accounting.tasks.stock_ordering import committed_generation, generation
from accounting.tasks.stock_source_client import StockSourceClient
from accounting.tasks.voucher_money_effects import audit, values

ZERO = Decimal("0.0000")
EMPTY = uuid.UUID(int=0)
SCOPE_FIELDS = ("item_id", "warehouse_id", "bin_id", "lot_id", "stock_date")


def require_access(current: Access, *, write: bool = False) -> None:
    authorize(current, STOCK_POSITION, "read")
    if not {"item_id", "warehouse_id", "bin_id", "lot_id", "quantity"} <= readable(
        current, STOCK_POSITION
    ):
        raise PermissionDeniedError("physical count dimensions and quantities must be readable")
    if not {"quantity", "value", "method"} <= readable(current, STOCK_POOL):
        raise PermissionDeniedError("native count cost evidence must be readable")
    if not {"stock_date", "quantity"} <= readable(current, STOCK_MOVEMENT) or denied_fields(
        frozenset(StockLine.model_fields),
        rules=rules(current, STOCK_MOVEMENT, None),
        access="read",
        target=ScopePath(company_id=current.context.company_id),
    ):
        raise PermissionDeniedError("native physical count evidence must be readable")
    if write:
        authorize(current, STOCK_POSTING, "post")
        if current.actor.impersonation_id:
            raise PermissionDeniedError("support sessions are read only")


async def latest(db: AsyncSession, current: Access, root: uuid.UUID) -> StockCountObservation:
    row = await db.scalar(
        select(StockCountObservation)
        .where(
            StockCountObservation.company_id == current.context.company_id,
            StockCountObservation.root_id == root,
        )
        .order_by(StockCountObservation.revision.desc())
        .limit(1)
    )
    if row is None:
        raise ConflictError("native physical count is unavailable")
    return row


async def position(db: AsyncSession, company: uuid.UUID, scope: Any) -> StockPosition | None:
    row = await db.scalar(
        select(StockPosition)
        .where(
            StockPosition.company_id == company,
            StockPosition.item_id == scope.item_id,
            StockPosition.warehouse_id == scope.warehouse_id,
            StockPosition.bin_key == (scope.bin_id or EMPTY),
            StockPosition.lot_key == (scope.lot_id or EMPTY),
            StockPosition.owner_kind == "COMPANY",
            StockPosition.custody_kind == "WAREHOUSE",
            StockPosition.disposition == "USABLE",
        )
        .with_for_update()
    )
    return row


async def quantities(
    db: AsyncSession, company: uuid.UUID, scope: Any, cutoff: int
) -> tuple[Decimal, Decimal, Decimal]:
    row = await position(db, company, scope)
    if row is None:
        return ZERO, ZERO, ZERO
    balance = await db.scalar(
        select(StockBalance)
        .where(
            StockBalance.company_id == company,
            StockBalance.position_id == row.id,
        )
        .with_for_update()
    )
    ordinal = generation(StockPosting)
    book, later, unverified = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(case((ordinal <= cutoff, StockMovement.quantity), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case((ordinal > cutoff, StockMovement.quantity), else_=0)), 0
                ),
                func.count(case((ordinal.is_(None), 1))),
            )
            .select_from(StockMovement)
            .join(StockPosting, StockPosting.id == StockMovement.posting_id)
            .where(
                StockMovement.company_id == company,
                StockPosting.company_id == company,
                StockMovement.position_id == row.id,
            )
        )
    ).one()
    if unverified or balance is None or book + later != balance.quantity:
        raise ConflictError(
            "count book quantity requires reconciled committed native movement history"
        )
    return book, later, balance.quantity


async def cost_evidence(
    db: AsyncSession, company: uuid.UUID, scope: Any
) -> tuple[StockCostPool | None, Fraction | None]:
    pool = await db.scalar(
        select(StockCostPool)
        .where(
            StockCostPool.company_id == company,
            StockCostPool.item_id == scope.item_id,
            StockCostPool.warehouse_id == scope.warehouse_id,
        )
        .with_for_update()
    )
    if pool is None:
        return None, None
    if pool.last_posting_id is None:
        raise ConflictError("native count cost pool has no verified owner posting")
    posting = await company_object(db, StockPosting, pool.last_posting_id, company_id=company)
    if await committed_generation(db, posting) is None:
        raise ConflictError("native count cost pool has no verified owner receipt")
    layers = (
        list(
            await db.scalars(
                select(StockCostLayer)
                .where(
                    StockCostLayer.company_id == company,
                    StockCostLayer.pool_id == pool.id,
                    StockCostLayer.remaining_quantity > 0,
                )
                .limit(1001)
                .with_for_update()
            )
        )
        if pool.method == "FIFO"
        else []
    )
    if len(layers) > 1000:
        return pool, None
    cost = verified_cost(
        pool.method,
        CostBucket(pool.id, pool.quantity, pool.value),
        [CostBucket(layer.id, layer.remaining_quantity, layer.remaining_value) for layer in layers],
    )
    return pool, cost


async def detail(db: AsyncSession, current: Access, row: StockCountObservation) -> CountDetail:
    require_access(current)
    book, later, actual = await quantities(
        db, current.context.company_id, row, row.cutoff_generation
    )
    if book != row.book_quantity:
        raise ConflictError("native count cutoff history changed; reconcile the count")
    applied = await db.scalar(
        select(StockCountApplication).where(
            StockCountApplication.company_id == row.company_id,
            StockCountApplication.root_id == row.root_id,
        )
    )
    pool, cost = await cost_evidence(db, row.company_id, row)
    review_stale = row.reviewed_unit_cost is not None and (
        row.reviewed_pool_id,
        row.reviewed_pool_version,
    ) != (pool.id if pool else None, pool.row_version if pool else None)
    delta = difference(row.book_quantity, row.observed_quantity)
    return CountDetail(
        **{key: getattr(row, key) for key in CountScope.model_fields},
        id=row.id,
        base_unit_id=row.base_unit_id,
        root_id=row.root_id,
        revision=row.revision,
        cutoff_at=row.cutoff_at,
        cutoff_generation=row.cutoff_generation,
        quantity_increment=row.quantity_increment,
        quantity_decimal_places=row.quantity_decimal_places,
        book_quantity=row.book_quantity,
        observed_quantity=row.observed_quantity,
        quantity_entry=QuantityCapture.model_validate(row.quantity_entry)
        if row.quantity_entry
        else None,
        difference=delta,
        later_quantity=later - applied.difference if applied else later,
        current_quantity=actual,
        status="APPLIED"
        if applied
        else "UNCOUNTED"
        if row.observed_quantity is None
        else "OBSERVED",
        cost_review_required=bool(
            not applied
            and delta is not None
            and delta > 0
            and (review_stale or (cost is None and row.reviewed_unit_cost is None))
        ),
        reviewed_unit_cost=row.reviewed_unit_cost,
        cost_review_reason=row.cost_review_reason,
    )


async def create(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    body: CountScope,
    key: str,
    authority: DelegatedAuthority,
    source: StockSourceClient,
) -> CommandResult[BaseModel]:
    require_access(current, write=True)
    if await has_retained_command(factory, start_identity(current, body, key)):
        return await create_local(factory, current, body, key, None)
    finance = financial_context(current)
    from zoneinfo import ZoneInfo

    if body.stock_date != utcnow().astimezone(ZoneInfo(finance.timezone)).date():
        raise ValidationFailedError("start a physical count on today's company-local date")
    request = StockFenceRequest(
        purpose="PREVIEW",
        tenant_id=current.actor.tenant_id,
        company_id=current.context.company_id,
        execution_id=uuid7(),
        actor_user_id=current.actor.user_id,
        authority=authority,
        authority_expires_at=utcnow() + dt.timedelta(seconds=45),
        stock_date=body.stock_date,
        content_hash=hashlib.sha256(canonical_json(body.model_dump(mode="json"))).hexdigest(),
        item_ids=(body.item_id,),
        warehouse_ids=(body.warehouse_id,),
        bin_ids=(body.bin_id,) if body.bin_id else (),
    )
    facts = await source.acquire(request)
    try:
        return await create_local(factory, current, body, key, facts)
    finally:
        await source.release(facts)


async def create_local(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    body: CountScope,
    key: str,
    facts: StockFenceFacts | None,
) -> CommandResult[BaseModel]:
    async def check(db: AsyncSession, _receipt: dict[str, Any] | None) -> None:
        require_access(current, write=True)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        if facts is None:
            raise ConflictError("native owner proof is required for a first count capture")
        setup = await setup_lock(db, current)
        if (
            facts.company_id != current.context.company_id
            or facts.tenant_id != current.actor.tenant_id
            or facts.actor_user_id != current.actor.user_id
            or facts.stock_date != body.stock_date
            or facts.expires_at <= utcnow()
        ):
            raise ConflictError("count owner scope or proof lifetime differs")
        item = next((row for row in facts.items if row.item_id == body.item_id), None)
        warehouse = next(
            (row for row in facts.warehouses if row.warehouse_id == body.warehouse_id), None
        )
        if (
            item is None
            or warehouse is None
            or item.serial_tracking
            or warehouse.kind == "INTERNAL_TRANSIT"
        ):
            raise ConflictError(
                "this count contract supports company warehouses and non-serial products"
            )
        if (
            item.status != "ACTIVE"
            or item.family_status != "ACTIVE"
            or item.lot_tracking != (body.lot_id is not None)
        ):
            raise ConflictError(
                "count requires an active product and its prepared batch dimensions"
            )
        permitted(item, warehouse, "ADJUSTMENT")
        if body.bin_id and not any(
            row.bin_id == body.bin_id and row.warehouse_id == body.warehouse_id and row.is_active
            for row in facts.bins
        ):
            raise ConflictError("count bin is outside its active warehouse")
        if body.lot_id:
            from accounting.models.stock_tracking import StockLot

            lot = await company_object(
                db, StockLot, body.lot_id, company_id=current.context.company_id
            )
            if lot.item_id != body.item_id or lot.status != "ACTIVE":
                raise ConflictError("count batch is outside the active product")
        writable(current, STOCK_MOVEMENT, {}, {key: getattr(body, key) for key in SCOPE_FIELDS})
        book, _, _ = await quantities(db, current.context.company_id, body, setup.generation)
        identity = uuid7()
        row = StockCountObservation(
            **(values(current) | {"id": identity}),
            **body.model_dump(),
            root_id=identity,
            revision=1,
            cutoff_at=utcnow(),
            cutoff_generation=setup.generation,
            book_quantity=book,
            base_unit_id=item.base_unit_id,
            quantity_increment=item.quantity_increment,
            quantity_decimal_places=item.quantity_decimal_places,
        )
        db.add(row)
        await db.flush()
        audit(db, current, row.id, "stock_count", "start", reason=body.reason)
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        row = await company_object(
            db,
            StockCountObservation,
            uuid.UUID(receipt["id"]),
            company_id=current.context.company_id,
        )
        return await detail(db, current, row)

    return await execute_idempotent(
        factory,
        start_identity(current, body, key),
        authorize=check,
        mutate=mutate,
        render=render,
    )


def start_identity(current: Access, body: CountScope, key: str) -> CommandIdentity:
    return CommandIdentity(
        current.actor.tenant_id,
        current.context.company_id,
        current.actor.user_id,
        "accounting.stock_count.start",
        key,
        body.model_dump(mode="json"),
    )


async def observe(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    identity: uuid.UUID,
    body: CountObservationInput,
    key: str,
) -> CommandResult[BaseModel]:
    async def check(db: AsyncSession, _receipt: dict[str, Any] | None) -> None:
        require_access(current, write=True)
        if body.reviewed_unit_cost is not None:
            current.actor.require_scope(
                "accounting.stock.configure",
                target=ScopePath(company_id=current.context.company_id),
            )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, current)
        original = await company_object(
            db, StockCountObservation, identity, company_id=current.context.company_id
        )
        previous = await latest(db, current, original.root_id)
        if previous.revision != body.expected_revision:
            raise ConflictError("count observation changed; reload before recounting")
        observed = Fraction(body.observed_quantity)
        if (observed * 10**previous.quantity_decimal_places).denominator != 1 or (
            observed / Fraction(previous.quantity_increment)
        ).denominator != 1:
            raise ValidationFailedError("count observation violates its native base quantity grid")
        if body.reviewed_unit_cost is not None and body.observed_quantity <= previous.book_quantity:
            raise ValidationFailedError("explicit cost review belongs only to a surplus count")
        if await db.scalar(
            select(StockCountApplication.id).where(
                StockCountApplication.company_id == previous.company_id,
                StockCountApplication.root_id == previous.root_id,
            )
        ):
            raise ConflictError("an applied count requires a new cutoff and count")
        writable(
            current,
            STOCK_MOVEMENT,
            {},
            {
                "quantity": body.observed_quantity,
                "count": {"observation_id": identity, "expected_revision": previous.revision + 1},
                "quantity_entry": body.quantity_entry,
            },
        )
        pool, _ = await cost_evidence(db, current.context.company_id, previous)
        row = StockCountObservation(
            **values(current),
            **{
                key: getattr(previous, key)
                for key in (
                    *SCOPE_FIELDS,
                    "root_id",
                    "cutoff_at",
                    "cutoff_generation",
                    "book_quantity",
                    "base_unit_id",
                    "quantity_increment",
                    "quantity_decimal_places",
                )
            },
            revision=previous.revision + 1,
            observed_quantity=body.observed_quantity,
            quantity_entry=body.quantity_entry.model_dump(mode="json")
            if body.quantity_entry
            else None,
            reason=body.reason,
            reviewed_unit_cost=body.reviewed_unit_cost,
            cost_review_reason=body.cost_review_reason,
            reviewed_pool_id=pool.id if pool and body.reviewed_unit_cost is not None else None,
            reviewed_pool_version=pool.row_version
            if pool and body.reviewed_unit_cost is not None
            else None,
        )
        db.add(row)
        await db.flush()
        audit(db, current, row.id, "stock_count", "observe", reason=body.reason)
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        row = await company_object(
            db,
            StockCountObservation,
            uuid.UUID(receipt["id"]),
            company_id=current.context.company_id,
        )
        return await detail(db, current, row)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            current.actor.tenant_id,
            current.context.company_id,
            current.actor.user_id,
            "accounting.stock_count.observe",
            key,
            {"id": str(identity), **body.model_dump(mode="json")},
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )
