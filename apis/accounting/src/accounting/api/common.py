"""Shared route adapters; authorization and transactions remain explicit."""

from collections.abc import AsyncIterator
from typing import Annotated, Any

from billing_platform.db import tenant_scope
from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from billing_platform.idempotency import CommandResult
from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.tasks.commands import require_metadata

Idempotency = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]


async def session(
    request: Request, current: Access = Depends(access)
) -> AsyncIterator[AsyncSession]:
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await require_metadata(db, current)
            yield db


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 503)
}


def response(request: Request, result: CommandResult[BaseModel]) -> JSONResponse:
    content = result.value.model_dump(mode="json", exclude_unset=True)
    headers = {"Idempotency-Replayed": str(result.replayed).lower()}
    if result.status == 201:
        # Relative locations preserve an external gateway prefix as well as direct API URLs.
        collection = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        headers["Location"] = f"{collection}/{content['id']}"
    return JSONResponse(status_code=result.status, content=content, headers=headers)


def no_query(request: Request) -> None:
    if request.query_params:
        raise ValidationFailedError("this operation does not accept query parameters")


def unique_query(request: Request) -> None:
    if len(request.query_params.multi_items()) != len(request.query_params):
        raise ValidationFailedError("duplicate query parameter")
