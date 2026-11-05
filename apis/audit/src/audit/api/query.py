"""Reject ambiguous and unsupported Audit filters before route execution."""

from billing_platform.errors import ValidationFailedError
from fastapi import Request
from fastapi.routing import APIRoute


def validate_query(request: Request) -> None:
    route = request.scope.get("route")
    assert isinstance(route, APIRoute)
    allowed = {field.alias for field in route.dependant.query_params}
    seen: set[str] = set()
    for key, _value in request.query_params.multi_items():
        if key not in allowed or key in seen:
            raise ValidationFailedError("unknown or repeated audit query parameter")
        seen.add(key)
