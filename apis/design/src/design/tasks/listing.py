"""Keyset paging for every growing list in this service (docs/api-conventions.md).

One codec factory and one page helper, so no endpoint invents its own cursor. The
cursor's context binds the resource, the scope, **the actor** and an authority version
derived from that actor's resolved permissions: a cursor is not authority, and one
minted before a revoke must not keep paging afterwards
(``billing_platform.pagination.cursor_context``).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from billing_platform.errors import ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.pagination import CursorCodec, cursor_context
from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.orm import InstrumentedAttribute

DEFAULT_LIMIT = 50
MAXIMUM_LIMIT = 200

T = TypeVar("T")


def authority_version(actor: Actor) -> str:
    """A short digest of the grants this request was authorized with.

    Changes when a permission is added or removed, which is exactly when a cursor
    minted under the old set must stop working.
    """
    held = ",".join(sorted(actor.permissions))
    return hashlib.sha256(held.encode()).hexdigest()[:32]


def codec(
    secret: bytes,
    *,
    resource: str,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    actor: Actor,
    query: Mapping[str, Any],
) -> CursorCodec:
    return CursorCodec(
        secret,
        context=cursor_context(
            resource=resource,
            tenant_id=tenant_id,
            company_id=company_id,
            actor_id=actor.user_id,
            authority_version=authority_version(actor),
            query=query,
        ),
    )


def after(
    cursor: str | None,
    codec: CursorCodec,
    *,
    created_at: InstrumentedAttribute[dt.datetime],
    identifier: InstrumentedAttribute[uuid.UUID],
) -> ColumnElement[bool] | None:
    """The ``(created_at, id)`` keyset predicate for the next page, newest first.

    ``id`` is the tie-breaker, so a page boundary inside a batch of rows written in the
    same microsecond is still stable (docs/api-conventions.md).
    """
    if not cursor:
        return None
    values = codec.decode(cursor)
    try:
        moment = dt.datetime.fromisoformat(str(values["created_at"]))
        last_id = uuid.UUID(str(values["id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise ValidationFailedError(
            "invalid cursor", fields={"cursor": "malformed, expired, or for another list"}
        ) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return or_(created_at < moment, and_(created_at == moment, identifier < last_id))


def page(
    rows: Sequence[T],
    *,
    limit: int,
    codec: CursorCodec,
    key: Any,
) -> tuple[list[T], str | None, bool]:
    """Split the over-fetched rows into the page, its cursor and ``has_more``."""
    has_more = len(rows) > limit
    items = list(rows[:limit])
    cursor: str | None = None
    if has_more and items:
        moment, identifier = key(items[-1])
        cursor = codec.encode({"created_at": moment.isoformat(), "id": str(identifier)})
    return items, cursor, has_more
