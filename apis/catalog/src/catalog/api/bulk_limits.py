"""Bound the wire body while streaming, before FastAPI allocates/parses JSON."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.routing import APIRoute
from starlette.types import Message

MAX_BODY_BYTES = 13 * 1024 * 1024


class BoundedBulkRoute(APIRoute):
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
                        status_code=413, detail="bulk request exceeds its byte bound"
                    )
                return message

            return await handler(Request(request.scope, receive=receive))

        return bounded
