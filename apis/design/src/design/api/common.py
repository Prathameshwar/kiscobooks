"""Session, error documentation and paging primitives shared by the routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

from billing_platform.db import tenant_scope
from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from design.api.auth import Access, access
from design.tasks.listing import MAXIMUM_LIMIT

ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorEnvelope} for code in (400, 401, 403, 404, 409, 413, 422, 429, 503)
}

#: Page size, with the platform's ceiling (docs/api-conventions.md).
Limit = Annotated[int, Query(ge=1, le=MAXIMUM_LIMIT)]
Cursor = Annotated[str | None, Query(max_length=4096)]


async def session(
    request: Request, current: Access = Depends(access)
) -> AsyncIterator[AsyncSession]:
    """Guarded session bound to this actor's tenant for the whole request.

    The tenant filter is session-level, never per-query discipline (CLAUDE.md §5.3): one
    forgotten ``WHERE`` would be a cross-tenant read, so no query here carries one.
    """
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            yield db


def unique_query(request: Request) -> None:
    """Refuse duplicated query parameters, which two parsers read differently."""
    if len(request.query_params) != len(request.query_params.multi_items()):
        raise ValidationFailedError("duplicate query parameters")


def cursor_secret(request: Request) -> bytes:
    return bytes(request.app.state.settings.cursor_signing_secret.get_secret_value().encode())
