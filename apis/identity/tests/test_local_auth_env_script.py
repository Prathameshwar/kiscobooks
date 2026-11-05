"""The development helper that prepares local sign-in (start/win/configure-local-auth.py).

It writes secrets, so what matters is what it refuses to disturb: a key-encryption key that signing
keys already depend on, an installation that chose Authentik, and the file it must never print.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

from identity.config import LocalAuthSettings

SCRIPT = Path(__file__).resolve().parents[3] / "start" / "win" / "configure-local-auth.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("configure_local_auth", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load()


def files(
    tmp_path: Path,
    identity: str = "IDENTITY_DATABASE_URL=mysql://x\n",
    auth: str = "NEXTAUTH_URL=http://localhost:4310\n",
):
    env = tmp_path / "env"
    env.mkdir()
    (env / "identity.env").write_text(identity, encoding="utf-8")
    auth_env = tmp_path / ".env.local"
    auth_env.write_text(auth, encoding="utf-8")
    return env, auth_env


def run(env: Path, auth_env: Path, capsys: pytest.CaptureFixture[str]) -> str:
    assert tool.main(["--env-dir", str(env), "--auth-env", str(auth_env)]) == 0
    return capsys.readouterr().out


def test_a_first_run_writes_a_valid_provider_and_the_matching_auth_app_settings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env, auth_env = files(tmp_path)
    run(env, auth_env, capsys)

    identity = tool.parse((env / "identity.env").read_text())
    auth = tool.parse(auth_env.read_text())
    assert identity["IDENTITY_AUTH_PROVIDER"] == "local" and auth["AUTH_PROVIDER"] == "local"
    settings = LocalAuthSettings.model_validate(json.loads(identity["IDENTITY_LOCAL_AUTH"]))
    assert settings.issuer == auth["AUTH_LOCAL_ISSUER"]
    # Access tokens are addressed to the API, never to the client an ID token is addressed to.
    assert settings.audience == "billing-api" and settings.audience != settings.clients[0].client_id
    assert settings.clients[0].client_id == auth["AUTH_LOCAL_CLIENT_ID"]
    # Identity holds only the digest; the Auth app holds the secret that hashes to it.
    assert (
        settings.clients[0].secret_sha256
        == hashlib.sha256(auth["AUTH_LOCAL_CLIENT_SECRET"].encode()).hexdigest()
    )
    assert settings.bff_secret.get_secret_value() == auth["AUTH_LOCAL_BFF_SECRET"]
    assert settings.clients[0].redirect_uris == ("http://localhost:4310/api/auth/callback/local",)
    assert len(base64.b64decode(settings.key_encryption_key.get_secret_value())) == 32


def test_the_other_lines_in_both_files_are_kept_in_place(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env, auth_env = files(
        tmp_path,
        identity='# keep me\nIDENTITY_DATABASE_URL=mysql://x\nIDENTITY_OIDC={"a":1}\nIDENTITY_REDIS_URL=redis://r\n',
        auth="NEXTAUTH_URL=http://localhost:4310\nAUTHENTIK_ISSUER=https://sso.example\nNEXTAUTH_SECRET=abc\n",
    )
    run(env, auth_env, capsys)
    identity, auth = (env / "identity.env").read_text(), auth_env.read_text()
    assert identity.startswith(
        '# keep me\nIDENTITY_DATABASE_URL=mysql://x\nIDENTITY_OIDC={"a":1}\nIDENTITY_REDIS_URL=redis://r\n'
    )
    assert "AUTHENTIK_ISSUER=https://sso.example" in auth and "NEXTAUTH_SECRET=abc" in auth


def test_a_second_run_changes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    env, auth_env = files(tmp_path)
    run(env, auth_env, capsys)
    before = ((env / "identity.env").read_bytes(), auth_env.read_bytes())
    run(env, auth_env, capsys)
    assert ((env / "identity.env").read_bytes(), auth_env.read_bytes()) == before


def test_the_key_encryption_key_survives_a_rerun_because_stored_signing_keys_depend_on_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env, auth_env = files(tmp_path)
    run(env, auth_env, capsys)
    first = json.loads(tool.parse((env / "identity.env").read_text())["IDENTITY_LOCAL_AUTH"])[
        "key_encryption_key"
    ]
    auth_env.write_text(auth_env.read_text().replace("AUTH_LOCAL_CLIENT_SECRET=", "REMOVED="))
    run(env, auth_env, capsys)
    assert (
        json.loads(tool.parse((env / "identity.env").read_text())["IDENTITY_LOCAL_AUTH"])[
            "key_encryption_key"
        ]
        == first
    )


def test_a_lost_client_secret_is_reissued_and_only_its_digest_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env, auth_env = files(tmp_path)
    run(env, auth_env, capsys)
    old = json.loads(tool.parse((env / "identity.env").read_text())["IDENTITY_LOCAL_AUTH"])
    auth_env.write_text(
        "\n".join(
            line
            for line in auth_env.read_text().splitlines()
            if not line.startswith("AUTH_LOCAL_CLIENT_SECRET=")
        )
        + "\n"
    )
    output = run(env, auth_env, capsys)
    new = json.loads(tool.parse((env / "identity.env").read_text())["IDENTITY_LOCAL_AUTH"])
    secret = tool.parse(auth_env.read_text())["AUTH_LOCAL_CLIENT_SECRET"]
    assert new["clients"][0]["secret_sha256"] == hashlib.sha256(secret.encode()).hexdigest()
    assert new["clients"][0]["secret_sha256"] != old["clients"][0]["secret_sha256"]
    assert {key: value for key, value in new.items() if key != "clients"} == {
        key: value for key, value in old.items() if key != "clients"
    }
    assert "new one was issued" in output


def test_an_installation_that_chose_authentik_is_left_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env, auth_env = files(
        tmp_path, identity="IDENTITY_AUTH_PROVIDER=authentik\nIDENTITY_DATABASE_URL=mysql://x\n"
    )
    before = ((env / "identity.env").read_bytes(), auth_env.read_bytes())
    output = run(env, auth_env, capsys)
    assert ((env / "identity.env").read_bytes(), auth_env.read_bytes()) == before
    assert "authentik" in output


def test_a_broken_existing_setting_is_reported_and_nothing_is_written(tmp_path: Path) -> None:
    env, auth_env = files(tmp_path, identity="IDENTITY_LOCAL_AUTH={broken\n")
    before = ((env / "identity.env").read_bytes(), auth_env.read_bytes())
    with pytest.raises(tool.ConfigurationError, match="not valid JSON"):
        tool.main(["--env-dir", str(env), "--auth-env", str(auth_env)])
    assert ((env / "identity.env").read_bytes(), auth_env.read_bytes()) == before


@pytest.mark.parametrize(
    "url",
    [
        "http://auth.example",
        "https://u:p@auth.example",
        "https://auth.example/?x=1",
        "ftp://localhost",
    ],
)
def test_an_unsafe_auth_app_address_is_refused(tmp_path: Path, url: str) -> None:
    env, auth_env = files(tmp_path, auth=f"NEXTAUTH_URL={url}\n")
    with pytest.raises(tool.ConfigurationError):
        tool.main(["--env-dir", str(env), "--auth-env", str(auth_env)])
    assert "AUTH_LOCAL" not in auth_env.read_text()


def test_no_secret_is_ever_printed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    env, auth_env = files(tmp_path)
    output = run(env, auth_env, capsys)
    auth = tool.parse(auth_env.read_text())
    assert (
        auth["AUTH_LOCAL_CLIENT_SECRET"] not in output
        and auth["AUTH_LOCAL_BFF_SECRET"] not in output
    )
    assert "IDENTITY_LOCAL_AUTH" in output  # the name, never the value


def test_the_settings_it_writes_are_what_identity_accepts_and_a_tampered_copy_is_not(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env, auth_env = files(tmp_path)
    run(env, auth_env, capsys)
    configuration = json.loads(
        tool.parse((env / "identity.env").read_text())["IDENTITY_LOCAL_AUTH"]
    )
    LocalAuthSettings.model_validate(configuration)
    configuration["bff_secret"] = "short"
    with pytest.raises(ValidationError):
        LocalAuthSettings.model_validate(configuration)
