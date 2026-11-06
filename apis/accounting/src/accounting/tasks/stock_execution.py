"""Stock uses the common voucher intent, Identity reservation and owner receipt.

Catalog and Identity calls occur between local transactions. Prepared evidence
does not move stock; the final company transaction composes physical effects and
the native journal, or rolls both back. A retained owner receipt wins every retry.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import uuid
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.diagnostics import log_failure
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from identity_posting import Receipt, ReservationAuthority, ReservationError
from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from voucher_execution import EffectReference, ExecutionCommand, ExecutionResult
from voucher_execution.money import MoneyInput
from voucher_execution.stock_facts import StockFenceFacts, StockFenceRequest

from accounting.api.auth import Access
from accounting.models.ledger import Journal
from accounting.models.stock import StockExecutionPlan
from accounting.models.voucher_execution import VoucherSourceGuard
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.schemas.masters import ExpectedVersion
from accounting.tasks.commands import setup_lock
from accounting.tasks.journal_drafts import create_in_transaction, lines
from accounting.tasks.journal_posting import (
    PostingDependencyError,
    commit_post,
    prepare_in_transaction,
)
from accounting.tasks.stock_effects import StockEffects, apply, captured, source_scope
from accounting.tasks.stock_quote import simulate
from accounting.tasks.stock_source_client import StockSourceClient, StockSourceUnavailableError
from accounting.tasks.stock_source_guard import SOURCE_DEADLINE
from accounting.tasks.voucher_execution import execute
from accounting.tasks.voucher_money_effects import audit, draft, values
from accounting.tasks.voucher_money_execution import abandon as abandon_money
from accounting.tasks.voucher_money_execution import authority, existing


def source_request(command: ExecutionCommand) -> StockFenceRequest:
    body, _ = captured(command)
    if command.authority is None or command.stock_date is None:
        raise AuthenticationRequiredError("stock requires exact delegated company authority")
    return StockFenceRequest(
        action="REVERSE" if command.purpose == "REVERSE" else "POST",
        tenant_id=command.tenant_id,
        company_id=command.company_id,
        execution_id=command.execution_id,
        actor_user_id=command.actor_user_id,
        authority=command.authority,
        authority_expires_at=command.authority_expires_at,
        stock_date=command.stock_date,
        content_hash=command.content_hash,
        # A goods Purchase bill is taxed from each item's published purchase GST bundle.
        include_purchase_tax=body.action == "PURCHASE_INVOICE" and command.purpose == "POST",
        item_ids=tuple(sorted({line.item_id for line in body.lines})),
        quantity_unit_revision_ids=tuple(
            sorted(
                {
                    line.quantity_entry.unit_revision_id
                    for line in body.lines
                    if line.quantity_entry and command.purpose == "POST"
                }
            )
        ),
        opening_unit_revision_ids=tuple(
            sorted(
                {
                    line.opening.unit_revision_id
                    for line in body.lines
                    if line.opening and command.purpose == "POST"
                }
            )
        ),
        warehouse_ids=tuple(
            sorted(
                {
                    identity
                    for line in body.lines
                    for identity in (
                        line.warehouse_id,
                        line.destination_warehouse_id,
                    )
                    if identity is not None
                }
            )
        ),
        bin_ids=tuple(
            sorted(
                {
                    identity
                    for line in body.lines
                    for identity in (
                        line.bin_id,
                        line.destination_bin_id,
                    )
                    if identity is not None
                }
            )
        ),
    )


async def plan_for(db: AsyncSession, intent: VoucherMoneyIntent) -> StockExecutionPlan:
    row = await db.scalar(
        select(StockExecutionPlan).where(
            StockExecutionPlan.company_id == intent.company_id,
            StockExecutionPlan.intent_id == intent.id,
        )
    )
    if row is None or row.execution_id != intent.execution_id:
        raise ConflictError("native stock execution plan is unavailable")
    return row


def reservation(
    intent: VoucherMoneyIntent,
    plan: StockExecutionPlan,
    journal: Journal | None = None,
) -> dict[str, Any]:
    command = ExecutionCommand.model_validate(intent.command)
    features = set(plan.effects["features"])
    if journal is not None:
        features.update(journal.features)
    return {
        "company_id": str(intent.company_id),
        "operation_id": str(intent.journal_id or intent.id),
        "actor_user_id": str(command.actor_user_id),
        "configuration_hash": command.company_configuration_hash,
        "features": sorted(features),
        "posted_at": None,
        "stock_execution_id": str(intent.execution_id),
        **({"reference_kind": "STOCK"} if intent.journal_id is None else {}),
    }


async def new_intent(
    db: AsyncSession,
    current: Access,
    command: ExecutionCommand,
    identity: uuid.UUID,
    journal_id: uuid.UUID | None,
) -> VoucherMoneyIntent:
    row = VoucherMoneyIntent(
        **(values(current) | {"id": identity}),
        execution_id=command.execution_id,
        voucher_id=command.voucher_id,
        journal_id=journal_id,
        request_hash=command.request_hash,
        kind=command.kind,
        posting_date=command.posting_date,
        status="PREPARED",
        command=command.model_dump(mode="json"),
    )
    db.add(row)
    await db.flush()
    return row


async def prepare(
    db: AsyncSession, current: Access, command: ExecutionCommand, facts: StockFenceFacts
) -> VoucherMoneyIntent:
    await setup_lock(db, current)
    previous = await db.scalar(
        select(VoucherMoneyIntent)
        .where(
            VoucherMoneyIntent.company_id == command.company_id,
            VoucherMoneyIntent.execution_id == command.execution_id,
        )
        .with_for_update()
    )
    if previous:
        if previous.status != "PREPARED" or previous.request_hash != command.request_hash:
            raise ConflictError("stock posting intent differs")
        plan = await plan_for(db, previous)
        if plan.source_fence_id != facts.fence_id or plan.source_fence_expires_at <= utcnow():
            raise ConflictError("prepared stock source lease has expired; reconcile the execution")
        return previous
    pending = await db.scalar(
        select(VoucherMoneyIntent.id)
        .where(
            VoucherMoneyIntent.company_id == command.company_id,
            VoucherMoneyIntent.voucher_id == command.voucher_id,
            VoucherMoneyIntent.status.in_(("PREPARED", "COMMITTED")),
            VoucherMoneyIntent.execution_id != command.reversal_of_execution_id
            if command.reversal_of_execution_id
            else true(),
        )
        .limit(1)
    )
    source = await db.scalar(
        select(VoucherSourceGuard).where(
            VoucherSourceGuard.company_id == command.company_id,
            VoucherSourceGuard.voucher_id == command.voucher_id,
        )
    )
    if pending or (command.purpose == "POST" and source and source.committed_execution_id):
        raise ConflictError("voucher already has a pending or committed source execution")
    identity = uuid7()

    async def quote() -> StockEffects:
        temporary = await new_intent(db, current, command, identity, None)
        return await apply(db, current, command, temporary, facts)

    proposed = await simulate(db, quote)
    journal = None
    if command.purpose == "REVERSE":
        from accounting.tasks.voucher_money_reversal import prepare as prepare_reversal

        journal = await prepare_reversal(db, current, command)
    elif proposed.money is not None:
        journal = await create_in_transaction(
            db,
            current,
            draft(command, proposed.money),
            kind="VOUCHER",
            source_system="vouchers",
            source_type=command.kind.lower(),
            source_id=str(command.execution_id),
        )
    if (journal is not None) != (proposed.money is not None):
        raise ConflictError("physical stock valuation differs from its prepared journal")
    intent = await new_intent(db, current, command, identity, journal.id if journal else None)
    db.add(
        StockExecutionPlan(
            **values(current),
            intent_id=intent.id,
            execution_id=command.execution_id,
            source_fence_id=facts.fence_id,
            source_fence_expires_at=facts.expires_at,
            semantic_hash=proposed.semantic_hash,
            source_facts=facts.model_dump(mode="json"),
            effects={
                "semantic": proposed.semantic,
                "money": proposed.money.model_dump(mode="json") if proposed.money else None,
                "features": sorted(proposed.features),
            },
        )
    )
    audit(db, current, intent.id, "voucher_money_intent", "prepare")
    await db.flush()
    if command.purpose == "POST" and command.source_payload.get("invoice") is not None:
        # B24: the bill's invoice facts (calculation, supplies, GST) are retained with its
        # intent, as for any invoice, so its payable bill and returns read the same record.
        from accounting.tasks.invoice_execution import resolve_goods
        from accounting.tasks.invoice_facts import store

        request, calculation, financial, _ = await resolve_goods(db, current, command, facts)
        if proposed.money != financial:
            raise ConflictError("the bill's distribution differs from its stock valuation")
        await store(db, current, intent, request, calculation, financial)
    if journal:
        db.info["voucher_money_execution"] = command.execution_id
        await prepare_in_transaction(
            db, current, journal.id, ExpectedVersion(expected_version=journal.row_version)
        )
    return intent


async def validate_journal(
    db: AsyncSession, current: Access, intent: VoucherMoneyIntent, journal: Journal
) -> None:
    if db.info.get("voucher_money_execution") != intent.execution_id or intent.status != "PREPARED":
        raise ConflictError("stock journal requires its common source execution")
    command = ExecutionCommand.model_validate(intent.command)
    plan = await plan_for(db, intent)
    facts = StockFenceFacts.model_validate(plan.source_facts)
    body, _ = captured(command)
    source_scope(current, command, body, facts)
    expected_money = MoneyInput.model_validate(plan.effects.get("money"))
    stored_lines = await lines(db, intent.company_id, journal.id)
    if len(stored_lines) != len(expected_money.accounts):
        raise ConflictError("stock journal lines differ from the exact prepared distribution")
    for expected, row in zip(expected_money.accounts, stored_lines, strict=True):
        if (
            expected.account_id,
            expected.side,
            expected.currency,
            expected.amount,
            expected.exchange_rate,
        ) != (
            row.account_id,
            row.side,
            row.currency,
            row.amount,
            row.exchange_rate,
        ):
            raise ConflictError("stock journal differs from its exact prepared valuation")


async def abandon(db: AsyncSession, command: ExecutionCommand, intent: VoucherMoneyIntent) -> None:
    await abandon_money(db, command, intent)
    if intent.journal_id is None:
        plan = await plan_for(db, intent)
        emit(
            db,
            aggregate_type="accounting.voucher_money_intent",
            aggregate_id=intent.id,
            tenant_id=intent.tenant_id,
            event_type="accounting.stock_posting.abort",
            payload=reservation(intent, plan),
        )


async def zero_commit(
    db: AsyncSession,
    current: Access,
    intent: VoucherMoneyIntent,
    plan: StockExecutionPlan,
    receipt: Receipt,
) -> None:
    payload = reservation(intent, plan)
    if (
        receipt.operation_id != intent.id
        or receipt.status != "pending"
        or receipt.configuration_hash != payload["configuration_hash"]
        or not set(payload["features"]) <= set(receipt.features)
    ):
        raise ConflictError("Identity reservation differs from the zero-GL stock intent")
    from accounting.tasks.financial_commands import mark_first_posted
    from accounting.tasks.fiscal import setup

    posted_at = utcnow()
    await mark_first_posted(db, current, await setup(db, current), posted_at)
    payload["posted_at"] = posted_at.isoformat()
    emit(
        db,
        aggregate_type="accounting.voucher_money_intent",
        aggregate_id=intent.id,
        tenant_id=intent.tenant_id,
        event_type="accounting.stock_posting.confirm",
        payload=payload,
    )


async def _dispatch(
    factory: async_sessionmaker[AsyncSession],
    command: ExecutionCommand,
    *,
    secret: bytes,
    client: ReservationAuthority | None,
    source_client: StockSourceClient | None,
    enabled: bool,
) -> tuple[ExecutionResult, StockFenceFacts | None]:
    with tenant_scope(command.tenant_id):
        async with factory() as db:
            terminal = await existing(db, command)
            if terminal:
                return terminal, None
        stale = command.authority_expires_at <= utcnow()
        current = None
        if not stale and command.purpose != "CANCEL":
            try:
                current = authority(command, secret)
            except AuthenticationRequiredError:
                stale = True
        if command.purpose == "CANCEL" or stale or not enabled:
            async with factory.begin() as db:
                result = await execute(db, command, stale_authority=stale)
                intent = await db.scalar(
                    select(VoucherMoneyIntent)
                    .where(
                        VoucherMoneyIntent.company_id == command.company_id,
                        VoucherMoneyIntent.execution_id == command.execution_id,
                    )
                    .with_for_update()
                )
                if intent and intent.status == "PREPARED" and result.outcome != "COMMITTED":
                    await abandon(db, command, intent)
                retained_facts = (
                    StockFenceFacts.model_validate((await plan_for(db, intent)).source_facts)
                    if intent
                    else None
                )
                return result, retained_facts
        assert current is not None
        if source_client is None or client is None:
            raise PostingDependencyError(
                "stock source and Identity posting authorization must be configured"
            )
        facts = None
        async with factory() as db:
            prior = await db.scalar(
                select(VoucherMoneyIntent).where(
                    VoucherMoneyIntent.company_id == command.company_id,
                    VoucherMoneyIntent.execution_id == command.execution_id,
                )
            )
            if prior:
                if prior.request_hash != command.request_hash or prior.status != "PREPARED":
                    raise ConflictError("stock intent identity differs")
                facts = StockFenceFacts.model_validate((await plan_for(db, prior)).source_facts)
        if facts is None:
            facts = await source_client.acquire(source_request(command))
        if facts.expires_at <= utcnow() + dt.timedelta(seconds=15):
            raise ConflictError(
                "stock source lease expired; reconcile this execution before another attempt"
            )
        async with asyncio.timeout(10), factory.begin() as db:
            intent = await prepare(db, current, command, facts)
            plan = await plan_for(db, intent)
            journal = await db.get(Journal, intent.journal_id) if intent.journal_id else None
            payload = reservation(intent, plan, journal)
            intent_id, journal_id = intent.id, intent.journal_id
        try:
            receipt = await client.reserve(
                command.tenant_id,
                command.company_id,
                operation_id=uuid.UUID(payload["operation_id"]),
                actor_user_id=command.actor_user_id,
                configuration_hash=payload["configuration_hash"],
                features=payload["features"],
            )
        except ReservationError as exc:
            raise PostingDependencyError(
                "Identity authorization is unavailable; reconcile and retry this stock execution"
            ) from exc
        if facts.expires_at <= utcnow() + dt.timedelta(seconds=15):
            raise ConflictError(
                "stock source lease expired during reservation; reconcile before retrying"
            )

        async def commit(
            db: AsyncSession, accepted: ExecutionCommand
        ) -> tuple[EffectReference, ...]:
            intent = await db.scalar(
                select(VoucherMoneyIntent)
                .where(
                    VoucherMoneyIntent.company_id == accepted.company_id,
                    VoucherMoneyIntent.id == intent_id,
                )
                .with_for_update()
            )
            if (
                intent is None
                or intent.status != "PREPARED"
                or intent.request_hash != accepted.request_hash
            ):
                raise ConflictError("stock intent is no longer live")
            plan = await plan_for(db, intent)
            # Physical writes precede the journal inside this one transaction, so
            # its first-use account versions still match the prepared cost quote.
            posted = await apply(db, current, accepted, intent, facts)
            if posted.semantic_hash != plan.semantic_hash:
                raise ConflictError(
                    "stock changed after review; reconcile and review a fresh execution"
                )
            db.info["voucher_money_execution"] = accepted.execution_id
            references = [
                EffectReference(
                    owner="accounting", effect_kind="STOCK", effect_id=posted.posting_id
                )
            ]
            if journal_id:
                journal = await db.get(Journal, journal_id)
                if journal is None:
                    raise ConflictError("prepared stock journal is unavailable")
                await commit_post(db, current, journal, receipt)
                references.append(
                    EffectReference(owner="accounting", effect_kind="JOURNAL", effect_id=journal.id)
                )
            else:
                await zero_commit(db, current, intent, plan, receipt)
            if facts.expires_at <= utcnow():
                raise ConflictError("stock definition lease expired before commit")
            intent.status = "COMMITTED"
            intent.row_version += 1
            audit(
                db,
                current,
                posted.posting_id,
                "stock_posting",
                "reverse" if accepted.purpose == "REVERSE" else "post",
            )
            audit(db, current, intent.id, "voucher_money_intent", "commit")
            return tuple(references)

        async with asyncio.timeout(10), factory.begin() as db:
            db.info[SOURCE_DEADLINE] = facts.expires_at
            result = await execute(db, command, executor=commit)
            if result.outcome != "COMMITTED":
                intent = await db.get(VoucherMoneyIntent, intent_id)
                if intent and intent.status == "PREPARED":
                    await abandon(db, command, intent)
            return result, facts


async def dispatch(
    factory: async_sessionmaker[AsyncSession],
    command: ExecutionCommand,
    *,
    secret: bytes,
    client: ReservationAuthority | None,
    source_client: StockSourceClient | None,
    enabled: bool = False,
) -> ExecutionResult:
    facts = None
    try:
        result, facts = await _dispatch(
            factory,
            command,
            secret=secret,
            client=client,
            source_client=source_client,
            enabled=enabled,
        )
    except (ConflictError, ValidationFailedError, PermissionDeniedError) as error:
        log_failure(
            logging.getLogger("accounting.stock_execution"),
            service="accounting",
            event="stock.execution.content_rejected",
            error=error,
        )
        with tenant_scope(command.tenant_id):
            async with factory.begin() as db:
                result = await execute(db, command, content_rejected=True)
                intent = await db.scalar(
                    select(VoucherMoneyIntent)
                    .where(
                        VoucherMoneyIntent.company_id == command.company_id,
                        VoucherMoneyIntent.execution_id == command.execution_id,
                    )
                    .with_for_update()
                )
                if intent:
                    plan = await plan_for(db, intent)
                    facts = StockFenceFacts.model_validate(plan.source_facts)
                    if intent.status == "PREPARED" and result.outcome != "COMMITTED":
                        await abandon(db, command, intent)
    if facts and source_client and result.outcome in {"COMMITTED", "CANCELLED", "REJECTED"}:
        try:
            await source_client.release(facts)
        except StockSourceUnavailableError:
            pass  # Retained evidence remains; the bounded lease expires within sixty seconds.
    return result
