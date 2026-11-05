from __future__ import annotations

from typing import Any

import httpx
import pytest

from notification.providers import FcmAdapter, MetaWhatsAppAdapter, SendCommand, TwilioSmsAdapter


def command(**changes: object) -> SendCommand:
    values: dict[str, object] = {
        "destination": "+15551234567",
        "sender": "sender",
        "body": "hello",
        "subject": "subject",
        "attempt_key": "attempt-1",
        "provider_template_name": "approved_template",
        "template_language": "en",
        "template_parameters": ("Ada",),
    }
    values.update(changes)
    return SendCommand(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["twilio", "meta", "fcm"])
async def test_http_adapters_classify_provider_results(kind: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"sid": "SM1", "messages": [{"id": "WA1"}], "name": "projects/p/messages/1"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapters: dict[str, Any] = {
            "twilio": TwilioSmsAdapter(client, account_sid="AC1", auth_token="token"),
            "meta": MetaWhatsAppAdapter(client, access_token="token"),
            "fcm": FcmAdapter(client, project_id="p", access_token="token"),
        }
        assert (await adapters[kind].send(command())).outcome == "accepted"


@pytest.mark.asyncio
async def test_ses_classifies_known_provider_rejections() -> None:
    from botocore.exceptions import ClientError  # type: ignore[import-untyped]

    from notification.providers import SesAdapter

    class RejectingSes:
        async def send_email(self, **kwargs: Any) -> dict[str, Any]:
            raise ClientError(
                {
                    "Error": {"Code": "BadRequestException", "Message": "invalid"},
                    "ResponseMetadata": {"HTTPStatusCode": 400},
                },
                "SendEmail",
            )

    result = await SesAdapter(RejectingSes()).send(command())
    assert result.outcome == "permanent_failure"
    assert result.error_code == "BadRequestException"


async def test_ses_validation_requires_the_explicit_dispatch_region() -> None:
    from types import SimpleNamespace

    from notification.providers.inspection import inspect_provider

    account: Any = SimpleNamespace(provider_key="ses", region=None)
    async with httpx.AsyncClient() as client:
        result = await inspect_provider(account, {}, "provider.validate", client=client)
    assert not result.success and result.reason == "provider_region_required"


@pytest.mark.parametrize(
    "remote_text,expected", [("Hello {{1}}", "approved"), ("Other {{1}}", "rejected")]
)
async def test_meta_inspection_checks_approved_remote_content(remote_text, expected):
    from notification.models import ProviderAccount, ProviderTemplateBinding, TemplateVersion
    from notification.providers.inspection import inspect_provider

    async def handler(request):
        assert request.url.path == "/v99.0/business/message_templates"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "remote",
                        "name": "welcome",
                        "language": "en",
                        "status": "APPROVED",
                        "components": [{"type": "BODY", "text": remote_text}],
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await inspect_provider(
            ProviderAccount(provider_key="meta"),
            {"api_version": "v99.0", "access_token": "test", "business_account_id": "business"},
            "binding.sync",
            binding=ProviderTemplateBinding(
                external_template_id="remote", external_name="welcome", external_language="en"
            ),
            version=TemplateVersion(
                body_text="Hello {{name}}", channel_payload={"template_parameters": ["name"]}
            ),
            client=client,
        )
    assert result.success and result.approval_status == expected
