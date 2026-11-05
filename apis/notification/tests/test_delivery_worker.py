"""Credential-gated dispatch adapter selection."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from notification.providers import FcmAdapter, MetaWhatsAppAdapter, TwilioSmsAdapter
from notification.tasks.delivery_worker import adapter_for


@pytest.mark.parametrize(
    ("provider_key", "channel", "credential", "expected"),
    [
        ("twilio", "sms", '{"account_sid":"AC1","auth_token":"secret"}', TwilioSmsAdapter),
        ("meta", "whatsapp", '{"access_token":"secret"}', MetaWhatsAppAdapter),
        ("fcm", "push", '{"project_id":"project","access_token":"secret"}', FcmAdapter),
    ],
)
@pytest.mark.asyncio
async def test_adapter_uses_environment_credential(
    monkeypatch: pytest.MonkeyPatch,
    provider_key: str,
    channel: str,
    credential: str,
    expected: type,
) -> None:
    monkeypatch.setenv("NOTIFICATION_PROVIDER_TEST", credential)
    provider: Any = SimpleNamespace(
        provider_key=provider_key,
        channel=channel,
        credential_ref="env:NOTIFICATION_PROVIDER_TEST",
        region=None,
    )
    async with httpx.AsyncClient() as client:
        assert isinstance(adapter_for(provider, client), expected)


@pytest.mark.asyncio
async def test_adapter_rejects_missing_or_unsupported_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider: Any = SimpleNamespace(
        provider_key="twilio",
        channel="sms",
        credential_ref="env:NOTIFICATION_MISSING",
        region=None,
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="unavailable"):
            adapter_for(provider, client)
        provider.credential_ref = "file:/tmp/secret"
        with pytest.raises(ValueError, match="environment reference"):
            adapter_for(provider, client)
        monkeypatch.setenv("NOTIFICATION_PROVIDER_TEST", '{"account_sid":"AC1"}')
        provider.credential_ref = "env:NOTIFICATION_PROVIDER_TEST"
        with pytest.raises(KeyError, match="auth_token"):
            adapter_for(provider, client)
        provider.provider_key = "unknown"
        with pytest.raises(ValueError, match="unsupported"):
            adapter_for(provider, client)
