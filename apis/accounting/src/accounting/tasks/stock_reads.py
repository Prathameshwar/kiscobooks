"""Bounded native stock views; immutable history and guarded projections stay separate."""

import uuid
from typing import Any

from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.listing import Page, SortColumn, fetch_page, resolve_sort
from billing_platform.pagination import CursorCodec
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.models.stock import (
    StockBalance,
    StockPosition,
    StockPosting,
    StockValueEntry,
)
from accounting.resources import Resource
from accounting.schemas import stock as s
from accounting.stock_resources import (
    STOCK_MOVEMENT,
    STOCK_POLICY,
    STOCK_POOL,
    STOCK_POSITION,
    STOCK_POSTING,
)
from accounting.tasks.access import authority_fingerprint, authorize, readable

SPECS = {
    "positions": STOCK_POSITION,
    "movements": STOCK_MOVEMENT,
    "postings": STOCK_POSTING,
    "account-policies": STOCK_POLICY,
    "cost-pools": STOCK_POOL,
}
LISTS: dict[str, type[BaseModel]] = {
    "positions": s.StockPositionListItem,
    "movements": s.StockMovementListItem,
    "postings": s.StockPostingListItem,
    "account-policies": s.StockAccountPolicyListItem,
    "cost-pools": s.StockCostPoolListItem,
}


def same_scope(left: Any, right: Any) -> Any:
    return and_(left.tenant_id == right.tenant_id, left.company_id == right.company_id)


def view(current: Access, spec: Resource) -> tuple[Any, dict[str, Any], frozenset[str]]:
    authorize(current, spec, "read")
    model: Any = spec.model
    columns = {key: getattr(model, key) for key in spec.detail.model_fields if hasattr(model, key)}
    statement = select(model.id).where(model.company_id == current.context.company_id)
    allowed = readable(current, spec)
    if spec == STOCK_POOL and (
        "currency" not in allowed
        or any(
            policy.get("entity_type") == "accounting.stock_cost_pool"
            and policy.get("access") == "read"
            and policy.get("effect") == "deny"
            and policy.get("field_key") == "received_value"
            for policy in current.context.policies
        )
    ):
        allowed = allowed - {"value"}
    if spec == STOCK_POSITION:
        statement = statement.join(
            StockBalance,
            and_(same_scope(model, StockBalance), StockBalance.position_id == model.id),
        )
        columns["quantity"] = StockBalance.quantity
    elif spec == STOCK_MOVEMENT:
        statement = (
            statement.join(
                StockPosition,
                and_(same_scope(model, StockPosition), StockPosition.id == model.position_id),
            )
            .join(
                StockValueEntry,
                and_(same_scope(model, StockValueEntry), StockValueEntry.movement_id == model.id),
            )
            .join(
                StockPosting,
                and_(same_scope(model, StockPosting), StockPosting.id == model.posting_id),
            )
        )
        position_allowed = readable(current, STOCK_POSITION)
        posting_allowed = readable(current, STOCK_POSTING)
        for field in ("item_id", "warehouse_id", "bin_id", "lot_id"):
            columns[field] = getattr(StockPosition, field)
            if field not in position_allowed:
                allowed = allowed - {field}
        for field in ("stock_date", "posting_date", "currency"):
            columns[field] = getattr(StockPosting, field)
            if field not in posting_allowed:
                allowed = allowed - {field}
        columns["value"] = StockValueEntry.amount
        # A value has meaning only alongside its readable currency. Quantity and
        # inward value capture denies also cover their immutable effect copies.
        if "currency" not in allowed or any(
            policy.get("entity_type") == "accounting.stock_movement"
            and policy.get("access") == "read"
            and policy.get("effect") == "deny"
            and policy.get("field_key") in {"received_value", "value"}
            for policy in current.context.policies
        ):
            allowed = allowed - {"value"}
    return statement, columns, allowed


async def listing(
    db: AsyncSession, current: Access, resource: str, query: s.StockQuery, secret: bytes
) -> Page[BaseModel]:
    spec, schema = SPECS[resource], LISTS[resource]
    statement, columns, allowed = view(current, spec)
    if query.q:
        raise ValidationFailedError("filter stock by product, warehouse or source reference")
    filters = query.model_dump(exclude_none=True, exclude={"q", "sort", "limit", "cursor"})
    for key, value in filters.items():
        if key not in columns:
            raise ValidationFailedError("unsupported stock filter")
        if key not in allowed:
            raise PermissionDeniedError("stock filter field is not readable")
        statement = statement.where(columns[key] == value)
    fields = set(schema.model_fields) & allowed & columns.keys()
    statement = statement.with_only_columns(*(columns[key].label(key) for key in sorted(fields)))
    terms = resolve_sort(
        query.sort,
        default="-id",
        columns={"id": SortColumn(columns["id"], "uuid")},
        readable=allowed,
        supported=frozenset({("id",), ("-id",)}),
    )
    context = canonical_json(
        {
            "resource": spec.name,
            "tenant": str(current.actor.tenant_id),
            "company": str(current.context.company_id),
            "authority": authority_fingerprint(current),
            "query": query.model_dump(mode="json", exclude={"cursor"}),
        }
    ).decode()
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=CursorCodec(secret, context=context),
        project=lambda row: schema.model_validate(dict(row)),
    )


async def detail(
    db: AsyncSession, current: Access, resource: str, object_id: uuid.UUID
) -> BaseModel:
    from billing_platform.db.access import company_object

    spec = SPECS[resource]
    authorize(current, spec, "read")
    # Object authorization distinguishes an unavailable reference from access to
    # an object that belongs to another company, before projecting any fields.
    await company_object(db, spec.model, object_id, company_id=current.context.company_id)
    statement, columns, allowed = view(current, spec)
    statement = statement.with_only_columns(
        *(columns[key].label(key) for key in sorted(allowed & columns.keys()))
    ).where(spec.model.id == object_id)
    row = (await db.execute(statement)).mappings().one()
    return spec.detail.model_validate(dict(row))
