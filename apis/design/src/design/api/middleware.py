"""Bound request bodies before JSON parsing; a header cannot bypass a chunked limit.

The ceilings come from configuration rather than from constants here, so an operator can
lower them without a deploy — and so there is one place that decides, instead of a
setting that is read nowhere. A canvas save gets the wide ceiling because a layout tree
is the largest legitimate *structural* body this service accepts. An asset upload gets
its own, wider still (plan P4, 2026-11-03): base64 inflates bytes by a third, so a 5 MiB
image — already this service's own ceiling on what an asset may be — needs close to
7 MiB of request body to arrive at all, independent of how large a layout tree may be.

Security headers are added on the way out for every response, including error envelopes:
``no-store`` so a layout or a print record is not cached by an intermediary, and
``nosniff`` so a JSON body is never re-interpreted as markup.
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Used only when the app was built without settings on state (never in production).
DEFAULT_MAX_BYTES = 1_048_576
CANVAS_MAX_BYTES = 5_242_880
ASSET_MAX_BYTES = 7_340_032

_WIDE_PATHS = ("/versions", "/templates")
_ASSET_PATHS = ("/assets",)


class BodyLimit:
    """Enforce body size limits and security headers on all responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def _ceiling(self, scope: Scope, path: str) -> int:
        settings = getattr(scope.get("app"), "state", None)
        settings = getattr(settings, "settings", None)
        if settings is None:
            if path.endswith(_ASSET_PATHS):
                return ASSET_MAX_BYTES
            return CANVAS_MAX_BYTES if path.endswith(_WIDE_PATHS) else DEFAULT_MAX_BYTES
        if path.endswith(_ASSET_PATHS):
            asset: int = settings.max_asset_body_bytes
            return asset
        wide: int = settings.max_canvas_body_bytes
        narrow: int = settings.max_body_bytes
        return wide if path.endswith(_WIDE_PATHS) else narrow

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        original_send = send

        async def private_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in headers}
                for name, value in (
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                ):
                    if name not in existing:
                        headers.append((name, value))
                message = dict(message) | {"headers": headers}
            await original_send(message)

        send = private_send
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD"}:
            await self.app(scope, receive, send)
            return

        maximum = self._ceiling(scope, scope.get("path", ""))

        pieces: list[bytes] = []
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
                    headers={"cache-control": "no-store"},
                )(scope, receive, send)
                return
            pieces.append(chunk)
            if not message.get("more_body", False):
                break

        full_body = b"".join(pieces)
        delivered = False

        async def buffered_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": full_body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, buffered_receive, send)
