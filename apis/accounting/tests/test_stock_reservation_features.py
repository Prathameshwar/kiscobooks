"""Stock invoices reserve every feature required by their prepared journal."""

import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from identity_posting import ReservationRejectedError
from identity_posting.stock import (
    StockAuthority,
    StockPostingClient,
    StockReservationIntent,
    StockReservationSource,
    StockTerminalRequest,
)

from accounting.tasks.posting_delivery import StockIntentPayload, deliver_stock_terminal
from accounting.tasks.stock_execution import reservation
from tests.test_voucher_execution import command


def test_stock_reservation_includes_journal_features() -> None:
    accepted = command()
    intent = SimpleNamespace(
        command=accepted.model_dump(mode="json"),
        company_id=accepted.company_id,
        journal_id=accepted.operation_id,
        id=accepted.execution_id,
        execution_id=accepted.execution_id,
    )
    plan = SimpleNamespace(effects={"features": ["inventory"]})
    journal = SimpleNamespace(features=["credit_limits", "inventory"])

    result = reservation(intent, plan, journal)

    assert result["features"] == ["credit_limits", "inventory"]
    assert result["operation_id"] == str(accepted.operation_id)


class TerminalClient:
    def __init__(self, first_status: int | None = None) -> None:
        self.first_status = first_status
        self.calls: list[StockTerminalRequest] = []

    async def terminal(
        self,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        operation_id: uuid.UUID,
        outcome: str,
        body: StockTerminalRequest,
    ) -> None:
        self.calls.append(body)
        if len(self.calls) == 1 and self.first_status is not None:
            raise ReservationRejectedError(self.first_status)


def terminal_evidence() -> tuple[uuid.UUID, StockIntentPayload, StockReservationIntent]:
    tenant, company, operation, execution, actor = (uuid7() for _ in range(5))
    payload = StockIntentPayload(
        company_id=company,
        operation_id=operation,
        actor_user_id=actor,
        configuration_hash="a" * 64,
        features=["credit_limits", "inventory"],
        posted_at=None,
        stock_execution_id=execution,
    )
    intent = StockReservationIntent(
        operation_id=operation,
        actor_user_id=actor,
        configuration_hash=payload.configuration_hash,
        features=("credit_limits", "inventory"),
        source=StockReservationSource(execution_id=execution, command_hash="b" * 64, action="POST"),
        authority=StockAuthority(
            actor_context="actor",
            actor_signature="c" * 64,
            company_context="company",
            company_signature="d" * 64,
        ),
    )
    return tenant, payload, intent


async def test_existing_stock_abort_uses_the_retained_reservation() -> None:
    tenant, payload, intent = terminal_evidence()
    client = TerminalClient()

    await deliver_stock_terminal(
        cast(StockPostingClient, client), tenant, payload, "aborted", intent
    )

    assert len(client.calls) == 1 and client.calls[0].intent is None


async def test_stock_abort_without_reservation_retains_exact_intent() -> None:
    tenant, payload, intent = terminal_evidence()
    client = TerminalClient(404)

    await deliver_stock_terminal(
        cast(StockPostingClient, client), tenant, payload, "aborted", intent
    )

    assert [body.intent for body in client.calls] == [None, intent]


async def test_stock_abort_does_not_retry_a_conflicting_reservation() -> None:
    tenant, payload, intent = terminal_evidence()
    client = TerminalClient(409)

    with pytest.raises(ReservationRejectedError) as error:
        await deliver_stock_terminal(
            cast(StockPostingClient, client), tenant, payload, "aborted", intent
        )

    assert error.value.status_code == 409 and len(client.calls) == 1


async def test_stock_confirmation_does_not_offer_an_abort_intent() -> None:
    tenant, payload, intent = terminal_evidence()
    client = TerminalClient()

    await deliver_stock_terminal(
        cast(StockPostingClient, client),
        tenant,
        payload.model_copy(update={"posted_at": utcnow()}),
        "confirmed",
        intent,
    )

    assert len(client.calls) == 1 and client.calls[0].intent is None
