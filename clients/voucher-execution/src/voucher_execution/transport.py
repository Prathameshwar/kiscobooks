"""Signed request-bound transport with no retry that changes execution identity."""

import hashlib
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal

import httpx
from billing_platform.errors import AuthenticationRequiredError
from billing_platform.idempotency import canonical_json
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)

from voucher_execution.contracts import ExecutionCommand, ExecutionResult
from voucher_execution.invoice import InvoiceCalculationDetail, InvoicePreviewCommand

if TYPE_CHECKING:
    from voucher_execution.printing import PurchasePrintCommand, PurchasePrintFacts


def command_digest(command: ExecutionCommand) -> str:
    return hashlib.sha256(
        canonical_json(
            command.model_dump(mode="json", exclude={"request_hash", "purpose"})
        )
    ).hexdigest()


def headers(
    secret: bytes, key_id: str, operation: str, framed: bytes, *, response: bool = False
) -> dict[str, str]:
    stamp = int(time.time())
    key = ServiceKey(
        "accounting" if response else "vouchers",
        "vouchers" if response else "accounting",
        frozenset({operation}),
        secret,
    )
    return {
        "X-Execution-Key-Id": key_id,
        "X-Execution-Timestamp": str(stamp),
        "X-Execution-Signature": sign_service_body(
            key, key_id=key_id, operation=operation, timestamp=stamp, body=framed
        ),
    }


def verify(
    secret: bytes,
    key_id: str,
    operation: str,
    framed: bytes,
    values: Mapping[str, str],
    *,
    response: bool = False,
) -> None:
    key = ServiceKey(
        "accounting" if response else "vouchers",
        "vouchers" if response else "accounting",
        frozenset({operation}),
        secret,
    )
    verify_service_body(
        {key_id: key},
        key_id=values.get("x-execution-key-id", ""),
        issuer=key.issuer,
        audience=key.audience,
        operation=operation,
        timestamp=values.get("x-execution-timestamp", ""),
        signature=values.get("x-execution-signature", ""),
        body=framed,
        now=int(time.time()),
    )


def validate_origin(origin: str) -> str:
    url = httpx.URL(origin)
    if (
        not url.host
        or (
            url.scheme != "https"
            and not (url.scheme == "http" and url.host in {"127.0.0.1", "::1"})
        )
        or url.path not in {"", "/"}
        or url.userinfo
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "execution transport requires an HTTPS origin or literal loopback"
        )
    return origin.rstrip("/")


class ExecutionClient:
    def __init__(
        self, client: httpx.AsyncClient, origin: str, key_id: str, secret: bytes
    ) -> None:
        origin = validate_origin(origin)
        self.client, self.origin, self.key_id, self.secret = (
            client,
            origin.rstrip("/"),
            key_id,
            secret,
        )

    async def send(
        self,
        command: ExecutionCommand,
        *,
        purpose: Literal["POST", "CANCEL", "REVERSE"] | None = None,
    ) -> ExecutionResult:
        payload = (
            command
            if purpose is None
            else command.model_copy(update={"purpose": purpose})
        )
        path = "/internal/v1/voucher-executions"
        body = canonical_json(payload.model_dump(mode="json"))
        return await self._request("POST", path, "voucher.execution.command", body)

    async def status(self, command: ExecutionCommand) -> ExecutionResult:
        path = (
            f"/internal/v1/voucher-executions/{command.tenant_id}/"
            f"{command.company_id}/{command.execution_id}"
        )
        return await self._request("GET", path, "voucher.execution.status", b"")

    async def preview(self, command: InvoicePreviewCommand) -> InvoiceCalculationDetail:
        raw = await self._exchange(
            "POST",
            "/internal/v1/voucher-invoice-previews",
            "voucher.invoice.preview",
            canonical_json(command.model_dump(mode="json"), maximum_bytes=1048576),
        )
        return InvoiceCalculationDetail.model_validate_json(raw)

    async def purchase_print(
        self, command: "PurchasePrintCommand"
    ) -> "PurchasePrintFacts":
        from voucher_execution.printing import PurchasePrintFacts

        raw = await self._exchange(
            "POST",
            "/internal/v1/purchase-print-facts",
            "voucher.purchase.print",
            canonical_json(command.model_dump(mode="json"), maximum_bytes=1048576),
        )
        return PurchasePrintFacts.model_validate_json(raw)

    async def _request(
        self, method: str, path: str, operation: str, body: bytes
    ) -> ExecutionResult:
        raw = await self._exchange(method, path, operation, body)
        return ExecutionResult.model_validate_json(raw)

    async def _exchange(
        self, method: str, path: str, operation: str, body: bytes
    ) -> bytes:
        framed = service_request_bytes(method=method, path=path, query="", body=body)
        result = await self.client.request(
            method,
            self.origin + path,
            content=body,
            headers=headers(self.secret, self.key_id, operation, framed)
            | {"Content-Type": "application/json"},
            follow_redirects=False,
        )
        result.raise_for_status()
        if len(result.content) > 1048576:
            raise AuthenticationRequiredError(
                "execution response exceeds protocol bound"
            )
        verify(
            self.secret,
            self.key_id,
            operation + ".response",
            service_response_bytes(request_bytes=framed, response_body=result.content),
            result.headers,
            response=True,
        )
        return result.content


class StockExecutionClient(ExecutionClient):
    """Dedicated delegated stock channel; ordinary financial scopes remain unchanged."""

    async def send(
        self,
        command: ExecutionCommand,
        *,
        purpose: Literal["POST", "CANCEL", "REVERSE"] | None = None,
    ) -> ExecutionResult:
        if command.source_payload.get("stock") is None:
            raise ValueError("the stock channel accepts typed physical executions only")
        payload = (
            command
            if purpose is None
            else command.model_copy(update={"purpose": purpose})
        )
        return await self._request(
            "POST",
            "/internal/v1/stock-voucher-executions",
            "stock.execution.command",
            canonical_json(payload.model_dump(mode="json")),
        )

    async def status(self, command: ExecutionCommand) -> ExecutionResult:
        if command.source_payload.get("stock") is None:
            raise ValueError(
                "stock reconciliation requires its exact accepted stock command"
            )
        return await self._request(
            "POST",
            "/internal/v1/stock-voucher-executions/status",
            "stock.execution.status",
            canonical_json(command.model_dump(mode="json")),
        )
