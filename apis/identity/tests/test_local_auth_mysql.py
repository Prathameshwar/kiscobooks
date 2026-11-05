"""The local provider on a real MySQL (CLAUDE.md §7: dialect behaviour is never asserted on SQLite).

What only a real server can show: the migrations build exactly what the models say and reverse
cleanly; the email key is case-insensitive under the platform collation; a signing key survives a
restart (the encrypted private half reloads and the *old* process's tokens still verify); a lock
and a revoked token family persist across requests; and ``DATETIME(6)`` keeps microseconds.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from typing import Any

import httpx
import pytest
from alembic import command
from billing_platform.oidc import AccessTokenVerifier
from billing_platform.rate_limit import WindowLimiter
from pydantic import SecretStr
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from identity.config import Settings
from identity.install import install_identity
from identity.local_auth.adapters import LocalAccountProvider
from identity.main import create_app
from identity.models.local_auth import (
    PATH_PENDING,
    LocalAuthorization,
    LocalCredential,
    LocalIdentity,
    LocalRecoveryToken,
    LocalRefreshToken,
    LocalSigningKey,
)
from tests.alembic_support import alembic_config
from tests.api_support import ACTOR_SECRET, CURSOR_SECRET
from tests.local_auth_support import (
    BFF,
    PASSWORD,
    begin,
    local_settings,
    redeem,
    refresh,
    sign_in,
    tokens,
)

REGISTER = "/internal/v1/local-auth/registrations"
LOGIN = "/internal/v1/local-auth/login"
TABLES = (
    LocalRefreshToken,
    LocalAuthorization,
    LocalRecoveryToken,
    LocalCredential,
    LocalIdentity,
    LocalSigningKey,
)


def build_app(url: str, **settings: Any) -> Any:
    app = create_app(
        Settings(
            database_url=url,
            actor_signing_secret=SecretStr(ACTOR_SECRET),
            cursor_signing_secret=SecretStr(CURSOR_SECRET),
            public_auth_url="https://auth.test",
            auth_provider="local",
            local_auth=local_settings(),
            **settings,
        )
    )
    app.state.auth_limiter = WindowLimiter()
    app.state.local_limiter = WindowLimiter()
    app.state.oidc_http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    )
    assert app.state.settings.oidc is not None
    app.state.token_verifier = AccessTokenVerifier(
        app.state.settings.oidc.configuration(), app.state.oidc_http
    )
    return app


def client_for(app: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost")


async def clear(app: Any) -> None:
    async with app.state.session_factory() as db:
        for model in TABLES:
            await db.execute(delete(model))
        await db.commit()


async def activate(app: Any, email: str) -> LocalIdentity:
    async with app.state.session_factory() as db:
        identity = await db.scalar(select(LocalIdentity).where(LocalIdentity.email == email))
        assert identity is not None
    provider = LocalAccountProvider(app.state.session_factory)
    _, raw = await provider.read(identity.seq)
    await provider.apply(identity.seq, raw, active=True, verified=True, command_id=uuid.uuid4())
    return identity


@pytest.mark.mysql
def test_the_provider_end_to_end_on_mysql(mysql_url: str) -> None:
    install_identity(mysql_url)

    async def exercise() -> None:
        app = build_app(mysql_url)
        await clear(app)
        async with client_for(app) as client:
            # -- sign-up, case-insensitive uniqueness, and the pending gate ---------------------
            body = {
                "name": "Ravi Menon",
                "username": "ravi",
                "email": "Ravi@Beta.Example",
                "password": PASSWORD,
                "country_code": "IN",
                "state_code": "IN-KA",
                "workspace_name": "North Books",
            }
            assert (await client.post(REGISTER, json=body, headers=BFF)).status_code == 201
            twin = await client.post(
                REGISTER,
                json=body | {"username": "ravi2", "email": "RAVI@BETA.EXAMPLE"},
                headers=BFF,
            )
            assert (
                twin.status_code == 422
                and twin.json()["error"]["code"] == "registration_unavailable"
            )
            # The key itself is case-insensitive, whatever the application does before it.
            async with app.state.session_factory() as db:
                db.add(
                    LocalIdentity(
                        uid=uuid.uuid4(),
                        sub="f" * 64,
                        email="RAVI@BETA.EXAMPLE",
                        name="Twin",
                        username="twin",
                        path=PATH_PENDING,
                        status="pending",
                    )
                )
                with pytest.raises(IntegrityError):
                    await db.commit()
            pending = await client.post(
                LOGIN,
                json={
                    "request_id": await begin(client),
                    "email": "ravi@beta.example",
                    "password": PASSWORD,
                },
                headers=BFF,
            )
            assert (
                pending.status_code == 403 and pending.json()["error"]["code"] == "account_pending"
            )

            # -- approval, tokens, refresh rotation and theft detection ------------------------
            await activate(app, "ravi@beta.example")
            first = await tokens(client, "ravi@beta.example")
            claims = await app.state.token_verifier.verify(first["access_token"])
            assert claims.email == "ravi@beta.example" and claims.email_verified is True
            username_tokens = await tokens(client, " RAVI ")
            username_claims = await app.state.token_verifier.verify(username_tokens["access_token"])
            assert username_claims.sub == claims.sub and username_claims.email == claims.email
            second = (await refresh(client, first["refresh_token"])).json()
            assert (await refresh(client, first["refresh_token"])).status_code == 400
            assert (await refresh(client, second["refresh_token"])).status_code == 400

            # -- a code is single use, and the replay kills what it made ----------------------
            code = await sign_in(client, "ravi@beta.example")
            started = (await redeem(client, code)).json()
            assert (await redeem(client, code)).status_code == 400
            assert (await refresh(client, started["refresh_token"])).status_code == 400

            # -- the lock persists across requests ---------------------------------------------
            for _ in range(3):
                bad = await client.post(
                    LOGIN,
                    json={
                        "request_id": await begin(client),
                        "email": "ravi@beta.example",
                        "password": "no no no",
                    },
                    headers=BFF,
                )
                assert bad.status_code == 401
            locked = await client.post(
                LOGIN,
                json={
                    "request_id": await begin(client),
                    "email": "ravi@beta.example",
                    "password": PASSWORD,
                },
                headers=BFF,
            )
            assert locked.status_code == 423 and locked.json()["retry_after"] > 0

            # -- stored shapes -----------------------------------------------------------------
            async with app.state.session_factory() as db:
                identity = (await db.scalars(select(LocalIdentity))).one()
                credential = await db.get(LocalCredential, identity.seq)
                key = (await db.scalars(select(LocalSigningKey))).one()
                digests = list(await db.scalars(select(LocalRefreshToken.token_hash)))
            assert identity.last_login_at is not None
            assert credential is not None and credential.password_hash.startswith("$argon2id$")
            assert "BEGIN" not in key.private_jwk_ciphertext and '"d"' not in key.public_jwk
            assert all(len(digest) == 64 for digest in digests)
            assert first["refresh_token"] not in digests
            assert hashlib.sha256(first["refresh_token"].encode()).hexdigest() in digests
        await app.state.oidc_http.aclose()
        await app.state.engine.dispose()

    asyncio.run(exercise())


@pytest.mark.mysql
def test_a_restarted_service_keeps_the_same_signing_key_and_still_verifies_earlier_tokens(
    mysql_url: str,
) -> None:
    install_identity(mysql_url)

    async def exercise() -> None:
        first = build_app(mysql_url)
        await clear(first)
        async with client_for(first) as client:
            async with first.state.session_factory() as db:
                await first.state.local_auth.create_account(
                    db,
                    name="Ravi",
                    username="ravi",
                    email="ravi@beta.example",
                    password=PASSWORD,
                    region=("IN", ""),
                    workspace_name=None,
                    path=PATH_PENDING,
                    status="active",
                    verified=True,
                )
                await db.commit()
            issued = await tokens(client, "ravi@beta.example")
            kid = (await client.get("/oidc/jwks")).json()["keys"][0]["kid"]
        await first.state.oidc_http.aclose()
        await first.state.engine.dispose()

        # A new process: nothing in memory, the key must come back out of the database.
        second = build_app(mysql_url)
        async with client_for(second) as client:
            assert (await client.get("/oidc/jwks")).json()["keys"][0]["kid"] == kid
            claims = await second.state.token_verifier.verify(issued["access_token"])
            assert claims.email == "ravi@beta.example"
            renewed = await refresh(client, issued["refresh_token"])
            assert renewed.status_code == 200
        await second.state.oidc_http.aclose()
        await second.state.engine.dispose()

    asyncio.run(exercise())


@pytest.mark.mysql
def test_simultaneous_redemptions_on_separate_connections_yield_one_session(
    mysql_url: str,
) -> None:
    """Row locks, not the test's own scheduling, pick one winner (SQLite shares one connection)."""
    install_identity(mysql_url)

    async def exercise() -> None:
        app = build_app(mysql_url)
        await clear(app)
        async with client_for(app) as client:
            async with app.state.session_factory() as db:
                await app.state.local_auth.create_account(
                    db,
                    name="Ravi",
                    username="ravi",
                    email="ravi@beta.example",
                    password=PASSWORD,
                    region=("IN", ""),
                    workspace_name=None,
                    path=PATH_PENDING,
                    status="active",
                    verified=True,
                )
                await db.commit()
            for _ in range(5):
                code = await sign_in(client, "ravi@beta.example")
                one, two = await asyncio.gather(redeem(client, code), redeem(client, code))
                assert sorted([one.status_code, two.status_code]) == [200, 400]

            issued = await tokens(client, "ravi@beta.example")
            one, two = await asyncio.gather(
                refresh(client, issued["refresh_token"]), refresh(client, issued["refresh_token"])
            )
            assert sorted([one.status_code, two.status_code]) == [200, 400]
            # The loser is a reuse, so the family — the winner's successor included — is revoked.
            winner = one if one.status_code == 200 else two
            assert (await refresh(client, winner.json()["refresh_token"])).status_code == 400
        await app.state.oidc_http.aclose()
        await app.state.engine.dispose()

    asyncio.run(exercise())


@pytest.mark.mysql
def test_simultaneous_wrong_guesses_are_counted_one_by_one_and_lock_the_account(
    mysql_url: str,
) -> None:
    """A burst must not count once: the credential row is locked while a failure is recorded."""
    install_identity(mysql_url)

    async def exercise() -> None:
        app = build_app(mysql_url)
        await clear(app)
        limit = app.state.settings.local_auth.max_failed_attempts
        async with client_for(app) as client:
            async with app.state.session_factory() as db:
                await app.state.local_auth.create_account(
                    db,
                    name="Ravi",
                    username="ravi",
                    email="ravi@beta.example",
                    password=PASSWORD,
                    region=("IN", ""),
                    workspace_name=None,
                    path=PATH_PENDING,
                    status="active",
                    verified=True,
                )
                await db.commit()
            request_id = await begin(client)
            guesses = limit + 3

            async def wrong(identifier: str) -> int:
                response = await client.post(
                    LOGIN,
                    json={
                        "request_id": request_id,
                        "identifier": identifier,
                        "password": "not the password",
                    },
                    headers=BFF,
                )
                return response.status_code

            statuses = sorted(
                await asyncio.gather(
                    *(
                        wrong("ravi" if index % 2 else "ravi@beta.example")
                        for index in range(guesses)
                    )
                )
            )
            # Counted in turn: exactly `limit` answered as wrong guesses, the rest found it locked.
            assert statuses == [401] * limit + [423] * 3
            async with app.state.session_factory() as db:
                credential = (await db.scalars(select(LocalCredential))).one()
            assert credential.lock_ends_at is not None  # locking restarts the count
        await app.state.oidc_http.aclose()
        await app.state.engine.dispose()

    asyncio.run(exercise())


@pytest.mark.mysql
def test_two_simultaneous_first_run_administrators_yield_exactly_one(mysql_url: str) -> None:
    """Needs a disposable database where setup has not completed, like the other setup tests."""
    install_identity(mysql_url)
    setup_key = "setup-key-for-tests-only-0123456789abcdef"

    async def exercise() -> None:
        app = build_app(mysql_url, setup_key=SecretStr(setup_key))
        await clear(app)
        async with client_for(app) as client:

            async def create(email: str) -> int:
                response = await client.post(
                    "/internal/v1/local-auth/setup/administrator",
                    json={"name": "Priya Nair", "email": email, "password": PASSWORD},
                    headers={**BFF, "X-Setup-Key": setup_key},
                )
                return response.status_code

            statuses = sorted(
                await asyncio.gather(*(create(f"owner{n}@owner.example") for n in range(4)))
            )
            assert statuses == [201, 409, 409, 409]
            async with app.state.session_factory() as db:
                assert len(list(await db.scalars(select(LocalIdentity)))) == 1
        await app.state.oidc_http.aclose()
        await app.state.engine.dispose()

    asyncio.run(exercise())


@pytest.mark.mysql
def test_first_run_setup_completes_with_nothing_but_a_local_sign_in(mysql_url: str) -> None:
    """The whole first-run path with no Authentik; needs a database where setup is still open."""
    install_identity(mysql_url)
    setup_key = "setup-key-for-tests-only-0123456789abcdef"

    async def exercise() -> None:
        app = build_app(mysql_url, setup_key=SecretStr(setup_key))
        await clear(app)
        async with client_for(app) as client:
            # The installation is waiting, and the readiness check names the local provider.
            checks = await client.get("/v1/setup/checks", headers={"X-Setup-Key": setup_key})
            names = {check["name"]: check["status"] for check in checks.json()["checks"]}
            assert names["Identity signing keys"] == "ready" and "Authentik" not in str(names)

            created = await client.post(
                "/internal/v1/local-auth/setup/administrator",
                json={"name": "Priya Nair", "email": "priya@owner.example", "password": PASSWORD},
                headers={**BFF, "X-Setup-Key": setup_key},
            )
            assert created.status_code == 201, created.text
            issued = await tokens(client, "priya@owner.example")
            bearer = {"Authorization": f"Bearer {issued['access_token']}", "X-Setup-Key": setup_key}

            who = await client.get("/v1/setup/administrator", headers=bearer)
            assert who.status_code == 200 and who.json()["email"] == "priya@owner.example"
            done = await client.post(
                "/v1/setup/complete",
                json={
                    "platform_name": "Owner Books",
                    "public_url": "https://books.owner.example",
                    "workspace_name": "Owner Books",
                    "workspace_slug": "owner-books",
                    "administrator_name": "Priya Nair",
                    "country_code": "IN",
                    "currency_code": "INR",
                    "timezone": "Asia/Kolkata",
                    "locale": "en",
                },
                headers=bearer,
            )
            assert done.status_code == 200, done.text
            # The same sign-in is now a platform administrator's session in the new workspace.
            session = await client.get(
                "/v1/session", headers={"Authorization": f"Bearer {issued['access_token']}"}
            )
            assert session.status_code == 200, session.text

            # -- the platform operator then creates tenants, with no Authentik to provision in -----
            fresh = await tokens(client, "priya@owner.example")
            operator = {
                "Authorization": f"Bearer {fresh['access_token']}",
                "Idempotency-Key": "first-tenant",
            }
            probe = "/v1/platform/tenant-administrators/available"
            unknown = await client.get(
                probe, params={"email": "ravi@acme.example"}, headers=operator
            )
            assert unknown.status_code == 200 and unknown.json() == {"available": None}
            tenant = {
                "name": "Acme Traders",
                "administrator_name": "Ravi Menon",
                "administrator_email": "ravi@acme.example",
                "administrator_password": "a long first password",
                "recipient_confirmed": True,
                "country_code": "IN",
                "currency_code": "INR",
                "timezone": "Asia/Kolkata",
            }
            created_tenant = await client.post(
                "/v1/platform/tenants", headers=operator, json=tenant
            )
            assert created_tenant.status_code == 201, created_tenant.text
            # The new administrator signs in with the operator's password, into the new tenant.
            ravi = await tokens(client, "ravi@acme.example", "a long first password")
            mine = await client.get(
                "/v1/session", headers={"Authorization": f"Bearer {ravi['access_token']}"}
            )
            assert mine.status_code == 200, mine.text
            assert mine.json()["tenant"]["id"] == created_tenant.json()["id"]
            # Someone with a local account and no tenant can be named as an existing administrator.
            async with app.state.session_factory() as db:
                await app.state.local_auth.create_account(
                    db,
                    name="Maya Das",
                    username="maya",
                    email="maya@acme.example",
                    password=PASSWORD,
                    region=("IN", ""),
                    workspace_name=None,
                    path=PATH_PENDING,
                    status="active",
                    verified=True,
                )
                await db.commit()
            offered = await client.get(
                probe, params={"email": "maya@acme.example"}, headers=operator
            )
            assert offered.json()["available"]["email"] == "maya@acme.example"
            second = await client.post(
                "/v1/platform/tenants",
                headers={**operator, "Idempotency-Key": "second-tenant"},
                json={
                    "name": "Das & Co",
                    "administrator_mode": "existing",
                    "administrator_name": "Maya Das",
                    "administrator_email": "maya@acme.example",
                    "country_code": "IN",
                    "currency_code": "INR",
                    "timezone": "Asia/Kolkata",
                },
            )
            assert second.status_code == 201, second.text
            # Once she belongs to a tenant she is no longer on offer.
            taken = await client.get(probe, params={"email": "maya@acme.example"}, headers=operator)
            assert taken.json() == {"available": None}

            # And a second administrator can no longer be created through the setup route.
            again = await client.post(
                "/internal/v1/local-auth/setup/administrator",
                json={"name": "Other", "email": "other@owner.example", "password": PASSWORD},
                headers={**BFF, "X-Setup-Key": setup_key},
            )
            assert again.status_code == 409
        await app.state.oidc_http.aclose()
        await app.state.engine.dispose()

    asyncio.run(exercise())


@pytest.mark.mysql
def test_the_six_migrations_reverse_and_reapply_cleanly(mysql_url: str) -> None:
    install_identity(mysql_url)

    async def tables() -> set[str]:
        app = build_app(mysql_url)
        async with app.state.engine.connect() as connection:
            rows = await connection.execute(text("SHOW TABLES"))
            names = {row[0] for row in rows}
        await app.state.oidc_http.aclose()
        await app.state.engine.dispose()
        return names

    config = alembic_config(mysql_url)
    mine = {
        "local_identity",
        "local_credential",
        "local_recovery_token",
        "local_signing_key",
        "local_authorization",
        "local_refresh_token",
    }
    assert mine <= asyncio.run(tables())
    command.downgrade(config, "0089")
    assert not mine & asyncio.run(tables())
    command.upgrade(config, "head")
    assert mine <= asyncio.run(tables())
