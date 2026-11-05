from __future__ import annotations

from typing import Any, Protocol

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from notification.providers.base import SendCommand, SendResult


class SesClient(Protocol):
    async def send_email(self, **kwargs: Any) -> dict[str, Any]: ...


class SesAdapter:
    """SES v2 adapter over an injected workload-identity-aware async client."""

    def __init__(self, client: SesClient) -> None:
        self.client = client

    async def send(self, command: SendCommand) -> SendResult:
        body_dict: dict[str, Any] = {"Text": {"Data": command.body}}
        if command.body_html:
            body_dict["Html"] = {"Data": command.body_html}
        try:
            response = await self.client.send_email(
                FromEmailAddress=command.sender,
                Destination={"ToAddresses": [command.destination]},
                Content={
                    "Simple": {
                        "Subject": {"Data": command.subject or ""},
                        "Body": body_dict,
                    }
                },
                EmailTags=[
                    {"Name": "attempt_key", "Value": command.attempt_key.replace(":", "_")[:256]}
                ],
            )
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            code = exc.response.get("Error", {}).get("Code")
            retryable = status == 429 or (isinstance(status, int) and status >= 500)
            outcome = "retryable_failure" if retryable else "permanent_failure"
            return SendResult(outcome, None, status, code)
        message_id = response.get("MessageId")
        if not isinstance(message_id, str) or not message_id:
            return SendResult("unknown", None, 200, error_code="invalid_provider_response")
        return SendResult("accepted", message_id, 200)
