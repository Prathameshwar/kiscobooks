"""Opaque request correlation and query-free access logs for API applications."""

import logging
import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from billing_platform.audit_context import audit_request


class SafeAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn's access arguments include the full query string. Never keep it.
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, target, version, status = record.args
            if isinstance(target, str):
                record.args = (client, method, target.partition("?")[0], version, status)
        return True


class RequestCorrelation:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        access = logging.getLogger("uvicorn.access")
        if not any(isinstance(item, SafeAccessLogFilter) for item in access.filters):
            access.addFilter(SafeAccessLogFilter())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        trace = headers.get(b"x-trace-id", b"").decode("ascii", errors="ignore")
        if not re.fullmatch(r"[0-9a-fA-F]{32}", trace):
            trace = uuid.uuid4().hex
        request = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        try:
            request = str(uuid.UUID(request))
        except ValueError:
            request = str(uuid.uuid4())
        # Adapters and failure boundaries see the same validated identifiers.
        scope["headers"] = [
            (key, value)
            for key, value in scope.get("headers", [])
            if key.lower() not in {b"x-trace-id", b"x-request-id"}
        ] + [(b"x-trace-id", trace.encode()), (b"x-request-id", request.encode())]

        async def correlated_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in {b"x-trace-id", b"x-request-id"}
                ] + [(b"x-trace-id", trace.encode()), (b"x-request-id", request.encode())]
            await send(message)

        with audit_request(trace, request):
            await self.app(scope, receive, correlated_send)
