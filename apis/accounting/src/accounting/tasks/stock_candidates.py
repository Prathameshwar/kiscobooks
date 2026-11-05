"""Read-only eligible stock lookup; it cannot reserve or post an effect."""

import dataclasses
import datetime as dt
import hashlib

from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.listing import Page, SortColumn, fetch_page, resolve_sort
from billing_platform.pagination import CursorCodec
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from voucher_execution.contracts import DelegatedAuthority
from voucher_execution.stock_facts import StockFenceRequest

from accounting.api.auth import Access
from accounting.domain.stock_eligibility import posting_day
from accounting.domain.stock_tracking import normalized
from accounting.models.stock import StockCostPool, StockPosition, StockUnitPosition
from accounting.models.stock_tracking import StockUnit, StockUnitIdentifier
from accounting.schemas.stock import (
    StockAvailableUnitQuery,
    StockSelection,
    StockSelectionInput,
    StockSelectionItem,
)
from accounting.schemas.stock_tracking import SerialListItem
from accounting.stock_resources import BATCH, SERIAL, STOCK_MOVEMENT, STOCK_POSITION
from accounting.tasks.access import authority_fingerprint, authorize, readable
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.stock_effects import permitted
from accounting.tasks.stock_selection import candidates
from accounting.tasks.stock_source_client import StockSourceClient
from accounting.tasks.stock_tracking import identifiers


async def selection(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    body: StockSelectionInput,
    authority: DelegatedAuthority,
    source: StockSourceClient,
) -> StockSelection:
    authorize(current, STOCK_POSITION, "read")
    required = {"item_id", "warehouse_id", "bin_id", "lot_id", "quantity"}
    if not required <= readable(current, STOCK_POSITION):
        raise PermissionDeniedError("stock selection dimensions and quantities must be readable")
    if "stock_date" not in readable(current, STOCK_MOVEMENT):
        raise PermissionDeniedError("stock receipt dates must be readable for selection")
    finance = financial_context(current)
    posting_day(body.stock_date, now=utcnow(), timezone=finance.timezone, last_posted_day=None)
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
    )
    facts = await source.acquire(request)
    item = facts.items[0]
    location = next(row for row in facts.warehouses if row.warehouse_id == body.warehouse_id)
    permitted(item, location, body.operation)
    if item.lot_tracking:
        authorize(current, BATCH, "read")
        if not {"item_id", "status", "is_held", "manufactured_on", "expires_on"} <= readable(
            current, BATCH
        ):
            raise PermissionDeniedError("batch eligibility fields must be readable for selection")
    if item.serial_tracking:
        authorize(current, SERIAL, "read")
        if not {"item_id", "lot_id", "status", "is_held"} <= readable(current, SERIAL):
            raise PermissionDeniedError("serial eligibility fields must be readable for selection")
    async with factory() as db:
        last = await db.scalar(
            select(StockCostPool.last_stock_date).where(
                StockCostPool.company_id == current.context.company_id,
                StockCostPool.item_id == body.item_id,
                StockCostPool.warehouse_id == body.warehouse_id,
            )
        )
        if last is not None and body.stock_date < last:
            raise ConflictError(
                "stock selection predates later warehouse movements; "
                "use a current movement date"
            )
        available = await candidates(
            db,
            company=current.context.company_id,
            item=item,
            warehouse=body.warehouse_id,
            day=body.stock_date,
        )
    return StockSelection(
        company_id=current.context.company_id,
        item_id=body.item_id,
        warehouse_id=body.warehouse_id,
        stock_date=body.stock_date,
        issue_strategy=item.issue_strategy,
        has_more=len(available) > 200,
        items=[
            StockSelectionItem.model_validate(dataclasses.asdict(row)) for row in available[:200]
        ],
    )


async def available_units(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    query: StockAvailableUnitQuery,
    authority: DelegatedAuthority,
    source: StockSourceClient,
    secret: bytes,
) -> Page[SerialListItem]:
    authorize(current, SERIAL, "read")
    authorize(current, STOCK_POSITION, "read")
    allowed = readable(current, SERIAL)
    if not {"item_id", "lot_id", "status", "is_held", "identifiers"} <= allowed:
        raise PermissionDeniedError("serial selection fields must be readable")
    async with factory() as db:
        position = await company_object(
            db,
            StockPosition,
            query.position_id,
            company_id=current.context.company_id,
        )
    choices = await selection(
        factory,
        current,
        StockSelectionInput(
            item_id=position.item_id,
            warehouse_id=position.warehouse_id,
            stock_date=query.stock_date,
            operation=query.operation,
        ),
        authority,
        source,
    )
    origins = [row.origin_id for row in choices.items if row.position_id == position.id]
    columns = {
        key: getattr(StockUnit, key)
        for key in SerialListItem.model_fields
        if hasattr(StockUnit, key) and key in allowed
    }
    statement = (
        select(*(column.label(key) for key, column in columns.items()))
        .select_from(StockUnit)
        .join(
            StockUnitPosition,
            and_(
                StockUnitPosition.company_id == StockUnit.company_id,
                StockUnitPosition.unit_id == StockUnit.id,
            ),
        )
        .where(
            StockUnit.company_id == current.context.company_id,
            StockUnitPosition.position_id == position.id,
            StockUnitPosition.origin_id.in_(origins),
            StockUnit.status == "ACTIVE",
            StockUnit.is_held.is_(False),
        )
    )
    if query.q:
        term = normalized(query.q, maximum=200)
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(
            select(StockUnitIdentifier.id)
            .where(
                StockUnitIdentifier.company_id == current.context.company_id,
                StockUnitIdentifier.unit_id == StockUnit.id,
                StockUnitIdentifier.normalized_value.startswith(escaped, escape="\\"),
            )
            .exists()
        )
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(StockUnit.id, "uuid")},
        readable=allowed,
        supported=frozenset({("id",), ("-id",)}),
    )
    codec = CursorCodec(
        secret,
        context=canonical_json(
            {
                "resource": "available_stock_units",
                "tenant": str(current.actor.tenant_id),
                "company": str(current.context.company_id),
                "authority": authority_fingerprint(current),
                "query": query.model_dump(mode="json", exclude={"cursor"}),
            }
        ).decode(),
    )
    async with factory() as db:
        page = await fetch_page(
            db,
            statement,
            query=query,
            terms=terms,
            codec=codec,
            project=lambda row: SerialListItem.model_validate(dict(row)),
        )
        labels = await identifiers(db, current, [row.id for row in page.items])
        return page.model_copy(
            update={
                "items": [
                    SerialListItem.model_validate(
                        row.model_dump(exclude_unset=True)
                        | {
                            "identifiers": labels.get(row.id, []),
                        }
                    )
                    for row in page.items
                ]
            }
        )
