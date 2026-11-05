"""Deployment boundaries: authenticated gateway context and a scoped audit publisher."""

import asyncio
import importlib
import os
import re
import runpy
import secrets
import shutil
import subprocess
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest
from billing_platform.publisher import PublisherConfig
from pydantic import SecretStr


def test_gateway_authenticates_accounting_and_replaces_client_context() -> None:
    config = (Path(__file__).resolve().parents[3] / "start/win/conf/bill.conf").read_text()
    match = re.search(r"location /accounting/ \{([^}]+)\}", config)
    assert match is not None
    location = match.group(1)
    assert "auth_request /_accounting_authorize;" in location
    for name in ("Actor-Context", "Actor-Signature", "Company-Context", "Company-Signature"):
        assert f"proxy_set_header X-{name} $accounting_" in location
    assert "location = /_accounting_authorize" in config
    match = re.search(r"location = /_accounting_authorize \{([^}]+)\}", config)
    assert match is not None
    auth = match.group(1)
    assert "internal;" in auth and "proxy_pass_request_body off;" in auth
    assert "proxy_set_header X-Original-URI $request_uri;" in auth
    assert 'proxy_set_header X-Actor-Context "";' in auth
    for status in (401, 403):
        assert f'return {status} \'{{"error":' in config
    assert "error_page 500 502 503 504 = @accounting_unavailable;" in location


async def test_accounting_audit_publisher_uses_only_its_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("accounting.tasks.audit_publisher")
    captured = []

    async def run(config: PublisherConfig) -> None:
        captured.append(config)

    monkeypatch.setattr(module, "run_publisher", run)
    settings = module.AuditPublisherSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        audit_broker_url=SecretStr("amqp://ephemeral.invalid"),
        audit_broker_user="accounting_audit",
        audit_event_secret=SecretStr(secrets.token_hex(32)),
    )
    await module.run(settings)
    config = captured[0]
    assert config.key.issuer == "accounting" and config.key.audience == "audit"
    assert "accounting.party.create" in config.key.operations
    assert "accounting.account_posting_mapping.draft_publish" in config.key.operations
    assert all(event.startswith("accounting.") for event in config.key.operations)
    assert settings.audit_event_secret.get_secret_value() not in repr(config)


def test_publisher_entrypoint_reads_environment_and_rejects_unknown_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from accounting.events.audit_contract import audit_event
    from accounting.tasks import audit_publisher

    values: dict[str, Any] = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "AUDIT_BROKER_URL": "amqp://ephemeral.invalid",
        "AUDIT_BROKER_USER": "accounting_audit",
        "AUDIT_EVENT_SECRET": secrets.token_hex(32),
    }
    for key, value in values.items():
        monkeypatch.setenv("ACCOUNTING_" + key, value)
    monkeypatch.setattr(sys, "argv", ["accounting-audit-publisher"])
    invoked = []

    def run(coroutine: Coroutine[Any, Any, None]) -> None:
        invoked.append(True)
        coroutine.close()

    monkeypatch.setattr(asyncio, "run", run)
    audit_publisher.main()
    runpy.run_path(audit_publisher.__file__, run_name="__main__")
    assert len(invoked) == 2
    with pytest.raises(ValueError, match="unregistered"):
        audit_event("party", "unregistered")


def test_identity_field_contract_is_current() -> None:
    from tools.export_field_contract import TARGET, document

    assert TARGET.read_text(encoding="utf-8") == document()


def test_generated_service_environments_share_the_gateway_signer(tmp_path: Path) -> None:
    powershell = shutil.which("powershell")
    if powershell is None:
        pytest.skip("Windows environment generator requires PowerShell")
    root = Path(__file__).resolve().parents[3]
    script = """
        . ./start/win/lib/_common.ps1
        . ./start/win/lib/write-envs.ps1
        $Global:BILL_ENV_DIR = $env:ACCOUNTING_ENV_TEST_DIR
        Invoke-BillWriteEnvs -Config (Get-BillConfig)
    """
    result = subprocess.run(  # noqa: S603 -- fixed repository script, isolated temporary output.
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=root,
        env=dict(os.environ, ACCOUNTING_ENV_TEST_DIR=str(tmp_path)),
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0
    keys: list[str] = []
    for path in tmp_path.glob("*.env"):
        keys.extend(
            line.partition("=")[2]
            for line in path.read_text().splitlines()
            if "ACTOR_SIGNING_SECRET=" in line
        )
    if len(set(keys)) != 1:
        raise AssertionError("generated services cannot verify the gateway's signing key")
    # Re-running alignment must preserve private settings, including UTF-8 text,
    # and remove a duplicate stale verification key without rotating encryption.
    accounting_env = tmp_path / "accounting.env"
    original = accounting_env.read_text(encoding="utf-8")
    preserved = original + "# Private deployment: \u20b9\nACCOUNTING_DATABASE_TAG=\u00e9\n"
    accounting_env.write_text(
        preserved + "ACCOUNTING_ACTOR_SIGNING_SECRET=" + secrets.token_hex(32) + "\n",
        encoding="utf-8",
    )
    subprocess.run(  # noqa: S603 -- same fixed script and isolated output directory.
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=root,
        env=dict(os.environ, ACCOUNTING_ENV_TEST_DIR=str(tmp_path)),
        capture_output=True,
        text=True,
        check=True,
    )
    updated = accounting_env.read_text(encoding="utf-8")
    assert updated.count("ACCOUNTING_ACTOR_SIGNING_SECRET=") == 1
    assert set(preserved.splitlines()) == set(updated.splitlines())
