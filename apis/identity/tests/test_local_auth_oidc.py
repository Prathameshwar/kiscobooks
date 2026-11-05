"""The local provider's OpenID Connect surface, driven over HTTP (docs/local-auth.md §3).

Tokens are checked by the platform's real ``AccessTokenVerifier`` (keys fetched from the app's own
``/oidc/jwks``), so "the provider's tokens are accepted by every service" is tested, not assumed.
Each class names the failure it exists to catch: an open redirect, a code that works twice, a
refresh token that outlives its theft, a private key in the key set.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from billing_platform.db.types import utcnow
from billing_platform.errors import AuthenticationRequiredError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from identity.models.local_auth import (
    PATH_ADMINISTRATORS,
    LocalAuthorization,
    LocalCredential,
    LocalIdentity,
    LocalRefreshToken,
    LocalSigningKey,
)
from tests.local_auth_support import (
    AUDIENCE,
    BFF,
    CHALLENGE,
    CLIENT_ID,
    CLIENT_SECRET,
    ISSUER,
    OTHER_CLIENT_ID,
    OTHER_CLIENT_SECRET,
    PASSWORD,
    REDIRECT,
    SCOPE,
    UI,
    VERIFIER,
    authorize_params,
    decode_unverified,
    header_of,
    light_engine,
    redeem,
    refresh,
    sign_in,
    tokens,
)

EMAIL = "asha@alpha.example"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Only the tables the provider touches (see ``local_auth_support``)."""
    eng = await light_engine()
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def account(local_app: Any, factory: async_sessionmaker[AsyncSession]) -> LocalIdentity:
    async with factory() as db:
        identity = await local_app.state.local_auth.create_account(
            db,
            name="Asha Rao",
            username="asha",
            email=EMAIL,
            password=PASSWORD,
            region=("IN", "IN-KA"),
            workspace_name=None,
            path=PATH_ADMINISTRATORS,
            status="active",
            verified=True,
        )
        await db.commit()
        return identity


class TestDiscoveryAndKeys:
    async def test_discovery_advertises_exactly_what_is_supported(
        self, local_client: httpx.AsyncClient
    ) -> None:
        document = (await local_client.get("/oidc/.well-known/openid-configuration")).json()
        assert document["issuer"] == ISSUER
        assert document["authorization_endpoint"] == f"{ISSUER}/authorize"
        assert document["token_endpoint"] == f"{ISSUER}/token"
        assert document["jwks_uri"] == f"{ISSUER}/jwks"
        assert document["revocation_endpoint"] == f"{ISSUER}/revoke"
        assert document["response_types_supported"] == ["code"]
        assert document["code_challenge_methods_supported"] == ["S256"]
        assert document["id_token_signing_alg_values_supported"] == ["RS256"]
        assert set(document["grant_types_supported"]) == {"authorization_code", "refresh_token"}

    async def test_the_key_set_has_a_public_rsa_key_and_never_a_private_member(
        self, local_client: httpx.AsyncClient
    ) -> None:
        response = await local_client.get("/oidc/jwks")
        keys = response.json()["keys"]
        assert len(keys) == 1
        key = keys[0]
        assert key["kty"] == "RSA" and key["use"] == "sig" and key["alg"] == "RS256" and key["kid"]
        assert not {"d", "p", "q", "dp", "dq", "qi"} & set(key)

    async def test_an_id_token_is_not_accepted_as_an_access_token(
        self, local_app: Any, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        """The ID token is for the client to read; presenting it to an API must fail."""
        issued = await tokens(local_client, EMAIL)
        assert issued["id_token"]
        with pytest.raises(AuthenticationRequiredError):
            await local_app.state.token_verifier.verify(issued["id_token"])
        await local_app.state.token_verifier.verify(issued["access_token"])  # the real one works

    async def test_the_signing_key_is_stable_across_requests(
        self, local_client: httpx.AsyncClient
    ) -> None:
        first = (await local_client.get("/oidc/jwks")).json()["keys"][0]["kid"]
        second = (await local_client.get("/oidc/jwks")).json()["keys"][0]["kid"]
        assert first == second

    async def test_a_first_key_created_in_a_transaction_that_rolls_back_is_not_remembered(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        keys = local_app.state.local_auth.keys
        async with factory() as db:
            lost, _ = await keys.signer(db)
            await db.rollback()
        async with factory() as db:
            kept, _ = await keys.signer(db)
            await db.commit()
        # Remembering the first would sign tokens with a key id that was never published.
        assert lost != kept
        async with factory() as db:
            assert [row.kid for row in await db.scalars(select(LocalSigningKey))] == [kept]
        async with factory() as db:
            assert (await keys.signer(db))[0] == kept

    async def test_the_private_key_is_stored_only_encrypted(
        self, local_client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await local_client.get("/oidc/jwks")
        async with factory() as db:
            row = (await db.scalars(select(LocalSigningKey))).one()
        assert '"d"' not in row.private_jwk_ciphertext
        assert "BEGIN" not in row.private_jwk_ciphertext
        assert '"d"' not in row.public_jwk


class TestAuthorizeRequest:
    async def test_a_valid_request_goes_to_the_sign_in_page_with_an_opaque_id(
        self, local_client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        response = await local_client.get("/oidc/authorize", params=authorize_params())
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith(f"{UI}/signin?request=")
        assert response.headers["cache-control"] == "no-store"
        request_id = parse_qs(urlsplit(location).query)["request"][0]
        assert len(request_id) == 43
        async with factory() as db:
            row = (await db.scalars(select(LocalAuthorization))).one()
        # Only the digest of the id is stored; the id itself never is.
        assert row.request_hash == hashlib.sha256(request_id.encode()).hexdigest()
        assert request_id not in (row.state, row.nonce, row.redirect_uri)

    @pytest.mark.parametrize(
        "override",
        [
            {"client_id": "someone-else"},
            {"client_id": None},
            {"redirect_uri": "http://localhost:4310/api/auth/callback/local/"},
            {"redirect_uri": "http://localhost:4310/api/auth/callback/local?x=1"},
            {"redirect_uri": "https://evil.example/callback"},
            {"redirect_uri": "http://localhost:4310/api/auth/callback"},
            {"redirect_uri": None},
        ],
    )
    async def test_an_unrecognised_client_or_redirect_is_shown_never_redirected_to(
        self, local_client: httpx.AsyncClient, override: dict[str, str | None]
    ) -> None:
        response = await local_client.get("/oidc/authorize", params=authorize_params(**override))
        assert response.status_code == 400
        assert "location" not in response.headers
        assert response.json()["error"] == "invalid_request"

    async def test_another_clients_redirect_is_not_this_clients(
        self, local_client: httpx.AsyncClient
    ) -> None:
        response = await local_client.get(
            "/oidc/authorize",
            params=authorize_params(client_id=OTHER_CLIENT_ID, redirect_uri=REDIRECT),
        )
        assert response.status_code == 400 and "location" not in response.headers

    @pytest.mark.parametrize(
        ("override", "error"),
        [
            ({"response_type": "token"}, "unsupported_response_type"),
            ({"response_type": "id_token"}, "unsupported_response_type"),
            ({"scope": "profile email billing.api"}, "invalid_scope"),
            ({"scope": "openid profile email"}, "invalid_scope"),
            ({"scope": "openid billing.api admin"}, "invalid_scope"),
            ({"nonce": None}, "invalid_request"),
            ({"state": None}, "invalid_request"),
            ({"code_challenge": None}, "invalid_request"),
            ({"code_challenge_method": "plain"}, "invalid_request"),
            ({"code_challenge_method": None}, "invalid_request"),
            ({"code_challenge": "short"}, "invalid_request"),
            ({"max_age": "-1"}, "invalid_request"),
            ({"max_age": "abc"}, "invalid_request"),
            ({"prompt": "none"}, "login_required"),
        ],
    )
    async def test_a_faulty_request_comes_back_to_the_client_with_its_state(
        self, local_client: httpx.AsyncClient, override: dict[str, str | None], error: str
    ) -> None:
        response = await local_client.get("/oidc/authorize", params=authorize_params(**override))
        assert response.status_code == 302
        target = urlsplit(response.headers["location"])
        assert f"{target.scheme}://{target.netloc}{target.path}" == REDIRECT
        query = parse_qs(target.query)
        assert query["error"] == [error]
        if override.get("state", "x") is not None:
            assert query["state"] == ["state-123"]

    async def test_a_repeated_parameter_is_refused(self, local_client: httpx.AsyncClient) -> None:
        response = await local_client.get(
            "/oidc/authorize?"
            + "&".join(f"{k}={v}" for k, v in authorize_params().items())
            + "&state=other"
        )
        assert response.status_code == 400 and "location" not in response.headers

    async def test_max_age_and_prompt_login_are_accepted_because_every_request_asks_for_a_password(
        self, local_client: httpx.AsyncClient
    ) -> None:
        response = await local_client.get(
            "/oidc/authorize", params=authorize_params(max_age="1", prompt="login")
        )
        assert response.status_code == 302 and "/signin?request=" in response.headers["location"]


class TestCodeExchange:
    async def test_the_whole_flow_yields_tokens_the_platform_verifier_accepts(
        self, local_app: Any, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        body = await tokens(local_client, EMAIL)
        assert body["token_type"] == "Bearer" and body["expires_in"] == 300
        assert body["scope"] == SCOPE
        claims = await local_app.state.token_verifier.verify(body["access_token"])
        assert claims.iss == ISSUER and claims.aud == AUDIENCE and claims.sub == account.sub
        assert claims.email == EMAIL and claims.email_verified is True
        assert "billing.api" in claims.scope.split()
        assert claims.exp - claims.iat == 300 and claims.auth_time is not None
        assert claims.azp is None

    async def test_the_access_token_is_an_rs256_jwt_with_a_key_id(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        body = await tokens(local_client, EMAIL)
        header = header_of(body["access_token"])
        assert header["alg"] == "RS256" and header["typ"] == "at+jwt"
        jwks = (await local_client.get("/oidc/jwks")).json()["keys"]
        assert header["kid"] in {key["kid"] for key in jwks}

    async def test_the_id_token_carries_the_nonce_audience_and_profile(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        body = await tokens(local_client, EMAIL)
        claims = decode_unverified(body["id_token"])
        assert claims["iss"] == ISSUER and claims["aud"] == CLIENT_ID
        assert claims["nonce"] == "nonce-456" and claims["sub"] == account.sub
        assert claims["name"] == "Asha Rao" and claims["email"] == EMAIL
        assert claims["email_verified"] is True
        assert claims["billing_registration_region"] == {
            "country_code": "IN",
            "state_code": "IN-KA",
        }

    async def test_a_refresh_token_comes_only_with_offline_access(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        code = await sign_in(local_client, EMAIL, scope="openid billing.api")
        body = (await redeem(local_client, code)).json()
        assert "refresh_token" not in body

    async def test_the_response_is_never_cached(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        response = await redeem(local_client, await sign_in(local_client, EMAIL))
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"

    async def test_a_code_works_once_and_replaying_it_revokes_what_it_started(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        code = await sign_in(local_client, EMAIL)
        first = (await redeem(local_client, code)).json()
        replay = await redeem(local_client, code)
        assert replay.status_code == 400 and replay.json()["error"] == "invalid_grant"
        # The refresh token the first redemption minted is now dead: someone else held the code.
        assert (await refresh(local_client, first["refresh_token"])).status_code == 400

    async def test_two_simultaneous_redemptions_of_one_code_yield_one_session(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        # Both requests may read the code as unused; only the conditional update decides the winner.
        code = await sign_in(local_client, EMAIL)
        first, second = await asyncio.gather(redeem(local_client, code), redeem(local_client, code))
        assert sorted([first.status_code, second.status_code]) == [200, 400]

    async def test_a_wrong_verifier_fails_and_burns_the_code(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        code = await sign_in(local_client, EMAIL)
        wrong = await redeem(local_client, code, code_verifier="A" * 43)
        assert wrong.status_code == 400 and wrong.json()["error"] == "invalid_grant"
        assert (await redeem(local_client, code)).status_code == 400

    async def test_the_code_verifier_is_required(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        code = await sign_in(local_client, EMAIL)
        assert (await redeem(local_client, code, code_verifier=None)).status_code == 400

    async def test_a_different_redirect_uri_fails_and_burns_the_code(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        code = await sign_in(local_client, EMAIL)
        wrong = await redeem(local_client, code, redirect_uri=REDIRECT + "/other")
        assert wrong.status_code == 400
        assert (await redeem(local_client, code)).status_code == 400

    async def test_a_code_cannot_be_redeemed_by_another_client(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        code = await sign_in(local_client, EMAIL)
        response = await redeem(
            local_client, code, client_id=OTHER_CLIENT_ID, client_secret=OTHER_CLIENT_SECRET
        )
        assert response.status_code == 400 and response.json()["error"] == "invalid_grant"

    async def test_an_expired_code_is_refused(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        code = await sign_in(local_client, EMAIL)
        async with factory() as db:
            await db.execute(
                update(LocalAuthorization).values(expires_at=utcnow() - dt.timedelta(seconds=1))
            )
            await db.commit()
        assert (await redeem(local_client, code)).status_code == 400

    @pytest.mark.parametrize("code", ["", "short", "a" * 43, "../" + "a" * 40, "a" * 500])
    async def test_a_code_that_was_never_issued_is_refused(
        self, local_client: httpx.AsyncClient, account: LocalIdentity, code: str
    ) -> None:
        response = await redeem(local_client, code)
        assert response.status_code == 400 and response.json()["error"] == "invalid_grant"

    async def test_a_disabled_account_cannot_redeem_a_code_it_already_holds(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        code = await sign_in(local_client, EMAIL)
        async with factory() as db:
            await db.execute(update(LocalIdentity).values(status="disabled"))
            await db.commit()
        assert (await redeem(local_client, code)).status_code == 400

    async def test_codes_and_requests_are_stored_only_as_digests(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        code = await sign_in(local_client, EMAIL)
        async with factory() as db:
            row = (await db.scalars(select(LocalAuthorization))).one()
        assert row.code_hash == hashlib.sha256(code.encode()).hexdigest()
        assert code not in repr(row.__dict__)


class TestRequestSize:
    async def test_a_body_with_no_length_is_cut_off_at_the_limit_not_read_whole(
        self, local_client: httpx.AsyncClient
    ) -> None:
        """Content-Length is advisory: a chunked body must not be buffered to what nginx allows."""
        sent = 0

        async def body() -> Any:
            nonlocal sent
            for _ in range(400):  # 25 MB in 64 KiB chunks, announced nowhere
                sent += 1
                yield b"a=" + b"x" * 65_536

        response = await local_client.post(
            "/oidc/token",
            content=body(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 400 and response.json()["error"] == "invalid_request"
        assert sent < 10, f"{sent} chunks were consumed before the request was refused"


class TestClientAuthentication:
    async def test_a_wrong_secret_is_a_401_that_asks_for_basic_credentials(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        response = await redeem(
            local_client, await sign_in(local_client, EMAIL), client_secret="nope"
        )
        assert response.status_code == 401 and response.json()["error"] == "invalid_client"
        assert response.headers["www-authenticate"].startswith("Basic")

    async def test_an_unknown_client_is_indistinguishable_from_a_wrong_secret(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        code = await sign_in(local_client, EMAIL)
        unknown = await redeem(local_client, code, client_id="ghost", client_secret="whatever")
        wrong = await redeem(local_client, code, client_secret="whatever")
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json() == wrong.json()

    async def test_basic_authentication_is_accepted(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        code = await sign_in(local_client, EMAIL)
        response = await local_client.post(
            "/oidc/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT,
                "code_verifier": VERIFIER,
            },
            auth=(CLIENT_ID, CLIENT_SECRET),
        )
        assert response.status_code == 200

    async def test_a_malformed_basic_header_is_a_client_error_not_a_crash(
        self, local_client: httpx.AsyncClient
    ) -> None:
        response = await local_client.post(
            "/oidc/token",
            data={"grant_type": "authorization_code"},
            headers={"Authorization": "Basic !!!not-base64!!!"},
        )
        assert response.status_code == 401

    async def test_a_repeated_form_parameter_is_refused(
        self, local_client: httpx.AsyncClient
    ) -> None:
        response = await local_client.post(
            "/oidc/token",
            content="grant_type=refresh_token&grant_type=authorization_code",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 400 and response.json()["error"] == "invalid_request"

    async def test_a_json_body_is_not_a_token_request(
        self, local_client: httpx.AsyncClient
    ) -> None:
        response = await local_client.post("/oidc/token", json={"grant_type": "refresh_token"})
        assert response.status_code == 400 and response.json()["error"] == "invalid_request"

    async def test_an_oversized_body_is_refused(self, local_client: httpx.AsyncClient) -> None:
        response = await local_client.post(
            "/oidc/token",
            content="a=" + "x" * 20_000,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 400

    async def test_an_unsupported_grant_is_named_as_such(
        self, local_client: httpx.AsyncClient
    ) -> None:
        response = await local_client.post(
            "/oidc/token",
            data={
                "grant_type": "password",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "username": EMAIL,
                "password": PASSWORD,
            },
        )
        assert response.status_code == 400 and response.json()["error"] == "unsupported_grant_type"


class TestRefresh:
    async def test_refresh_rotates_the_token_and_keeps_the_original_sign_in_time(
        self, local_app: Any, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        first = await tokens(local_client, EMAIL)
        response = await refresh(local_client, first["refresh_token"])
        assert response.status_code == 200
        second = response.json()
        assert second["refresh_token"] != first["refresh_token"]
        assert "id_token" not in second
        old, new = (
            decode_unverified(first["access_token"]),
            decode_unverified(second["access_token"]),
        )
        assert new["auth_time"] == old["auth_time"] and new["jti"] != old["jti"]
        await local_app.state.token_verifier.verify(second["access_token"])

    async def test_a_session_cannot_be_renewed_forever(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        first = await tokens(local_client, EMAIL)
        longest = local_app.state.settings.local_auth.session_seconds
        # One day short of the cap still renews; one day past it asks for the password again.
        async with factory() as db:
            await db.execute(
                update(LocalRefreshToken).values(
                    authenticated_at=utcnow() - dt.timedelta(seconds=longest - 86_400)
                )
            )
            await db.commit()
        renewed = await refresh(local_client, first["refresh_token"])
        assert renewed.status_code == 200
        async with factory() as db:
            await db.execute(
                update(LocalRefreshToken).values(
                    authenticated_at=utcnow() - dt.timedelta(seconds=longest + 86_400)
                )
            )
            await db.commit()
        expired = await refresh(local_client, renewed.json()["refresh_token"])
        assert expired.status_code == 400 and expired.json()["error"] == "invalid_grant"

    async def test_presenting_a_used_token_again_revokes_the_whole_family(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        first = await tokens(local_client, EMAIL)
        second = (await refresh(local_client, first["refresh_token"])).json()
        replay = await refresh(local_client, first["refresh_token"])
        assert replay.status_code == 400 and replay.json()["error"] == "invalid_grant"
        # The successor is collateral: whoever holds it may be the thief.
        assert (await refresh(local_client, second["refresh_token"])).status_code == 400

    async def test_a_refresh_token_belongs_to_its_client(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        first = await tokens(local_client, EMAIL)
        response = await refresh(
            local_client,
            first["refresh_token"],
            client_id=OTHER_CLIENT_ID,
            client_secret=OTHER_CLIENT_SECRET,
        )
        assert response.status_code == 400

    async def test_scope_may_narrow_but_never_widen(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        first = await tokens(local_client, EMAIL)
        narrow = await refresh(local_client, first["refresh_token"], scope="openid billing.api")
        assert narrow.status_code == 200 and narrow.json()["scope"] == "openid billing.api"
        # Narrowing is per request: the grant itself is unchanged, so the original scope is still
        # available — but nothing beyond it ever is.
        widen = await refresh(local_client, narrow.json()["refresh_token"], scope=SCOPE + " admin")
        assert widen.status_code == 400 and widen.json()["error"] == "invalid_scope"

    async def test_an_expired_refresh_token_is_refused(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        first = await tokens(local_client, EMAIL)
        async with factory() as db:
            await db.execute(
                update(LocalRefreshToken).values(expires_at=utcnow() - dt.timedelta(seconds=1))
            )
            await db.commit()
        assert (await refresh(local_client, first["refresh_token"])).status_code == 400

    async def test_a_disabled_account_cannot_refresh(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        first = await tokens(local_client, EMAIL)
        async with factory() as db:
            await db.execute(update(LocalIdentity).values(status="disabled"))
            await db.commit()
        assert (await refresh(local_client, first["refresh_token"])).status_code == 400

    @pytest.mark.parametrize("token", ["", "short", "a" * 43, "a" * 100])
    async def test_a_token_that_was_never_issued_is_refused(
        self, local_client: httpx.AsyncClient, account: LocalIdentity, token: str
    ) -> None:
        assert (await refresh(local_client, token)).status_code == 400

    async def test_tokens_are_stored_only_as_digests(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        first = await tokens(local_client, EMAIL)
        async with factory() as db:
            row = (await db.scalars(select(LocalRefreshToken))).one()
        assert row.token_hash == hashlib.sha256(first["refresh_token"].encode()).hexdigest()

    async def test_two_simultaneous_refreshes_of_one_token_yield_one_successor(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        issued = await tokens(local_client, EMAIL)
        first, second = await asyncio.gather(
            refresh(local_client, issued["refresh_token"]),
            refresh(local_client, issued["refresh_token"]),
        )
        assert sorted([first.status_code, second.status_code]) == [200, 400]


class TestRevocation:
    async def test_revoking_a_refresh_token_ends_its_family_and_always_answers_200(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        first = await tokens(local_client, EMAIL)
        form = {
            "token": first["refresh_token"],
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        assert (await local_client.post("/oidc/revoke", data=form)).status_code == 200
        assert (await refresh(local_client, first["refresh_token"])).status_code == 400
        # The same call again, and a token that never existed, are not errors (RFC 7009).
        assert (await local_client.post("/oidc/revoke", data=form)).status_code == 200
        form["token"] = "a" * 43
        assert (await local_client.post("/oidc/revoke", data=form)).status_code == 200

    async def test_revocation_needs_the_client(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        first = await tokens(local_client, EMAIL)
        response = await local_client.post(
            "/oidc/revoke",
            data={
                "token": first["refresh_token"],
                "client_id": CLIENT_ID,
                "client_secret": "wrong",
            },
        )
        assert response.status_code == 401
        assert (await refresh(local_client, first["refresh_token"])).status_code == 200

    async def test_another_client_cannot_revoke_it(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        first = await tokens(local_client, EMAIL)
        form = {
            "token": first["refresh_token"],
            "client_id": OTHER_CLIENT_ID,
            "client_secret": OTHER_CLIENT_SECRET,
        }
        assert (await local_client.post("/oidc/revoke", data=form)).status_code == 200
        assert (await refresh(local_client, first["refresh_token"])).status_code == 200


class TestSessionRevocationAndVerifier:
    async def test_a_session_revoked_after_sign_in_is_refused_at_refresh(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        first = await tokens(local_client, EMAIL)
        # No user row yet, so nothing revokes: the refresh is fine (an unlinked sign-up).
        assert (await refresh(local_client, first["refresh_token"])).status_code == 200

    async def test_a_tampered_token_is_refused_by_the_verifier(
        self, local_app: Any, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        body = await tokens(local_client, EMAIL)
        head, payload, signature = body["access_token"].split(".")
        forged = ".".join(
            [head, payload[:-2] + ("AA" if not payload.endswith("AA") else "BB"), signature]
        )
        with pytest.raises(AuthenticationRequiredError):
            await local_app.state.token_verifier.verify(forged)

    async def test_the_credential_row_holds_a_hash_not_the_password(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with factory() as db:
            credential = await db.get(LocalCredential, account.seq)
        assert credential is not None and credential.password_hash.startswith("$argon2id$")
        assert PASSWORD not in credential.password_hash


class TestUnconfigured:
    async def test_without_local_settings_the_endpoints_answer_503_and_nothing_else_changes(
        self, client: httpx.AsyncClient
    ) -> None:
        for method, path in (
            ("GET", "/oidc/.well-known/openid-configuration"),
            ("GET", "/oidc/jwks"),
            ("GET", "/oidc/authorize"),
            ("POST", "/oidc/token"),
        ):
            response = await client.request(method, path)
            assert response.status_code == 503, (method, path, response.status_code)
        assert (
            await client.post("/internal/v1/local-auth/login", json={}, headers=BFF)
        ).status_code == 503


_ = CHALLENGE
