"""Shared helpers for the local-provider suites: settings, PKCE constants and a flow driver.

Every secret here is a throwaway constant for an in-process app (CLAUDE.md §5.9).
"""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from identity.config import LocalAuthSettings, LocalClient

CLIENT_ID = "billing-web"
CLIENT_SECRET = "web-client-secret-for-tests-only"
OTHER_CLIENT_ID = "billing-mobile"
OTHER_CLIENT_SECRET = "mobile-client-secret-for-tests-only"
REDIRECT = "http://localhost:4310/api/auth/callback/local"
OTHER_REDIRECT = "janso://callback"
BFF_SECRET = "bff-secret-for-tests-only-0123456789abcdef"
ISSUER = "http://localhost:8090/identity/oidc"
AUDIENCE = "billing-api"
UI = "http://localhost:4310"
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"  # RFC 7636 appendix B
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
SCOPE = "openid profile email offline_access billing.api"
BFF = {"X-Auth-Bff-Secret": BFF_SECRET}
PASSWORD = "correct horse battery"


def local_settings(**overrides: Any) -> LocalAuthSettings:
    values: dict[str, Any] = {
        "issuer": ISSUER,
        "jwks_url": "http://localhost/oidc/jwks",
        "audience": AUDIENCE,
        "auth_ui_url": UI,
        "clients": (
            LocalClient(
                client_id=CLIENT_ID,
                secret_sha256=hashlib.sha256(CLIENT_SECRET.encode()).hexdigest(),
                redirect_uris=(REDIRECT,),
            ),
            LocalClient(
                client_id=OTHER_CLIENT_ID,
                secret_sha256=hashlib.sha256(OTHER_CLIENT_SECRET.encode()).hexdigest(),
                redirect_uris=("http://localhost:4311/callback",),
            ),
        ),
        "bff_secret": BFF_SECRET,
        "key_encryption_key": base64.b64encode(b"k" * 32).decode(),
        "max_failed_attempts": 3,
    }
    return LocalAuthSettings(**(values | overrides))


def authorize_params(**overrides: str | None) -> dict[str, str]:
    values: dict[str, str | None] = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT,
        "scope": SCOPE,
        "state": "state-123",
        "nonce": "nonce-456",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
    }
    values.update(overrides)
    return {key: value for key, value in values.items() if value is not None}


def request_id_from(location: str) -> str:
    assert location.startswith(UI + "/signin?request="), location
    return str(parse_qs(urlsplit(location).query)["request"][0])


async def begin(client: httpx.AsyncClient, **overrides: str | None) -> str:
    """Start an authorization request and return the request id the sign-in page would carry."""
    response = await client.get("/oidc/authorize", params=authorize_params(**overrides))
    assert response.status_code == 302, response.text
    return request_id_from(response.headers["location"])


async def sign_in(
    client: httpx.AsyncClient, email: str, password: str = PASSWORD, **overrides: str | None
) -> str:
    """Complete the sign-in step and return the authorization code."""
    request_id = await begin(client, **overrides)
    response = await client.post(
        "/internal/v1/local-auth/login",
        json={"request_id": request_id, "email": email, "password": password},
        headers=BFF,
    )
    assert response.status_code == 200, response.text
    query = parse_qs(urlsplit(response.json()["redirect_to"]).query)
    assert query["state"] == [overrides.get("state", "state-123")]
    return str(query["code"][0])


async def redeem(client: httpx.AsyncClient, code: str, **overrides: str | None) -> httpx.Response:
    form: dict[str, str | None] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "code_verifier": VERIFIER,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    form.update(overrides)
    return await client.post(
        "/oidc/token", data={key: value for key, value in form.items() if value is not None}
    )


async def tokens(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> dict[str, Any]:
    response = await redeem(client, await sign_in(client, email, password))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def refresh(client: httpx.AsyncClient, token: str, **overrides: str | None) -> httpx.Response:
    form: dict[str, str | None] = {
        "grant_type": "refresh_token",
        "refresh_token": token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    form.update(overrides)
    return await client.post(
        "/oidc/token", data={key: value for key, value in form.items() if value is not None}
    )


def decode_unverified(token: str) -> dict[str, Any]:
    """The claims of a JWT, for assertions about what was put in it (not for trusting it)."""
    payload = token.split(".")[1]
    import json

    result: dict[str, Any] = json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    )
    return result


def header_of(token: str) -> dict[str, Any]:
    import json

    head = token.split(".")[0]
    result: dict[str, Any] = json.loads(base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)))
    return result


def no_secrets_in(text: str, *secrets: str) -> bool:
    return not any(secret and re.search(re.escape(secret), text) for secret in secrets)


# --- a light schema -------------------------------------------------------------------------
#
# Creating all ~110 identity tables costs seconds per test. The local provider touches a handful,
# so its suites build only those. Foreign keys stay enforced; a parent table that is not created is
# never the target of a non-NULL child value in these tests. A suite that seeds tenants and users
# turns enforcement off (their parents — countries, currencies — are not what is under test).

LIGHT_TABLES = (
    "local_identity",
    "local_credential",
    "local_recovery_token",
    "local_signing_key",
    "local_authorization",
    "local_refresh_token",
    "tenant",
    "user",
    "role",
    "role_assignment",
    "role_permission",
    "user_group",
    "user_group_member",
    "membership",
    "company",
    "company_business_role",
    "user_api_token",
    "outbox",
    "account_review",
    "account_review_command",
    "platform_installation",
)


async def light_engine(*, enforce_foreign_keys: bool = True) -> Any:
    from billing_platform.db.base import Base
    from billing_platform.db.session import create_engine
    from billing_platform.testing import SQLITE_URL
    from sqlalchemy import event

    from identity import models  # noqa: F401  (registers every model)

    eng = create_engine(SQLITE_URL)

    if enforce_foreign_keys:

        @event.listens_for(eng.sync_engine, "connect")
        def _foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    tables = [Base.metadata.tables[name] for name in LIGHT_TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    return eng
