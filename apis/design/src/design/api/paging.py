"""One pager, so six list routes cannot drift apart.

Each list differs only in its filters; the cursor context, the keyset predicate and the
envelope are identical, and three hand-copied calls per endpoint is how one of them
eventually ships without the keyset predicate — returning page one forever.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from billing_platform.gateway import Actor
from billing_platform.pagination import CursorCodec
from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import ColumnElement
from sqlalchemy.orm import InstrumentedAttribute

from design.api.common import cursor_secret
from design.schemas.page import Page, PageMeta
from design.tasks.listing import after, codec, page


@dataclass(frozen=True, slots=True)
class Pager:
    """A signed cursor bound to this request's resource, scope and authority."""

    codec: CursorCodec

    @classmethod
    def of(
        cls,
        request: Request,
        *,
        resource: str,
        actor: Actor,
        company_id: uuid.UUID,
        query: Mapping[str, Any],
    ) -> Pager:
        return cls(
            codec(
                cursor_secret(request),
                resource=resource,
                tenant_id=actor.tenant_id,
                company_id=company_id,
                actor=actor,
                query=query,
            )
        )

    def keyset(
        self,
        cursor: str | None,
        moment: InstrumentedAttribute[Any],
        identifier: InstrumentedAttribute[uuid.UUID],
    ) -> ColumnElement[bool] | None:
        return after(cursor, self.codec, created_at=moment, identifier=identifier)

    def page[T: BaseModel](
        self,
        rows: Sequence[Any],
        *,
        limit: int,
        item: type[T],
        moment: str = "created_at",
    ) -> Page[T]:
        items, next_cursor, has_more = page(
            rows, limit=limit, codec=self.codec, key=lambda row: (getattr(row, moment), row.id)
        )
        return Page[item](  # type: ignore[valid-type]  # concrete model, resolved at call
            items=[item.model_validate(row) for row in items],
            page=PageMeta(next_cursor=next_cursor, has_more=has_more),
        )
