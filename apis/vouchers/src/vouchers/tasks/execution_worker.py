"""Durable signed Accounting delivery and reconciliation; no timeout releases an attempt."""

import asyncio
import logging
import uuid
from zoneinfo import ZoneInfo

import httpx
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.tenant_context import unfiltered
from billing_platform.db.types import utcnow
from billing_platform.diagnostics import log_failure
from billing_platform.errors import ConflictError, PlatformError
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from voucher_execution import ExecutionCommand
from voucher_execution.transport import ExecutionClient, StockExecutionClient, command_digest

from vouchers.api.auth import Access
from vouchers.domain.configuration import digest
from vouchers.domain.documents import validate_content
from vouchers.models import core as m
from vouchers.schemas.documents import VoucherInput
from vouchers.schemas.owners import StockExecutionOwner
from vouchers.tasks.access import authorize
from vouchers.tasks.common import company_lock
from vouchers.tasks.configuration import effective
from vouchers.tasks.documents import validate_masters
from vouchers.tasks.operations import apply_result
from vouchers.tasks.source_worker import Owner


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VOUCHERS_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    execution_owner: Owner | None = None
    stock_execution_owner: StockExecutionOwner | None = None


def check_configuration(settings: Settings) -> None:
    if settings.execution_owner is None and settings.stock_execution_owner is None:
        raise ValueError("execution delivery requires a configured owner")


async def enqueue(
    db: AsyncSession, current: Access, command: ExecutionCommand
) -> m.VoucherOperation:
    """Called by a future capability-gated producer after validation, under its company fence."""
    authorize(current, "post")
    if (command.tenant_id, command.company_id, command.actor_user_id) != (
        current.actor.tenant_id,
        current.context.company_id,
        current.actor.user_id,
    ):
        raise ConflictError("execution actor or company differs")
    await company_lock(db, current)
    voucher = await db.scalar(
        select(m.Voucher)
        .where(m.Voucher.company_id == command.company_id, m.Voucher.id == command.voucher_id)
        .with_for_update()
    )
    if voucher is None or voucher.status not in {"APPROVED", "ISSUED"}:
        raise ConflictError("approved current voucher evidence is required")
    if command.purpose != "POST" or command_digest(command) != command.request_hash:
        raise ConflictError("invalid durable execution command")
    revision = await db.scalar(
        select(m.VoucherRevision).where(
            m.VoucherRevision.company_id == command.company_id,
            m.VoucherRevision.id == command.revision_id,
            m.VoucherRevision.voucher_id == command.voucher_id,
        )
    )
    if (
        revision is None
        or revision.revision_number != voucher.current_revision
        or revision.content_hash != digest(command.source_payload)
        or revision.content_hash != command.content_hash
        or revision.configuration_hash != command.configuration_hash
    ):
        raise ConflictError("execution does not match the accepted document revision")
    policy, evidence = await effective(
        db,
        current,
        revision.type_revision_id,
        date=revision.document_date,
        posting_date=revision.posting_date,
        class_id=revision.class_id,
    )
    if (
        evidence["digest"] != command.configuration_hash
        or evidence["company_configuration_hash"] != command.company_configuration_hash
        or (evidence["kind"], evidence["profile"]) != (command.kind, command.profile)
    ):
        raise ConflictError("execution configuration has changed")
    approved = set(
        await db.scalars(
            select(m.VoucherApproval.id).where(
                m.VoucherApproval.company_id == command.company_id,
                m.VoucherApproval.revision_id == revision.id,
                m.VoucherApproval.action == "approve",
                m.VoucherApproval.configuration_hash == command.configuration_hash,
            )
        )
    )
    if (policy.approval_required and not approved) or set(command.approval_ids) != approved:
        raise ConflictError("execution approval evidence differs")
    finance = current.context.finance
    if finance is None or not finance.company_active:
        raise ConflictError("current financial company facts are required")
    payload = VoucherInput.model_validate(command.source_payload)
    validate_content(
        payload,
        policy,
        kind=command.kind,
        profile=command.profile,
        stage="POST",
        today=utcnow().astimezone(ZoneInfo(finance.timezone)).date(),
    )
    await validate_masters(
        db, current, payload, capture=False, kind=command.kind, profile=command.profile
    )
    pending = await db.scalar(
        select(m.VoucherOperation.id)
        .where(
            m.VoucherOperation.company_id == command.company_id,
            m.VoucherOperation.voucher_id == command.voucher_id,
            m.VoucherOperation.purpose == "POST",
            m.VoucherOperation.status.in_(["PENDING", "COMMITTED"]),
        )
        .limit(1)
    )
    if pending is not None:
        raise ConflictError("source already has an unresolved or committed attempt")
    row = m.VoucherOperation(
        id=command.operation_id,
        tenant_id=command.tenant_id,
        company_id=command.company_id,
        voucher_id=command.voucher_id,
        revision_id=command.revision_id,
        execution_id=command.execution_id,
        purpose="POST",
        status="PENDING",
        content_hash=command.content_hash,
        configuration_hash=command.configuration_hash,
        request_hash=command.request_hash,
        command=command.model_dump(mode="json"),
        created_by=command.actor_user_id,
        updated_by=command.actor_user_id,
    )
    db.add(row)
    await db.flush()
    return row


async def deliver(
    factory: async_sessionmaker[AsyncSession],
    transport: ExecutionClient,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    operation_id: uuid.UUID,
    *,
    stock_channel: bool = False,
) -> bool:
    with tenant_scope(tenant_id):
        async with factory() as db, db.begin():
            row = await db.scalar(
                select(m.VoucherOperation)
                .where(
                    m.VoucherOperation.company_id == company_id,
                    m.VoucherOperation.id == operation_id,
                )
                .with_for_update()
            )
            if (
                row is None
                or row.purpose not in {"POST", "REVERSE"}
                or row.status != "PENDING"
                or row.command is None
            ):
                return False
            command = ExecutionCommand.model_validate(row.command)
            if (command.source_payload.get("stock") is not None) != stock_channel:
                return False
            cancel = row.cancel_requested
            row.attempt_count += 1
        # Remote calls are outside all SQL transactions. Unknown outcomes remain pending.
        try:
            result = await transport.status(command)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 404:
                raise
            result = await transport.send(command, purpose="CANCEL" if cancel else command.purpose)
        if (
            result.operation_id != operation_id
            or result.tenant_id != tenant_id
            or result.company_id != company_id
        ):
            raise ConflictError("Accounting returned a different execution scope")
        async with factory() as db, db.begin():
            await apply_result(db, result)
        return result.outcome != "PENDING"


async def stock_companies(
    factory: async_sessionmaker[AsyncSession], after: uuid.UUID | None
) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    # Trusted queue maintenance discovers identifiers only. No document or user
    # facts escape tenant scoping. Delivery re-enters that tenant and the owner
    # checks the immutable accepted command and delegated company authority.
    with unfiltered():
        async with factory() as db:
            query = select(
                m.VoucherCompanyGuard.id,
                m.VoucherCompanyGuard.tenant_id,
                m.VoucherCompanyGuard.company_id,
            )
            if after is not None:
                query = query.where(m.VoucherCompanyGuard.id > after)
            return [
                tuple(row)
                for row in (
                    await db.execute(query.order_by(m.VoucherCompanyGuard.id).limit(100))
                ).all()
            ]


async def deliver_stock_page(
    factory: async_sessionmaker[AsyncSession],
    transport: StockExecutionClient,
    after: uuid.UUID | None,
) -> uuid.UUID | None:
    companies = await stock_companies(factory, after)
    for _identity, tenant_id, company_id in companies:
        with tenant_scope(tenant_id):
            async with factory() as db:
                ids = list(
                    await db.scalars(
                        select(m.VoucherOperation.id)
                        .where(
                            m.VoucherOperation.company_id == company_id,
                            m.VoucherOperation.status == "PENDING",
                            m.VoucherOperation.purpose.in_(["POST", "REVERSE"]),
                        )
                        .order_by(m.VoucherOperation.id)
                        .limit(50)
                    )
                )
        for identity in ids:
            try:
                await deliver(
                    factory, transport, tenant_id, company_id, identity, stock_channel=True
                )
            except (httpx.HTTPError, PlatformError) as error:
                log_failure(
                    logging.getLogger("vouchers.execution"),
                    service="vouchers",
                    event="stock.execution.delivery_deferred",
                    error=error,
                )
    return companies[-1][0] if len(companies) == 100 else None


async def run(settings: Settings) -> None:
    owner = settings.execution_owner
    stock_owner = settings.stock_execution_owner
    if (owner is None and stock_owner is None) or (
        owner is not None and owner.owner != "accounting"
    ):
        raise ValueError("an Accounting execution owner is required")
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as http:
            transport = (
                ExecutionClient(
                    http, owner.origin, owner.key_id, owner.secret.get_secret_value().encode()
                )
                if owner is not None
                else None
            )
            stock_transport = (
                StockExecutionClient(
                    http,
                    stock_owner.origin,
                    stock_owner.key_id,
                    stock_owner.secret.get_secret_value().encode(),
                )
                if stock_owner is not None
                else None
            )
            stock_after = None
            while True:
                if stock_transport is not None:
                    stock_after = await deliver_stock_page(factory, stock_transport, stock_after)
                for scope in owner.scopes if owner is not None else ():
                    with tenant_scope(scope.tenant_id):
                        async with factory() as db:
                            ids = list(
                                await db.scalars(
                                    select(m.VoucherOperation.id)
                                    .where(
                                        m.VoucherOperation.company_id == scope.company_id,
                                        m.VoucherOperation.purpose.in_(["POST", "REVERSE"]),
                                        m.VoucherOperation.status == "PENDING",
                                    )
                                    .order_by(m.VoucherOperation.id)
                                    .limit(50)
                                )
                            )
                    for identity in ids:
                        try:
                            assert transport is not None
                            await deliver(
                                factory, transport, scope.tenant_id, scope.company_id, identity
                            )
                        except (httpx.HTTPError, PlatformError) as error:
                            log_failure(
                                logging.getLogger("vouchers.execution"),
                                service="vouchers",
                                event="execution.delivery_deferred",
                                error=error,
                            )
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()
    configuration = Settings(_env_file=args.env_file)  # type: ignore[call-arg] # BaseSettings supports env-file at runtime.
    check_configuration(configuration)
    if not args.check_config:
        asyncio.run(run(configuration))
