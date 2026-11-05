"""Plumbing shared by the local provider's HTTP routes: transactions, throttling, form bodies."""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Awaitable, Callable
from typing import TypeVar
from urllib.parse import parse_qsl, unquote_plus

from billing_platform.errors import PlatformError
from billing_platform.rate_limit import WindowLimiter
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from identity.local_auth.errors import (
    AuthorizeError,
    LocalAuthUnavailableError,
    OAuthError,
    TooManyAttemptsError,
)
from identity.local_auth.service import LocalAuth

T = TypeVar("T")

#: A form body this large is not a token request.
MAX_FORM_BYTES = 16_384
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def local_auth(request: Request) -> LocalAuth:
    service: LocalAuth | None = getattr(request.app.state, "local_auth", None)
    if service is None:
        raise LocalAuthUnavailableError("Local sign-in is not configured.")
    return service


async def transact(request: Request, work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run ``work`` in one transaction.

    An *expected* refusal — a wrong password, a reused code — commits, because the failure count
    or the revocation it recorded must survive the error. Anything else rolls back.
    """
    async with request.app.state.session_factory() as db:
        try:
            result = await work(db)
        except (PlatformError, OAuthError, AuthorizeError):
            await db.commit()
            raise
        except BaseException:
            await db.rollback()
            raise
        await db.commit()
        return result


#: How many slots one throttle bucket is spread over. The keys are text a caller chooses (an email,
#: an address, a request id), and a table that remembers every distinct key can be filled by
#: inventing keys — after which it refuses everyone, which is a lockout of the whole installation.
#: Hashing each key into one of a fixed number of slots bounds the table (``SLOTS`` x the number of
#: buckets, well under the limiter's capacity), at the price of an occasional shared budget: two
#: unrelated keys in one slot split its limit, and the busiest single account still gets its own.
SLOTS = 4096


def throttle(request: Request, bucket: str, key: str, limit: int) -> None:
    """Per-process window limit; nginx's ``limit_req`` is the shared one in front of it."""
    limiter: WindowLimiter = request.app.state.local_limiter
    digest = hashlib.sha256(f"{bucket}:{key}".encode()).digest()
    slot = f"{bucket}:{int.from_bytes(digest[:4], 'big') % SLOTS}"
    if not limiter.allow(slot, limit=limit):
        raise TooManyAttemptsError("Too many attempts. Wait a minute and try again.")


def client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def form_params(request: Request) -> dict[str, str]:
    """A urlencoded body as single-valued parameters (RFC 6749 §3.2: no repeats)."""
    if (
        not request.headers.get("content-type", "")
        .lower()
        .startswith("application/x-www-form-urlencoded")
    ):
        raise OAuthError(
            "invalid_request", "Send the request as application/x-www-form-urlencoded."
        )
    if int(request.headers.get("content-length", "0") or 0) > MAX_FORM_BYTES:
        raise OAuthError("invalid_request", "The request body is too large.")
    # Content-Length is advisory (a chunked body has none), so the stream itself is bounded: reading
    # it whole first would let one request buffer whatever the proxy allows.
    received = bytearray()
    async for chunk in request.stream():
        received += chunk
        if len(received) > MAX_FORM_BYTES:
            raise OAuthError("invalid_request", "The request body is too large.")
    raw = bytes(received)
    try:
        pairs = parse_qsl(raw.decode("utf-8"), keep_blank_values=True, max_num_fields=32)
    except (UnicodeDecodeError, ValueError):
        raise OAuthError("invalid_request", "The request body is not valid.") from None
    names = [name for name, _ in pairs]
    if len(set(names)) != len(names):
        raise OAuthError("invalid_request", "A parameter was repeated.")
    return dict(pairs)


def basic_credentials(request: Request) -> tuple[str, str] | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        raise OAuthError("invalid_client", "Client authentication failed.", 401) from None
    client_id, separator, secret = decoded.partition(":")
    if not separator:
        raise OAuthError("invalid_client", "Client authentication failed.", 401)
    return unquote_plus(client_id), unquote_plus(secret)


def oauth_error(exc: OAuthError) -> JSONResponse:
    headers = dict(NO_STORE)
    if exc.status == 401:
        headers["WWW-Authenticate"] = 'Basic realm="oidc"'
    return JSONResponse(
        {"error": exc.error, "error_description": exc.description},
        status_code=exc.status,
        headers=headers,
    )
