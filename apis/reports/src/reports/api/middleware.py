"""Bound the HTTP body before JSON parsing; headers cannot bypass chunked limits."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        original_send = send

        async def private_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in headers}
                for name, value in (
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ):
                    if name not in existing:
                        headers.append((name, value))
                message = dict(message) | {"headers": headers}
            await original_send(message)

        send = private_send
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD"}:
            await self.app(scope, receive, send)
            return
        maximum = 1048576 if scope["path"].startswith("/internal/") else 262144
        pieces = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > maximum:
                await JSONResponse(
                    {
                        "error": {
                            "code": "payload_too_large",
                            "message": "request exceeds the supported body size",
                        }
                    },
                    status_code=413,
                )(scope, receive, send)
                return
            pieces.append(chunk)
            if not message.get("more_body", False):
                break
        sent = False

        async def bounded_receive() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"".join(pieces), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
