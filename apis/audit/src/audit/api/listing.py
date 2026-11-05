"""Keyset pagination for the audit read endpoints (api-conventions §list).

Signed keyset cursors, an allowlisted stable sort with a unique tie-breaker, ``limit``
default 50 / max 200. Service-local: the platform owns the codec and ``validate_sort``;
which columns sort and what a row projects to are the service's choice.

The tie-breaker is ``id`` (the second half of the PK), so a page boundary is stable even
when many events share an ``occurred_at`` to the microsecond.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any

from billing_platform.authz import grant_to_wire
from billing_platform.gateway import Actor
from billing_platform.pagination import CursorCodec, PageRequest, validate_sort
from fastapi import Request
from sqlalchemy import Select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date, DateTime


def cursor_codec(request: Request, context: str, current: Actor) -> CursorCodec:
    secret: bytes = request.app.state.settings.cursor_signing_secret.get_secret_value().encode()
    binding = json.dumps(
        {
            "surface": context,
            "tenant": str(current.tenant_id),
            "user": str(current.user_id),
            "actor_user": str(current.real_user_id) if current.real_user_id is not None else None,
            "impersonation": str(current.impersonation_id)
            if current.impersonation_id is not None
            else None,
            "audit_scope": current.audit_scope.model_dump(mode="json")
            if current.audit_scope is not None
            else None,
            "query": sorted(
                (key, value) for key, value in request.query_params.multi_items() if key != "cursor"
            ),
            "grants": [grant_to_wire(grant) for grant in current.grants],
            "policies": [policy.model_dump(mode="json") for policy in current.field_policies]
            if current.field_policies is not None
            else None,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    # The codec embeds its context in every signed cursor. Bind all query and
    # authority facts by digest so a broad administrator still fits the shared
    # size limit. A cursor authorizes nothing: each page checks current access.
    digest = hashlib.sha256(binding.encode()).hexdigest()
    return CursorCodec(secret, context="audit-binding-v2:" + digest)


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
        encoded = value.isoformat() if isinstance(value, dt.date | dt.datetime) else value
        next_cursor = codec.encode({sort_field: encoded, "id": str(last.id)})
    return rows, next_cursor, has_more
