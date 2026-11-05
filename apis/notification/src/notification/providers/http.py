from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlencode

import httpx

from notification.providers.base import SendCommand, SendResult


def _result(response: httpx.Response) -> SendResult:
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        return SendResult(
            "unknown", None, response.status_code, error_code="invalid_provider_response"
        )
    messages = data.get("messages")
    first = (
        messages[0]
        if isinstance(messages, list) and messages and isinstance(messages[0], dict)
        else {}
    )
    message_id = data.get("sid") or data.get("name") or first.get("id")
    error_data = data.get("error")
    error = (
        str(
            data.get("code")
            or (error_data.get("code") if isinstance(error_data, dict) else None)
            or ""
        )
        or None
    )
    message_id = message_id if isinstance(message_id, str) else None
    if 200 <= response.status_code < 300:
        outcome = "accepted" if isinstance(message_id, str) and message_id else "unknown"
    elif response.status_code == 429 or response.status_code >= 500:
        outcome = "retryable_failure"
    else:
        outcome = "permanent_failure"
    retry = response.headers.get("retry-after")
    return SendResult(
        outcome,
        message_id,
        response.status_code,
        error,
        min(int(retry), 86400)
        if retry and retry.isascii() and retry.isdigit() and len(retry) < 10
        else None,
        response.content,
    )


class TwilioSmsAdapter:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        account_sid: str,
        auth_token: str,
        callback_url: str | None = None,
    ) -> None:
        self.client, self.account_sid = client, account_sid
        self.callback_url = callback_url
        token = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}"}

    async def send(self, command: SendCommand) -> SendResult:
        response = await self.client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json",
            headers=self.headers,
            data={
                "To": command.destination,
                "From": command.sender,
                "Body": command.body,
                **(
                    {
                        "StatusCallback": self.callback_url
                        + ("&" if "?" in self.callback_url else "?")
                        + urlencode({"attempt_key": command.attempt_key})
                    }
                    if self.callback_url
                    else {}
                ),
            },
        )
        return _result(response)


class MetaWhatsAppAdapter:
    def __init__(
        self, client: httpx.AsyncClient, *, access_token: str, api_version: str = "v23.0"
    ) -> None:
        self.client, self.api_version = client, api_version
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def send(self, command: SendCommand) -> SendResult:
        if not command.provider_template_name or not command.template_language:
            raise ValueError("WhatsApp requires an approved provider template and language")
        template_obj: dict[str, Any] = {
            "name": command.provider_template_name,
            "language": {"code": command.template_language},
        }
        if command.template_components:
            template_obj["components"] = list(command.template_components)
        elif command.template_parameters:
            components = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": p} for p in command.template_parameters
                    ],
                }
            ]
            template_obj["components"] = components
        response = await self.client.post(
            f"https://graph.facebook.com/{self.api_version}/{command.sender}/messages",
            headers=self.headers,
            json={
                "messaging_product": "whatsapp",
                "to": command.destination,
                "type": "template",
                "biz_opaque_callback_data": command.attempt_key,
                "template": template_obj,
            },
        )
        return _result(response)


class FcmAdapter:
    def __init__(self, client: httpx.AsyncClient, *, project_id: str, access_token: str) -> None:
        self.client, self.project_id = client, project_id
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def send(self, command: SendCommand) -> SendResult:
        response = await self.client.post(
            f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send",
            headers=self.headers,
            json={
                "message": {
                    "token": command.destination,
                    "notification": {"title": command.subject or "", "body": command.body},
                }
            },
        )
        return _result(response)
