"""Prepare this machine to sign in with the local authentication provider.

Writes two private development files and nothing else (docs/local-auth.md §2):

* ``<env-dir>/identity.env``      ``IDENTITY_AUTH_PROVIDER`` and ``IDENTITY_LOCAL_AUTH``
* ``<auth-env>`` (the Auth app's ``.env.local``)   ``AUTH_PROVIDER`` and ``AUTH_LOCAL_*``

It is safe to run again. Existing values are preserved byte for byte: the key-encryption key must
never change once a signing key has been stored under it, an installation that chose
``authentik`` stays on it, and a client secret is only replaced when the Auth app has lost its copy
(Identity keeps just the digest, so nothing else depends on it). Output names variables; it never
prints a secret.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

CLIENT_ID = "billing-web"
#: What access tokens are addressed to. Never the client id: an ID token's audience is the client id.
API_AUDIENCE = "billing-api"
DEFAULT_ISSUER = "http://localhost:8090/identity/oidc"
DEFAULT_JWKS = "http://127.0.0.1:8001/oidc/jwks"
DEFAULT_AUTH_URL = "http://localhost:4310"
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class ConfigurationError(ValueError):
    pass


def parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not name:
            raise ConfigurationError("An environment file contains a line this tool cannot read.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    return values


def update(text: str, changes: dict[str, str]) -> str:
    """Set each name, replacing an existing line in place and appending the rest."""
    lines = text.splitlines()
    remaining = dict(changes)
    for index, line in enumerate(lines):
        name = line.partition("=")[0].strip()
        if name in remaining and not line.lstrip().startswith("#"):
            lines[index] = f"{name}={remaining.pop(name)}"
    lines.extend(f"{name}={value}" for name, value in remaining.items())
    return "\n".join(lines) + "\n"


def secret() -> str:
    return secrets.token_urlsafe(48)


def safe_origin(value: str, *, what: str) -> str:
    parsed = urlsplit(value)
    secure = parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in LOOPBACK)
    if (
        not secure
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(f"{what} must be https, or http on loopback, with no credentials.")
    return value.rstrip("/")


def build(
    auth_url: str, *, issuer: str = DEFAULT_ISSUER, jwks_url: str = DEFAULT_JWKS
) -> tuple[dict[str, Any], str]:
    """A fresh provider configuration and the plaintext client secret it was built around."""
    origin = safe_origin(auth_url, what="The Auth app address")
    client_secret = secret()
    configuration: dict[str, Any] = {
        "issuer": safe_origin(issuer, what="The issuer"),
        "jwks_url": safe_origin(jwks_url, what="The key-set address"),
        "audience": API_AUDIENCE,
        "auth_ui_url": origin,
        "clients": [
            {
                "client_id": CLIENT_ID,
                "secret_sha256": hashlib.sha256(client_secret.encode()).hexdigest(),
                "redirect_uris": [f"{origin}/api/auth/callback/local"],
            }
        ],
        "bff_secret": secret(),
        "key_encryption_key": base64.b64encode(secrets.token_bytes(32)).decode(),
    }
    return configuration, client_secret


def plan(
    identity: dict[str, str], auth: dict[str, str]
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """What to write to each file, and what was left alone, without touching the disk."""
    notes: list[str] = []
    provider = identity.get("IDENTITY_AUTH_PROVIDER", "local")
    if provider != "local":
        return {}, {}, [f"Identity is set to {provider!r}; the local provider was not configured."]
    identity_changes: dict[str, str] = {"IDENTITY_AUTH_PROVIDER": "local"}
    auth_changes: dict[str, str] = {"AUTH_PROVIDER": "local"}
    auth_url = auth.get("NEXTAUTH_URL", DEFAULT_AUTH_URL)

    existing = identity.get("IDENTITY_LOCAL_AUTH")
    if existing:
        try:
            configuration = json.loads(existing)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                "IDENTITY_LOCAL_AUTH exists but is not valid JSON; it was not changed."
            ) from exc
        notes.append("IDENTITY_LOCAL_AUTH already exists and was kept.")
        client_secret = auth.get("AUTH_LOCAL_CLIENT_SECRET")
        if not client_secret:
            # Identity holds only a digest, so a lost copy is replaced, not recovered.
            client_secret = secret()
            configuration["clients"][0]["secret_sha256"] = hashlib.sha256(
                client_secret.encode()
            ).hexdigest()
            identity_changes["IDENTITY_LOCAL_AUTH"] = json.dumps(
                configuration, separators=(",", ":")
            )
            notes.append("The Auth app had no client secret, so a new one was issued.")
    else:
        configuration, client_secret = build(auth_url)
        identity_changes["IDENTITY_LOCAL_AUTH"] = json.dumps(configuration, separators=(",", ":"))
        notes.append("Created IDENTITY_LOCAL_AUTH with new secrets.")

    auth_changes["AUTH_LOCAL_ISSUER"] = configuration["issuer"]
    auth_changes["AUTH_LOCAL_CLIENT_ID"] = configuration["clients"][0]["client_id"]
    auth_changes["AUTH_LOCAL_CLIENT_SECRET"] = client_secret
    auth_changes["AUTH_LOCAL_BFF_SECRET"] = configuration["bff_secret"]
    # A leftover verifier setting would be ignored by Identity, but it is misleading to keep.
    return identity_changes, auth_changes, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-dir", type=Path, required=True)
    parser.add_argument("--auth-env", type=Path, required=True)
    options = parser.parse_args(argv)
    identity_path = options.env_dir / "identity.env"
    if not identity_path.is_file():
        raise ConfigurationError("identity.env does not exist; run setup first.")
    identity_text = identity_path.read_text(encoding="utf-8-sig")
    auth_text = (
        options.auth_env.read_text(encoding="utf-8-sig") if options.auth_env.is_file() else ""
    )
    identity_changes, auth_changes, notes = plan(parse(identity_text), parse(auth_text))
    if identity_changes:
        # Both files are computed before either is written, so a failure leaves both untouched.
        new_identity, new_auth = (
            update(identity_text, identity_changes),
            update(auth_text, auth_changes),
        )
        identity_path.write_text(new_identity, encoding="utf-8")
        options.auth_env.write_text(new_auth, encoding="utf-8")
        print("Updated:", ", ".join(sorted(identity_changes) + sorted(auth_changes)))
    for note in notes:
        print(note)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigurationError as error:
        print(str(error))
        raise SystemExit(2) from None
