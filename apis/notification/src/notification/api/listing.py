"""One keyset-pagination implementation for the management list endpoints.

api-conventions §list: signed keyset cursors, an allowlisted stable sort with ``id`` as
tie-breaker, ``limit`` default 50 / max 200. Service-local (the platform owns the codec
and ``validate_sort``; which columns sort and what a row projects to are domain choices).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any

from billing_platform.pagination import CursorCodec, PageRequest, validate_sort
from fastapi import Request
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from sqlalchemy.types import Date, DateTime

from notification.api.control_schemas import Page
from notification.api.schemas import StrictModel


def cursor_codec(request: Request, context: str) -> CursorCodec:
    secret: bytes = request.app.state.settings.cursor_signing_secret.get_secret_value().encode()
    actor = getattr(request.state, "notification_actor", None)
    identity = (
        (str(actor.tenant_id), str(actor.user_id), actor.platform, repr(actor.context.grants))
        if actor
        else ()
    )
    filters = sorted(
        (k, v) for k, v in request.query_params.multi_items() if k not in {"cursor", "limit"}
    )
    bound = hashlib.sha256(
        json.dumps(("notification-cursor-v2", context, identity, filters), default=str).encode()
    ).hexdigest()
    return CursorCodec(secret, context=bound)


def _is_temporal(column: Any) -> bool:
    coltype = column.type
    impl = getattr(coltype, "impl", coltype)
    return isinstance(coltype, Date | DateTime) or isinstance(impl, Date | DateTime)


async def keyset_page(
    db: AsyncSession,
    statement: Select[Any],
    *,
    model: type[Any],
    page: PageRequest,
    sort: str,
    allowed: frozenset[str],
    default: str,
    codec: CursorCodec,
) -> tuple[list[Any], str | None, bool]:
    """Apply the cursor and sort to ``statement`` and fetch one page.

    Returns ``(rows, next_cursor, has_more)``; the tie-breaker is always ``model.id``.
    """
    sort_field, descending = validate_sort(sort, allowed=allowed, default=default)
    sort_col = getattr(model, sort_field)
    id_col = model.id
    temporal = _is_temporal(sort_col)

    if page.cursor:
        values = codec.decode(page.cursor)
        pivot = values[sort_field]
        if temporal:
            pivot = dt.datetime.fromisoformat(pivot)
        pivot_id = uuid.UUID(values["id"])
        comparison = sort_col < pivot if descending else sort_col > pivot
        tie = id_col < pivot_id if descending else id_col > pivot_id
        statement = statement.where(or_(comparison, and_(sort_col == pivot, tie)))

    order = sort_col.desc() if descending else sort_col.asc()
    statement = statement.order_by(order, id_col.desc() if descending else id_col.asc()).limit(
        page.limit + 1
    )
    rows = list((await db.scalars(statement)).all())

    has_more = len(rows) > page.limit
    rows = rows[: page.limit]
    next_cursor: str | None = None
    if has_more:
        last = rows[-1]
        value = getattr(last, sort_field)
        encoded = value.isoformat() if isinstance(value, dt.date | dt.datetime) else value
        next_cursor = codec.encode({sort_field: encoded, "id": str(last.id)})
    return rows, next_cursor, has_more


async def page_of[T: StrictModel](
    db: AsyncSession,
    request: Request,
    model: type[Any],
    schema: type[T],
    *,
    limit: int,
    cursor: str | None,
    where: Any = None,
    sort: str = "id",
) -> Page[T]:
    columns = [getattr(model, name) for name in schema.model_fields if hasattr(model, name)]
    stmt = select(model).options(load_only(*columns))
    if where is not None:
        stmt = stmt.where(where)
    rows, nxt, more = await keyset_page(
        db,
        stmt,
        model=model,
        page=PageRequest(limit, cursor),
        sort=sort,
        allowed=frozenset({"id", "created_at", "observed_at", "started_at", "received_at"}),
        default="id",
        codec=cursor_codec(request, request.url.path),
    )
    from notification.api.schemas import PageMeta

    return Page(
        items=[schema.model_validate(r) for r in rows],
        page=PageMeta(next_cursor=nxt, has_more=more),
    )
