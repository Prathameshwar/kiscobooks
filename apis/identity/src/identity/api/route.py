"""Strict public query contracts, including duplicate scalar query rejection."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from billing_platform.errors import ErrorEnvelope
from billing_platform.http_query import validate_query_names
from fastapi import Request, Response
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422)
}


def query_names(dependant: Dependant) -> set[str]:
    names = {field.alias for field in dependant.query_params}
    for child in dependant.dependencies:
        names.update(query_names(child))
    return names


class StrictRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        allowed = query_names(self.dependant)

        async def strict(request: Request) -> Response:
            validate_query_names((key for key, _ in request.query_params.multi_items()), allowed)
            return await handler(request)

        return strict
