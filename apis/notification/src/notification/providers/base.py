from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class SendCommand:
    destination: str
    sender: str
    body: str
    subject: str | None
    attempt_key: str
    body_html: str | None = None
    provider_template_name: str | None = None
    template_language: str | None = None
    template_parameters: tuple[str, ...] = ()
    template_components: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class SendResult:
    outcome: str
    provider_message_id: str | None
    http_status: int | None = None
    error_code: str | None = None
    retry_after_seconds: int | None = None
    response_body: bytes = b""


class ProviderAdapter(Protocol):
    async def send(self, command: SendCommand) -> SendResult: ...
