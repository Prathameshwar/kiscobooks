"""One keyset-pagination implementation for every list endpoint.

api-conventions §list: growing lists use signed keyset cursors, an allowlisted stable
sort with ``id`` as the tie-breaker, ``limit`` default 50 / max 200, and never a
deep-offset scan or an unconditional count. Hand-rolling that per endpoint is how two
lists drift on cursor shape or forget the tie-breaker, so it lives here once — the
route supplies the filtered statement, the allowed sort set, and the schema to project
each row through.

This is service-local rather than in ``libs/platform`` on purpose: the platform owns
the cursor *codec* and ``validate_sort`` (the mechanism); which columns are sortable
and what a row projects to are domain-visible decisions the platform must not make.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from dataclasses import asdict
from typing import Any

from billing_platform.errors import ValidationFailedError
from billing_platform.pagination import CursorCodec, PageRequest, validate_sort
from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import Select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from sqlalchemy.types import Date, DateTime

from identity.schemas.base import Page, PageMeta


def normalized_query(request: Request) -> list[tuple[str, str]]:
    result = []
    for field in request.scope["route"].dependant.query_params:
        if field.alias in {"cursor", "limit"}:
            continue
        raw = request.query_params.get(field.alias, field.default)
        if raw is None:
            continue
        value, errors = field.validate(raw, {}, loc=("query", field.alias))
        if errors:
            raise ValidationFailedError("invalid cursor query context")
        result.append((field.alias, json.dumps(value, default=str, sort_keys=True)))
    return sorted(result)


def cursor_codec(request: Request, context: str, *, authority_version: str = "") -> CursorCodec:
    """A codec bound to this endpoint's ``context`` — a cursor minted for one list is
    rejected by another, so a client cannot carry a companies cursor into users."""
    secret: bytes = request.app.state.settings.cursor_signing_secret.get_secret_value().encode()
    current = request.state.actor
    grants = sorted(
        json.dumps(
            asdict(g),
            default=lambda value: sorted(value) if isinstance(value, frozenset) else str(value),
            sort_keys=True,
        )
        for g in current.grants
    )
    binding = {
        "endpoint": context,
        "authority_version": authority_version,
        "path": request.url.path,
        "tenant": str(current.tenant_id),
        "actor": str(current.user_id),
        "grants": grants,
        "groups": sorted(str(g) for g in current.group_ids),
        "query": normalized_query(request),
    }
    digest = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    return CursorCodec(secret, context=context + ":" + digest)


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
    projection: type[BaseModel] | None = None,
    extra_columns: frozenset[str] = frozenset(),
    identity_field: str = "id",
) -> tuple[list[Any], str | None, bool]:
    """Apply the cursor and sort to ``statement`` and fetch one page.

    Returns ``(rows, next_cursor, has_more)``. ``rows`` are ORM objects for the route
    to project; the tie-breaker is always ``model.id`` appended after the client sort,
    so the order is total and the cursor unambiguous even when the sort column ties.
    """
    sort_field, descending = validate_sort(sort, allowed=allowed, default=default)
    if projection is not None:
        keys = set(projection.model_fields) | {"id", "tenant_id", sort_field} | extra_columns
        columns = [getattr(model, key) for key in sorted(keys) if key in model.__table__.columns]
        statement = statement.options(load_only(*columns, raiseload=True))
    sort_col = getattr(model, sort_field)
    id_col = getattr(model, identity_field)
    temporal = _is_temporal(sort_col)

    if page.cursor:
        values = codec.decode(page.cursor)
        try:
            if set(values) != {sort_field, identity_field}:
                raise ValueError("cursor shape mismatch")
            pivot = values[sort_field]
            pivot_id = (
                uuid.UUID(values[identity_field])
                if identity_field == "id"
                else values[identity_field]
            )
            if not isinstance(pivot_id, str | uuid.UUID):
                raise ValueError("invalid cursor identity")
            if not isinstance(pivot, str):
                raise ValueError("cursor value must be text")
            if temporal:
                pivot = dt.datetime.fromisoformat(pivot)
            elif sort_field == "id":
                pivot = uuid.UUID(pivot)
        except (KeyError, ValueError, TypeError) as exc:
            raise ValidationFailedError("cursor does not match this list") from exc
        comparison = sort_col < pivot if descending else sort_col > pivot
        statement = statement.where(or_(comparison, and_(sort_col == pivot, id_col > pivot_id)))

    order = sort_col.desc() if descending else sort_col.asc()
    statement = statement.order_by(order, id_col.asc()).limit(page.limit + 1)
    rows = list((await db.scalars(statement)).all())

    has_more = len(rows) > page.limit
    rows = rows[: page.limit]
    next_cursor: str | None = None
    if has_more:
        last = rows[-1]
        value = getattr(last, sort_field)
        encoded = (
            value.isoformat()
            if isinstance(value, dt.date | dt.datetime)
            else str(value)
            if isinstance(value, uuid.UUID)
            else value
        )
        next_cursor = codec.encode(
            {sort_field: encoded, identity_field: str(getattr(last, identity_field))}
        )
    return rows, next_cursor, has_more


async def paged[T: BaseModel](
    db: AsyncSession,
    request: Request,
    statement: Select[Any],
    *,
    model: type[Any],
    schema: type[T],
    limit: int,
    cursor: str | None,
) -> Page[T]:
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=model,
        page=PageRequest(limit, cursor),
        sort="id",
        allowed=frozenset({"id"}),
        default="id",
        codec=cursor_codec(request, model.__tablename__),
        projection=schema,
    )
    return Page[T](
        items=[schema.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )
