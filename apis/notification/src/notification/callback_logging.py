"""Preserve signed query inputs during verification, redact them before access logging."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class CallbackQueryRedaction:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/v1/callbacks/"):
            await self.app(scope, receive, send)
            return

        async def redacted_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                scope["query_string"] = b""
            await send(message)

        try:
            await self.app(scope, receive, redacted_send)
        finally:
            # Also protect the outer server-error path if verification raises.
            scope["query_string"] = b""
