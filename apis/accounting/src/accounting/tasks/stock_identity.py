"""Bind the accepted stock command to Identity's separate delegated first-use channel."""

import uuid

import httpx
from billing_platform.errors import ConflictError
from identity_posting import Receipt
from identity_posting.stock import (
    StockAuthority,
    StockPostingClient,
    StockReservationIntent,
    StockReservationSource,
)
from voucher_execution import ExecutionCommand
from voucher_execution.transport import command_digest

from accounting.config import Settings


def reservation_intent(
    command: ExecutionCommand,
    *,
    operation_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    configuration_hash: str,
    features: list[str],
) -> StockReservationIntent:
    if (
        command.purpose not in {"POST", "REVERSE"}
        or command.authority is None
        or command.source_payload.get("stock") is None
        or command_digest(command) != command.request_hash
        or (command.actor_user_id, command.company_configuration_hash)
        != (actor_user_id, configuration_hash)
    ):
        raise ConflictError("stock reservation differs from its accepted command")
    return StockReservationIntent(
        operation_id=operation_id,
        actor_user_id=actor_user_id,
        configuration_hash=configuration_hash,
        features=tuple(sorted(set(features))),
        source=StockReservationSource.model_validate(
            {
                "execution_id": command.execution_id,
                "command_hash": command.request_hash,
                "action": command.purpose,
            }
        ),
        authority=StockAuthority.model_validate(command.authority.model_dump()),
    )


class BoundStockAuthority:
    def __init__(self, client: StockPostingClient, command: ExecutionCommand):
        self.client, self.command = client, command

    async def reserve(
        self,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        operation_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        configuration_hash: str,
        features: list[str],
    ) -> Receipt:
        if (tenant_id, company_id) != (self.command.tenant_id, self.command.company_id):
            raise ConflictError("stock first-use company differs from the accepted command")
        return await self.client.reserve(
            tenant_id,
            company_id,
            reservation_intent(
                self.command,
                operation_id=operation_id,
                actor_user_id=actor_user_id,
                configuration_hash=configuration_hash,
                features=features,
            ),
        )


class StockIdentityConnection:
    def __init__(self, client: StockPostingClient):
        self.client = client

    def for_command(self, command: ExecutionCommand) -> BoundStockAuthority:
        return BoundStockAuthority(self.client, command)


def connection(settings: Settings) -> tuple[httpx.AsyncClient, StockIdentityConnection] | None:
    if settings.stock_identity_url is None:
        return None
    assert settings.stock_identity_request_secret is not None
    assert settings.stock_identity_response_secret is not None
    http = httpx.AsyncClient(base_url=settings.stock_identity_url, follow_redirects=False)
    client = StockPostingClient(
        http,
        request_secret=settings.stock_identity_request_secret.get_secret_value().encode(),
        response_secret=settings.stock_identity_response_secret.get_secret_value().encode(),
    )
    return http, StockIdentityConnection(client)
