"""Streaming input bounds and strict query handling for optional import routes."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Header, HTTPException, Request, Response
from fastapi.routing import APIRoute
from starlette.types import Message

from billing_platform.errors import ValidationFailedError

MAX_BODY_BYTES = 13 * 1024 * 1024


class BoundedImportRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            byte_count = 0

            async def receive() -> Message:
                nonlocal byte_count
                message = await request.receive()
                byte_count += len(message.get("body", b""))
                if byte_count > MAX_BODY_BYTES:
                    raise HTTPException(
                        status_code=413, detail="import request exceeds its byte bound"
                    )
                return message

            return await handler(Request(request.scope, receive=receive))

        return bounded


async def strict_query(request: Request) -> None:
    route = request.scope["route"]
    allowed = {field.alias for field in route.dependant.query_params}
    keys = [key for key, _ in request.query_params.multi_items()]
    if len(keys) != len(set(keys)) or not set(keys) <= allowed:
        raise ValidationFailedError("unknown or repeated import query parameter")


async def required_key(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> None:
    """Declare write idempotency in generated contracts as well as enforcing it."""
