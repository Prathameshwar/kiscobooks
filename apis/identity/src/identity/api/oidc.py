"""The local provider's OpenID Connect endpoints (docs/local-auth.md §3).

Public by design: a browser is sent to ``/authorize``, and the Auth app's server and the token
verifier call the rest. Nothing here authenticates a *person*; the person proves themselves at the
sign-in page, and every other call proves the *client* (a secret) or carries a one-use code/token.
Not part of the OpenAPI client: these are protocol endpoints, not product routes.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from identity.local_auth.errors import AuthorizeError, OAuthError, TooManyAttemptsError
from identity.local_auth.http import (
    NO_STORE,
    basic_credentials,
    client_address,
    form_params,
    local_auth,
    oauth_error,
    throttle,
    transact,
)

router = APIRouter(prefix="/oidc", include_in_schema=False)


def _single(request: Request) -> dict[str, str] | None:
    pairs = request.query_params.multi_items()
    names = [name for name, _ in pairs]
    return dict(pairs) if len(set(names)) == len(names) and len(pairs) <= 32 else None


@router.get("/.well-known/openid-configuration")
async def discovery(request: Request) -> JSONResponse:
    document = local_auth(request).discovery()
    return JSONResponse(document, headers={"Cache-Control": "public, max-age=300"})


@router.get("/jwks")
async def jwks(request: Request) -> JSONResponse:
    service = local_auth(request)
    document = await transact(request, service.keys.public_set)
    return JSONResponse(document, headers={"Cache-Control": "public, max-age=60"})


@router.get("/authorize")
async def authorize(request: Request) -> Response:
    service = local_auth(request)
    try:
        throttle(request, "authorize", client_address(request), 120)
    except TooManyAttemptsError:
        return JSONResponse(
            {"error": "temporarily_unavailable", "error_description": "Too many requests."},
            status_code=429,
            headers={**NO_STORE, "Retry-After": "60"},
        )
    query = _single(request)
    try:
        if query is None:
            raise AuthorizeError(
                "invalid_request", "A parameter was repeated or there were too many."
            )
        location = await transact(request, lambda db: service.authorize(db, query))
    except AuthorizeError as exc:
        if exc.redirect_uri is None:
            return JSONResponse(
                {"error": exc.error, "error_description": exc.description},
                status_code=400,
                headers=NO_STORE,
            )
        fields = {"error": exc.error, "error_description": exc.description}
        if exc.state:
            fields["state"] = exc.state
        return RedirectResponse(
            f"{exc.redirect_uri}?{urlencode(fields)}", status_code=302, headers=NO_STORE
        )
    return RedirectResponse(location, status_code=302, headers=NO_STORE)


@router.post("/token")
async def token(request: Request) -> JSONResponse:
    service = local_auth(request)
    try:
        params = await form_params(request)
        basic = basic_credentials(request)
        body = await transact(request, lambda db: service.token(db, params, basic=basic))
    except OAuthError as exc:
        return oauth_error(exc)
    except TooManyAttemptsError:
        return oauth_error(OAuthError("temporarily_unavailable", "Too many requests.", 429))
    return JSONResponse(body, headers=NO_STORE)


@router.post("/revoke")
async def revoke(request: Request) -> Response:
    service = local_auth(request)
    try:
        params = await form_params(request)
        basic = basic_credentials(request)
        client_id = basic[0] if basic else params.get("client_id")
        secret = basic[1] if basic else params.get("client_secret")
        await transact(
            request, lambda db: service.revoke(db, client_id, secret, params.get("token"))
        )
    except OAuthError as exc:
        return oauth_error(exc)
    except TooManyAttemptsError:
        return oauth_error(OAuthError("temporarily_unavailable", "Too many requests.", 429))
    return Response(status_code=200, headers=NO_STORE)
