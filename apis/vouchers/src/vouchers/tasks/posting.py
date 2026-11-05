"""Build a durable owner command from approved revision and current signed authority."""

import datetime as dt
import uuid

from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution import ExecutionCommand
from voucher_execution.stock import STOCK_PROFILES, StockInput
from voucher_execution.transport import command_digest

from vouchers.api.auth import Access
from vouchers.models import core as m
from vouchers.models.counter import CounterSession, VoucherCounterContext
from vouchers.tasks.common import audit, expected, get
from vouchers.tasks.configuration import effective
from vouchers.tasks.documents import content, revision_for, validate_masters
from vouchers.tasks.execution_worker import enqueue


async def reverse(
    db: AsyncSession,
    current: Access,
    voucher_id: uuid.UUID,
    version: int,
    date: dt.date,
    reason: str,
    *,
    money_enabled: bool = True,
    stock_enabled: bool = False,
) -> m.VoucherOperation:
    from vouchers.domain.configuration import digest
    from vouchers.tasks.access import authorize

    authorize(current, "reverse")
    voucher = await get(db, current, m.Voucher, voucher_id, lock=True)
    expected(voucher, version)
    if (
        voucher.status != "POSTED"
        or current.authority is None
        or current.context.finance is None
        or not {"accounting", "vouchers"} <= current.context.policy_namespaces
    ):
        raise ConflictError("reversal requires a posted voucher and current financial authority")
    originals = list(
        await db.scalars(
            select(m.VoucherOperation)
            .where(
                m.VoucherOperation.company_id == voucher.company_id,
                m.VoucherOperation.voucher_id == voucher.id,
                m.VoucherOperation.purpose == "POST",
                m.VoucherOperation.status == "COMMITTED",
            )
            .limit(2)
        )
    )
    reversing = await db.scalar(
        select(m.VoucherOperation.id)
        .where(
            m.VoucherOperation.company_id == voucher.company_id,
            m.VoucherOperation.voucher_id == voucher.id,
            m.VoucherOperation.purpose == "REVERSE",
            m.VoucherOperation.status.in_(["PENDING", "COMMITTED"]),
        )
        .limit(1)
    )
    if len(originals) != 1 or reversing:
        raise ConflictError("original execution is unavailable or already reversing")
    counter_context = await db.scalar(
        select(VoucherCounterContext).where(
            VoucherCounterContext.company_id == current.context.company_id,
            VoucherCounterContext.revision_id == originals[0].revision_id,
        )
    )
    if counter_context is not None and counter_context.session_id is not None:
        shift = await get(db, current, CounterSession, counter_context.session_id, lock=True)
        if shift.status != "OPEN":
            raise ConflictError("closed counter session requires a new correction voucher")
    original = ExecutionCommand.model_validate(originals[0].command)
    is_stock = original.source_payload.get("stock") is not None
    if is_stock:
        stock = StockInput.model_validate(original.source_payload["stock"])
        if not stock_enabled or (original.kind, original.profile) != STOCK_PROFILES[stock.action]:
            raise ConflictError("native stock execution has not been activated for this profile")
    elif not money_enabled or original.kind not in {"JOURNAL", "CONTRA", "PAYMENT", "RECEIPT"}:
        raise ConflictError("this kind does not have a supported reversal execution")
    period = await fiscal_evidence(db, voucher.company_id, date)
    evidence = dict(original.configuration_evidence or {})
    evidence.pop("digest", None)
    evidence["company_configuration_hash"] = current.context.finance.configuration_hash
    evidence["digest"] = digest(evidence)
    command = original.model_copy(
        update={
            "purpose": "REVERSE",
            "reversal_of_execution_id": original.execution_id,
            "correction_reason": reason,
            "posting_date": date,
            "stock_date": date if is_stock else original.stock_date,
            "period_versions": {period.source_id: period.source_version},
            "authority": current.authority,
            "actor_user_id": current.actor.user_id,
            "authority_expires_at": dt.datetime.fromtimestamp(
                current.context.issued_at + 60, dt.UTC
            ),
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "configuration_evidence": evidence,
            "configuration_hash": evidence["digest"],
            "company_configuration_hash": current.context.finance.configuration_hash,
        }
    )
    command = command.model_copy(update={"request_hash": command_digest(command)})
    row = m.VoucherOperation(
        id=command.operation_id,
        tenant_id=command.tenant_id,
        company_id=command.company_id,
        voucher_id=voucher.id,
        revision_id=command.revision_id,
        execution_id=command.execution_id,
        purpose="REVERSE",
        status="PENDING",
        content_hash=command.content_hash,
        configuration_hash=command.configuration_hash,
        request_hash=command.request_hash,
        command=command.model_dump(mode="json"),
        created_by=current.actor.user_id,
        updated_by=current.actor.user_id,
    )
    db.add(row)
    audit(db, current, "operation", row.id, "create")
    return row


async def post(
    db: AsyncSession,
    current: Access,
    voucher_id: uuid.UUID,
    version: int,
    *,
    money_enabled: bool,
    invoice_enabled: bool,
    stock_enabled: bool = False,
) -> m.VoucherOperation:
    voucher = await get(db, current, m.Voucher, voucher_id, lock=True)
    expected(voucher, version)
    revision = await revision_for(db, current, voucher)
    counter_context = await db.scalar(
        select(VoucherCounterContext).where(
            VoucherCounterContext.company_id == current.context.company_id,
            VoucherCounterContext.revision_id == revision.id,
        )
    )
    if counter_context is not None and counter_context.session_id is not None:
        shift = await get(db, current, CounterSession, counter_context.session_id, lock=True)
        if shift.status != "OPEN" or shift.counter_id != counter_context.counter_id:
            raise ConflictError("counter session is closed or mismatched")
    if (
        current.authority is None
        or not {"accounting", "vouchers"} <= current.context.policy_namespaces
    ):
        raise ConflictError(
            "current gateway authority must include Accounting and voucher policies"
        )
    _, evidence = await effective(
        db,
        current,
        revision.type_revision_id,
        date=revision.document_date,
        posting_date=revision.posting_date,
        class_id=revision.class_id,
    )
    payload = await content(db, current, revision)
    kind = evidence["kind"]
    from vouchers.schemas.documents import VoucherInput

    await validate_masters(
        db,
        current,
        VoucherInput.model_validate(payload),
        capture=False,
        kind=kind,
        profile=evidence["profile"],
    )
    stock = (
        StockInput.model_validate(payload["stock"]) if payload.get("stock") is not None else None
    )
    if stock is not None:
        if not stock_enabled or (kind, evidence["profile"]) != STOCK_PROFILES[stock.action]:
            raise ConflictError("native stock execution has not been activated for this profile")
        if revision.posting_date is None or revision.stock_date is None:
            raise ConflictError("stock and posting dates are required")
        if stock.action == "PURCHASE_INVOICE":
            # B24: a goods Purchase bill posts its stock and its invoice in one execution.
            invoice = payload.get("invoice")
            if not invoice_enabled:
                raise ConflictError("invoice execution has not been activated")
            if (
                not isinstance(invoice, dict)
                or not invoice.get("accepted_calculation_hash")
                or payload.get("financial") is not None
                or revision.stock_date != revision.posting_date
            ):
                raise ConflictError("an accepted goods bill with its posting date is required")
    elif kind in {"JOURNAL", "CONTRA", "PAYMENT", "RECEIPT"}:
        if not money_enabled:
            raise ConflictError("ordinary money execution has not been activated")
        if not payload.get("financial") or revision.posting_date is None:
            raise ConflictError("financial entries and posting date are required")
    elif kind in {"SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"}:
        if not invoice_enabled:
            raise ConflictError("invoice execution has not been activated")
        invoice = payload.get("invoice")
        if (
            evidence["profile"] != "STANDARD"
            or not isinstance(invoice, dict)
            or not invoice.get("accepted_calculation_hash")
            or (kind in {"CREDIT_NOTE", "DEBIT_NOTE"}) != bool(invoice.get("source_invoice_id"))
            or payload.get("financial") is not None
            or payload.get("mode") != "ACCOUNTS"
            or payload.get("lines")
            or payload.get("stock_date")
            or revision.posting_date is None
            or any(
                supply.get("supply_kind") == "GOODS" or supply.get("item_line_key")
                for supply in invoice.get("supplies", [])
            )
        ):
            raise ConflictError("accepted account/service invoice and posting date are required")
    else:
        raise ConflictError("this kind has no supported financial execution")
    period = await fiscal_evidence(db, voucher.company_id, revision.posting_date)
    periods = {period.source_id: period.source_version}
    if stock is not None:
        stock_period = await fiscal_evidence(db, voucher.company_id, stock.stock_date)
        periods[stock_period.source_id] = stock_period.source_version
    number = (
        await db.scalar(
            select(m.VoucherNumberAssignment.display_number).where(
                m.VoucherNumberAssignment.company_id == voucher.company_id,
                m.VoucherNumberAssignment.revision_id == revision.id,
            )
        )
        if stock is not None
        else None
    )
    if stock is not None and number is None and stock.action != "PURCHASE_INVOICE":
        # A goods Purchase bill, like any Purchase, is numbered by its journal on posting.
        raise ConflictError("issue the stock voucher and retain its number before posting")
    approvals = tuple(
        await db.scalars(
            select(m.VoucherApproval.id).where(
                m.VoucherApproval.company_id == voucher.company_id,
                m.VoucherApproval.revision_id == revision.id,
                m.VoucherApproval.action == "approve",
                m.VoucherApproval.configuration_hash == revision.configuration_hash,
            )
        )
    )
    command = ExecutionCommand(
        protocol_version=2,
        tenant_id=current.actor.tenant_id,
        company_id=voucher.company_id,
        voucher_id=voucher.id,
        voucher_number=number,
        revision_id=revision.id,
        operation_id=uuid7(),
        execution_id=uuid7(),
        purpose="POST",
        kind=evidence["kind"],
        profile=evidence["profile"],
        authority=current.authority,
        authority_expires_at=dt.datetime.fromtimestamp(current.context.issued_at + 60, dt.UTC),
        configuration_evidence=evidence,
        company_configuration_hash=evidence["company_configuration_hash"],
        source_payload=payload,
        content_hash=revision.content_hash,
        configuration_hash=revision.configuration_hash,
        request_hash="0" * 64,
        posting_date=revision.posting_date,
        stock_date=revision.stock_date,
        period_versions=periods,
        actor_user_id=current.actor.user_id,
        approval_ids=approvals,
    )
    command = command.model_copy(update={"request_hash": command_digest(command)})
    row = await enqueue(db, current, command)
    audit(db, current, "operation", row.id, "create")
    return row


async def fiscal_evidence(
    db: AsyncSession, company_id: uuid.UUID, date: dt.date
) -> m.VoucherMasterEvidence:
    matches = list(
        await db.scalars(
            select(m.VoucherMasterEvidence)
            .where(
                m.VoucherMasterEvidence.company_id == company_id,
                m.VoucherMasterEvidence.owner == "accounting",
                m.VoucherMasterEvidence.entity_type == "fiscal_period",
                m.VoucherMasterEvidence.status == "ACTIVE",
                m.VoucherMasterEvidence.facts["start_date"].as_string() <= date.isoformat(),
                m.VoucherMasterEvidence.facts["end_date"].as_string() >= date.isoformat(),
            )
            .limit(2)
        )
    )
    if len(matches) != 1:
        raise ConflictError("refresh fiscal evidence and open the posting period")
    return matches[0]
