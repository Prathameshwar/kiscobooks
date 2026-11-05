"""Reusable company transaction and bounded response helpers."""

from collections.abc import AsyncIterator
from typing import Annotated, Any

from billing_platform.db import tenant_scope
from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access

Idempotency = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)
}


async def session(
    request: Request, current: Access = Depends(access)
) -> AsyncIterator[AsyncSession]:
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            yield db


def unique_query(request: Request) -> None:
    if len(request.query_params) != len(request.query_params.multi_items()):
        raise ValidationFailedError("duplicate query parameters")


def response(result: Any) -> JSONResponse:
    from fastapi.encoders import jsonable_encoder

    return JSONResponse(
        jsonable_encoder(result.value),
        status_code=result.status,
        headers={"Idempotency-Replayed": str(result.replayed).lower(), "Cache-Control": "no-store"},
    )
