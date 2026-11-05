"""Recoverable quote decisions; existing native quote rules still own mutations."""

import uuid
from typing import Any, Literal

from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.schemas.exchange_rates import RateCandidate, RateDecision
from accounting.tasks import exchange_rates
from accounting.tasks.commands import require_metadata, setup_lock


async def command(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    body: RateCandidate | RateDecision,
    key: str,
    action: Literal["create", "approve", "withdraw"],
    quote_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        exchange_rates.authorize(current, True)
        await require_metadata(db, current)
        if isinstance(body, RateCandidate):
            exchange_rates.validate_scope(current, body)
        target = uuid.UUID(receipt["id"]) if receipt else quote_id
        if target:
            await exchange_rates.get(db, current, target)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, current)
        if isinstance(body, RateCandidate):
            row = await exchange_rates.candidate(db, current, body)
        else:
            assert quote_id is not None
            row = await exchange_rates.decide(db, current, quote_id, body, action)
        return CommandReceipt(201 if action == "create" else 200, {"id": str(row.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        return exchange_rates.view(await exchange_rates.get(db, current, uuid.UUID(receipt["id"])))

    return await execute_idempotent(
        factory,
        CommandIdentity(
            current.actor.tenant_id,
            current.context.company_id,
            current.actor.user_id,
            "accounting.exchange_rate_quote." + action,
            key,
            {"body": body.model_dump(mode="json"), "id": str(quote_id) if quote_id else None},
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )
