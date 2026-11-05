"""How the local provider is configured, and which settings win (docs/local-auth.md §2)."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from identity.config import LocalAuthSettings, LocalClient, OidcSettings, Settings
from tests.api_support import ACTOR_SECRET, CURSOR_SECRET
from tests.local_auth_support import REDIRECT, local_settings

BASE: dict[str, Any] = {
    "database_url": "sqlite+aiosqlite:///:memory:",
    "actor_signing_secret": SecretStr(ACTOR_SECRET),
    "cursor_signing_secret": SecretStr(CURSOR_SECRET),
}


def client(**overrides: Any) -> LocalClient:
    values: dict[str, Any] = {
        "client_id": "billing-web",
        "secret_sha256": hashlib.sha256(b"s").hexdigest(),
        "redirect_uris": (REDIRECT,),
    }
    return LocalClient(**(values | overrides))


def test_local_is_the_default_provider() -> None:
    assert Settings(**BASE).auth_provider == "local"


def test_an_unknown_provider_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(**BASE, auth_provider="ldap")


def test_the_verifier_is_configured_from_the_provider_so_the_two_cannot_disagree() -> None:
    settings = Settings(**BASE, local_auth=local_settings())
    assert settings.oidc is not None
    assert settings.oidc.issuer == local_settings().issuer
    assert settings.oidc.audience == local_settings().audience
    assert settings.oidc.max_token_seconds == local_settings().access_token_seconds


def test_a_leftover_authentik_oidc_setting_does_not_override_the_local_provider() -> None:
    stale = OidcSettings(
        issuer="https://sso.example/application/o/bill/",
        audience="old",
        jwks_url="https://sso.example/jwks/",
    )
    settings = Settings(**BASE, local_auth=local_settings(), oidc=stale)
    assert settings.oidc is not None and settings.oidc.issuer == local_settings().issuer


def test_under_authentik_the_oidc_setting_is_left_alone_and_local_is_ignored() -> None:
    explicit = OidcSettings(
        issuer="https://sso.example/application/o/bill/",
        audience="web",
        jwks_url="https://sso.example/jwks/",
    )
    settings = Settings(
        **BASE, auth_provider="authentik", local_auth=local_settings(), oidc=explicit
    )
    assert settings.oidc == explicit
    assert Settings(**BASE, auth_provider="authentik", local_auth=local_settings()).oidc is None


def test_a_legacy_oidc_setting_with_no_provider_chosen_is_refused_not_half_applied() -> None:
    legacy = OidcSettings(
        issuer="https://sso.example/application/o/bill/",
        audience="web",
        jwks_url="https://sso.example/jwks/",
    )
    with pytest.raises(ValidationError, match="IDENTITY_AUTH_PROVIDER=authentik"):
        Settings(**BASE, oidc=legacy)
    # Either explicit choice is fine.
    assert Settings(**BASE, oidc=legacy, auth_provider="authentik").oidc == legacy
    assert Settings(**BASE, oidc=legacy, local_auth=local_settings()).oidc is not None


def test_an_unconfigured_local_provider_leaves_verification_off_rather_than_guessing() -> None:
    assert Settings(**BASE).oidc is None


def test_an_explicit_jwks_url_is_used_when_the_public_one_is_not_reachable_from_the_service() -> (
    None
):
    assert (
        Settings(
            **BASE, local_auth=local_settings(jwks_url="http://127.0.0.1:8001/oidc/jwks")
        ).oidc.jwks_url
        == "http://127.0.0.1:8001/oidc/jwks"
    )  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "overrides",
    [
        {"issuer": "http://sso.example/oidc"},
        {"issuer": "https://user:pw@sso.example/oidc"},
        {"issuer": "https://sso.example/oidc?x=1"},
        {"issuer": "https://sso.example/oidc#frag"},
        {"issuer": "http://localhost.evil.example/oidc"},
        {"auth_ui_url": "http://auth.example"},
        {"auth_ui_url": "https://auth.example/app"},
        {"jwks_url": "http://sso.example/jwks"},
        {"bff_secret": "too-short"},
        {"key_encryption_key": "not base64!!"},
        {"key_encryption_key": base64.b64encode(b"short").decode()},
        {"access_token_seconds": 901},
        {"access_token_seconds": 59},
        {"audience": "billing-web"},  # the client id: an ID token would pass as an access token
        {"session_seconds": 3599},
        {"session_seconds": 7_776_001},
        {"max_failed_attempts": 2},
        {"clients": ()},
        {"unexpected": True},
    ],
)
def test_unsafe_or_malformed_local_settings_are_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        local_settings(**overrides)


def test_loopback_http_is_accepted_and_nothing_else_over_http() -> None:
    for host in ("localhost", "127.0.0.1", "[::1]"):
        assert local_settings(
            issuer=f"http://{host}:8090/identity/oidc", auth_ui_url=f"http://{host}:4310"
        )


@pytest.mark.parametrize(
    "uris",
    [
        ("https://app.example/cb?x=1",),
        ("https://app.example/cb#f",),
        ("http://app.example/cb",),
        ("javascript:alert(1)",),
        ("https://app.example/cb", "https://app.example/cb"),
        (),
        ("https://u:p@app.example/cb",),
    ],
)
def test_a_redirect_uri_must_be_an_exact_https_or_loopback_address(uris: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        client(redirect_uris=uris)


def test_client_ids_must_be_unique_and_secrets_are_a_digest_only() -> None:
    with pytest.raises(ValidationError):
        local_settings(clients=(client(), client()))
    with pytest.raises(ValidationError):
        client(secret_sha256="plain-secret")


def test_secrets_are_not_printed() -> None:
    shown = repr(local_settings())
    assert "bff-secret" not in shown and "kkkk" not in shown
    assert isinstance(LocalAuthSettings, type)
