"""Bounded reference commands, including nested duplicate JSON member rejection."""

import json
from collections.abc import Callable, Coroutine
from typing import Any

from billing_platform.errors import ValidationFailedError
from fastapi import Request, Response

from identity.api.route import StrictRoute


def unique_members(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


class ReferenceRoute(StrictRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            if request.method in {"POST", "PATCH"}:
                if (
                    request.headers.get("content-type", "").split(";")[0].strip()
                    != "application/json"
                ):
                    raise ValidationFailedError("a JSON command is required")
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 16_384:
                        raise ValidationFailedError("reference command exceeds the size limit")
                try:
                    json.loads(body, object_pairs_hook=unique_members)
                except (ValueError, UnicodeDecodeError, RecursionError):
                    raise ValidationFailedError("invalid JSON or duplicate fields") from None
                request._body = bytes(body)
            return await handler(request)

        return bounded
