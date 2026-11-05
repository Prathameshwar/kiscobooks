from __future__ import annotations

import time

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from billing_platform.errors import AuthenticationRequiredError
from billing_platform.oidc import AccessTokenVerifier, IdentityProviderUnavailableError, OidcConfig


@pytest.fixture(scope="module")
def signing_key() -> RSAKey:
    return RSAKey.generate_key(2048, {"kid": "first"})


def token(key: RSAKey, **changes: object) -> str:
    now = int(time.time())
    return jwt.encode(
        {"alg": "RS256", "kid": "first"},
        {
            "iss": "https://id.test/application/o/web/",
            "aud": "web",
            "sub": "subject",
            "iat": now,
            "exp": now + 300,
            "scope": "openid billing.api",
            **changes,
        },
        key,
    )


def config() -> OidcConfig:
    return OidcConfig("https://id.test/application/o/web/", "web", "https://id.test/jwks/")


async def test_signature_claims_and_jwks_cache(signing_key: RSAKey) -> None:
    requests: list[str] = []

    def jwks(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, json={"keys": [signing_key.as_dict()]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(jwks)) as client:
        verifier = AccessTokenVerifier(config(), client)
        for _ in range(2):
            assert (await verifier.verify(token(signing_key))).sub == "subject"
        assert requests == [config().jwks_url]
        other = RSAKey.generate_key(2048, {"kid": "first"})
        with pytest.raises(AuthenticationRequiredError):
            await verifier.verify(token(other))


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://evil.test/"},
        {"aud": "mobile"},
        {"scope": "openid"},
        {"exp": 1},
        {"iat": int(time.time()) + 600},
        {"exp": int(time.time()) + 3600},
        {"email_verified": "true"},
        {"aud": ["web", "mobile"]},
        {"nbf": int(time.time()) + 600},
    ],
)
async def test_rejects_unusable_claims(signing_key: RSAKey, claims: dict[str, object]) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"keys": [signing_key.as_dict()]}),
        )
    ) as client:
        with pytest.raises(AuthenticationRequiredError):
            await AccessTokenVerifier(config(), client).verify(token(signing_key, **claims))


@pytest.mark.parametrize("value", ["", "bad", "a.b.c", "x" * 16385])
async def test_malformed_token_never_fetches_keys(value: str) -> None:
    def unreachable(_: httpx.Request) -> httpx.Response:
        raise AssertionError("malformed token fetched remote keys")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unreachable)) as client:
        with pytest.raises(AuthenticationRequiredError):
            await AccessTokenVerifier(config(), client).verify(value)


async def test_provider_outage_fails_closed_and_backs_off(signing_key: RSAKey) -> None:
    attempts = 0

    def outage(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(outage)) as client:
        verifier = AccessTokenVerifier(config(), client)
        for _ in range(2):
            with pytest.raises(IdentityProviderUnavailableError):
                await verifier.verify(token(signing_key))
        assert attempts == 1


def test_plaintext_or_dynamic_jwks_configuration_is_rejected() -> None:
    for url in (
        "http://id.test/jwks/",
        "https://user:password@id.test/jwks/",
        "https://id.test/?url=x",
    ):
        with pytest.raises(ValueError):
            OidcConfig("https://id.test/", "web", url)


@pytest.mark.parametrize(
    "host", ["http://localhost:8001/oidc", "http://127.0.0.1:8001/oidc", "http://[::1]:8001/oidc"]
)
def test_plain_http_is_accepted_for_loopback_only(host: str) -> None:
    # A development machine has no certificate, and traffic to loopback never leaves it.
    cfg = OidcConfig(host, "web", host + "/jwks")
    assert cfg.issuer == host


@pytest.mark.parametrize(
    "host",
    [
        "http://id.test/oidc",
        "http://localhost.evil.example/oidc",
        "http://127.0.0.1.evil.example/oidc",
        "http://10.0.0.5/oidc",
        "http://0.0.0.0/oidc",
        "http://localhost@evil.example/oidc",
        "ftp://localhost/oidc",
    ],
)
def test_plain_http_is_rejected_for_every_other_host(host: str) -> None:
    with pytest.raises(ValueError):
        OidcConfig(host, "web", host + "/jwks")


def test_loopback_http_does_not_excuse_credentials_query_or_fragment() -> None:
    for url in (
        "http://u:p@localhost/oidc",
        "http://user@localhost/oidc",
        "http://:secret@localhost/oidc",
        "https://user@id.test/oidc",
        "http://localhost/oidc?x=1",
        "http://localhost/oidc#f",
    ):
        with pytest.raises(ValueError):
            OidcConfig(url, "web", "http://localhost/jwks")
