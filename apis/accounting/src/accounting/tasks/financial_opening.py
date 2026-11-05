"""Company opening worksheets reuse native opening batches and journal effects."""

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any, cast

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import denied_fields
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    canonical_json,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.domain.financial_opening import declaration_hash, execution_chunks, opening_plan
from accounting.models.financial_opening import (
    FinancialOpeningChunk,
    FinancialOpeningEntry,
    FinancialOpeningRevision,
)
from accounting.models.ledger import Journal
from accounting.models.masters import Account, Record
from accounting.models.subledger import OpeningBatch
from accounting.schemas.financial_opening import (
    OpeningDeclaration,
    OpeningReplace,
    OpeningRevisionCommand,
    OpeningWorkspaceDetail,
)
from accounting.schemas.ledger import JournalCreate
from accounting.schemas.subledger import OpeningCreate
from accounting.tasks.commands import require_metadata, setup_lock
from accounting.tasks.finance_records import change_row, create_row, require_fields
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.journal_drafts import create_in_transaction, require_preview_fields
from accounting.tasks.openings import preview, require_available, require_opening_revision_window


def require_read(current: Any) -> None:
    financial_context(current)
    require_fields(
        current, "opening_batch", {"id", "status", "posting_date", "payload", "journal_id"}
    )
    require_preview_fields(current)
    require_fields(
        current, "account", {"id", "kind", "party_id", "party_role", "currency", "currency_mode"}
    )
    require_fields(current, "journal_line", {"party_id", "role", "description", "sequence"})
    require_fields(current, "journal", {"document_date", "posting_date", "description", "status"})
    from accounting.financial_resources import FINANCIAL_BY_NAME
    from accounting.tasks.access import rules

    if denied_fields(
        frozenset({"opening_base_amount"}),
        rules=rules(current, FINANCIAL_BY_NAME["journal_line"], None),
        access="read",
        target=ScopePath(company_id=current.context.company_id),
    ):
        raise PermissionDeniedError("opening carrying values are not readable")
    require_fields(
        current,
        "open_item",
        {
            "account_id",
            "party_id",
            "role",
            "direction",
            "reference",
            "amount",
            "base_amount",
            "currency",
            "document_date",
            "due_date",
            "terms",
        },
    )


def capture_permissions(current: Any) -> dict[str, dict[str, bool]]:
    """Capture uses finance management; native posting rights remain separate."""
    from accounting.financial_resources import FINANCIAL_BY_NAME
    from accounting.tasks.access import rules

    target = ScopePath(company_id=current.context.company_id)
    allowed = current.actor.allows_scope("accounting.finance.manage", target=target)
    fields = {
        "journal_lines": (
            "journal_line",
            frozenset(
                {
                    "account_id",
                    "side",
                    "currency",
                    "amount",
                    "exchange_rate",
                    "base_amount",
                    "base_currency",
                    "party_id",
                    "role",
                    "description",
                    "opening_base_amount",
                }
            ),
        ),
        "open_items": (
            "open_item",
            frozenset(
                {
                    "account_id",
                    "party_id",
                    "role",
                    "direction",
                    "reference",
                    "currency",
                    "amount",
                    "base_currency",
                    "base_amount",
                    "document_date",
                    "due_date",
                    "posting_date",
                    "terms",
                }
            ),
        ),
    }
    result = {}
    for name, (resource, keys) in fields.items():
        denied = denied_fields(
            keys,
            rules=rules(current, FINANCIAL_BY_NAME[resource], None),
            access="write",
            target=target,
        )
        result[name] = {key: allowed and key not in denied for key in sorted(keys)}
    return result


OPENING_AUDIT_FIELDS = {
    "master_opening_balance": frozenset({"account_id", "source_key", "status", "opening_date"}),
    "financial_opening_revision": frozenset({"batch_id", "revision", "manifest_hash"}),
    "financial_opening_entry": frozenset(
        {
            "revision_id",
            "ordinal",
            "account_id",
            "party_id",
            "role",
            "side",
            "currency",
            "amount",
            "base_amount",
            "document_count",
        }
    ),
    "financial_opening_chunk": frozenset({"batch_id", "revision_id", "ordinal", "journal_id"}),
    "financial_opening_import": frozenset({"state", "batch_id", "row_version"}),
}


def audit_values(row: Record) -> dict[str, Any]:
    return {key: getattr(row, key) for key in OPENING_AUDIT_FIELDS[row.__tablename__]}


def audit(
    db: AsyncSession,
    current: Any,
    row: Record,
    action: str,
    *,
    before: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    from billing_platform.audit_evidence import scalar

    from accounting.events.audit_contract import audit_event

    event = audit_event(row.__tablename__, action)
    after = audit_values(row)
    evidence: dict[str, Any] = {
        key: {"from": scalar((before or {}).get(key)), "to": scalar(value)}
        if action == "create" or (before is not None and key in before)
        else {"changed": True}
        for key, value in after.items()
        if action == "create" or before is None or (key in before and before[key] != value)
    }
    if "base_amount" in evidence:
        evidence["base_currency"] = {"from": None, "to": current.context.base_currency}
    emit(
        db,
        aggregate_type="accounting." + row.__tablename__,
        aggregate_id=row.id,
        tenant_id=current.actor.tenant_id,
        event_type=event,
        payload=audit_payload(
            action=event,
            category="access" if action == "export" else "money",
            entity_type="accounting." + row.__tablename__,
            entity_id=row.id,
            actor_user_id=current.actor.user_id,
            company_id=row.company_id,
            changes=evidence,
            reason=reason,
        )
        | {"actor_type": "user"},
    )


def record(current: Any, model: type[Record], **values: Any) -> Record:
    return model(
        id=uuid7(),
        tenant_id=current.actor.tenant_id,
        company_id=current.context.company_id,
        created_by=current.actor.user_id,
        updated_by=current.actor.user_id,
        **values,
    )


async def command(
    factory: async_sessionmaker[AsyncSession],
    current: Any,
    action: str,
    body: BaseModel,
    key: str,
    mutate: Callable[[AsyncSession], Awaitable[Record]],
    identity: uuid.UUID | None = None,
    *,
    scope_model: type[Record] = OpeningBatch,
    renderer: Callable[[AsyncSession, Any, uuid.UUID], Awaitable[BaseModel]] | None = None,
) -> CommandResult[BaseModel]:
    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        require_read(current)
        current.actor.require_scope(
            "accounting.finance.manage", target=ScopePath(company_id=current.context.company_id)
        )
        await require_metadata(db, current)
        if identity:
            await company_object(db, scope_model, identity, company_id=current.context.company_id)
        if receipt:
            await company_object(
                db, scope_model, uuid.UUID(receipt["id"]), company_id=current.context.company_id
            )

    async def change(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, current)
        row = await mutate(db)
        return CommandReceipt(
            201 if action in {"create", "import_stage"} else 200, {"id": str(row.id)}
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        return (
            await detail(db, current, uuid.UUID(receipt["id"]))
            if renderer is None
            else await renderer(db, current, uuid.UUID(receipt["id"]))
        )

    try:
        encoded = canonical_json(body.model_dump(mode="json"), maximum_bytes=3 * 1048576)
    except ValueError as problem:
        raise ValidationFailedError(
            "opening command exceeds the supported request size"
        ) from problem
    digest = hashlib.sha256(encoded).hexdigest()
    return await execute_idempotent(
        factory,
        CommandIdentity(
            current.actor.tenant_id,
            current.context.company_id,
            current.actor.user_id,
            "accounting.financial_opening." + action,
            key,
            {"input_hash": digest, "id": str(identity) if identity else None},
        ),
        authorize=check,
        mutate=change,
        render=render,
        timeout_seconds=30,
    )


async def revision(db: AsyncSession, current: Any, batch: OpeningBatch) -> FinancialOpeningRevision:
    marker = batch.payload.get("workspace_revision_id")
    if not marker:
        raise ConflictError("use the legacy opening workflow for this batch")
    row = await company_object(
        db, FinancialOpeningRevision, uuid.UUID(marker), company_id=batch.company_id
    )
    if row.batch_id != batch.id:
        raise ConflictError("opening declaration does not belong to this batch")
    return row


async def declaration(
    db: AsyncSession, current: Any, batch: OpeningBatch, revision_id: uuid.UUID | None = None
) -> OpeningDeclaration:
    require_read(current)
    rev = (
        await revision(db, current, batch)
        if revision_id is None
        else await company_object(
            db, FinancialOpeningRevision, revision_id, company_id=batch.company_id
        )
    )
    if rev.batch_id != batch.id:
        raise ConflictError("opening revision does not belong to this company declaration")
    rows = list(
        await db.scalars(
            select(FinancialOpeningEntry)
            .where(
                FinancialOpeningEntry.company_id == batch.company_id,
                FinancialOpeningEntry.revision_id == rev.id,
            )
            .order_by(FinancialOpeningEntry.ordinal)
            .limit(10001)
        )
    )
    if len(rows) != rev.header["entry_count"]:
        raise ConflictError("opening declaration evidence is incomplete")
    return OpeningDeclaration.model_validate(
        rev.header["declaration"] | {"entries": [row.payload for row in rows]}
    )


async def chunks(
    db: AsyncSession, current: Any, batch: OpeningBatch
) -> list[FinancialOpeningChunk]:
    rev = await revision(db, current, batch)
    return list(
        await db.scalars(
            select(FinancialOpeningChunk)
            .where(
                FinancialOpeningChunk.company_id == batch.company_id,
                FinancialOpeningChunk.revision_id == rev.id,
            )
            .order_by(FinancialOpeningChunk.ordinal)
            .limit(1001)
        )
    )


async def validate_ytd(db: AsyncSession, current: Any, body: OpeningDeclaration) -> None:
    if body.coverage_mode != "YTD_SUMMARY":
        return
    from collections import defaultdict

    from accounting.domain.fiscal import monthly_periods
    from accounting.domain.ledger import base_value
    from accounting.models.masters import AccountGroup, AccountHead

    facts = financial_context(current)
    year = body.posting_date.year
    start = monthly_periods(year, facts.fiscal_year_start_month, facts.fiscal_year_start_day)[
        0
    ].start_date
    if start > body.posting_date:
        start = monthly_periods(
            year - 1, facts.fiscal_year_start_month, facts.fiscal_year_start_day
        )[0].start_date
    if start != body.originating_year_start:
        raise ValidationFailedError(
            "YTD source year must match the company's cutover financial year"
        )
    require_fields(current, "account_group", {"head_id"})
    require_fields(current, "account_head", {"nature"})
    identities = {entry.account_id for entry in body.entries} | {
        entry.account_id for entry in body.ytd_summary or []
    }
    rows = list(
        await db.execute(
            select(Account.id, AccountHead.nature)
            .join(AccountGroup, AccountGroup.id == Account.group_id)
            .join(AccountHead, AccountHead.id == AccountGroup.head_id)
            .where(Account.company_id == current.context.company_id, Account.id.in_(identities))
        )
    )
    nominal = {row.id for row in rows if row.nature in {"INCOME", "EXPENSE"}}
    expected: dict[tuple[uuid.UUID, str], list[Decimal]] = defaultdict(
        lambda: [Decimal(0), Decimal(0)]
    )
    actual: dict[tuple[uuid.UUID, str], list[Decimal]] = defaultdict(
        lambda: [Decimal(0), Decimal(0)]
    )
    for entry in body.entries:
        if entry.account_id in nominal:
            sign = 1 if entry.side == "DEBIT" else -1
            key = (entry.account_id, entry.currency)
            expected[key][0] += sign * entry.amount
            expected[key][1] += sign * (
                entry.base_amount
                or base_value(
                    entry.amount,
                    entry.currency,
                    entry.exchange_rate,
                    body.currency,
                    facts.amount_precision,
                    facts.rounding_mode,
                )
            )
    for summary_entry in body.ytd_summary or []:
        if (
            summary_entry.account_id not in nominal
            or (summary_entry.account_id, summary_entry.currency) not in expected
        ):
            await company_object(
                db, Account, summary_entry.account_id, company_id=current.context.company_id
            )
            raise ValidationFailedError("YTD activity must reference income or expense accounts")
        if (
            summary_entry.currency == body.currency
            and summary_entry.amount != summary_entry.base_amount
        ):
            raise ValidationFailedError(
                "base-currency YTD activity must have identical carrying and transaction amounts"
            )
        sign = 1 if summary_entry.side == "DEBIT" else -1
        key = (summary_entry.account_id, summary_entry.currency)
        actual[key][0] += sign * summary_entry.amount
        actual[key][1] += sign * summary_entry.base_amount
    if {key: value for key, value in expected.items() if any(value)} != {
        key: value for key, value in actual.items() if any(value)
    }:
        raise ValidationFailedError(
            "YTD nominal activity must match opening nominal GL; do not duplicate retained earnings"
        )


async def require_clearing_account(db: AsyncSession, current: Any, identity: uuid.UUID) -> None:
    from accounting.models.masters import AccountGroup, AccountHead
    from accounting.models.stock import StockAccountPolicy

    if await db.scalar(
        select(StockAccountPolicy.id)
        .where(
            StockAccountPolicy.company_id == current.context.company_id,
            StockAccountPolicy.inventory_account_id == identity,
        )
        .limit(1)
    ):
        raise ValidationFailedError("an inventory-control account cannot be migration clearing")
    account = await company_object(db, Account, identity, company_id=current.context.company_id)
    group = await company_object(db, AccountGroup, account.group_id, company_id=account.company_id)
    head = await company_object(db, AccountHead, group.head_id, company_id=account.company_id)
    require_fields(current, "account", {"posting_policy", "status"}, row=account)
    require_fields(current, "account_group", {"head_id"}, row=group)
    require_fields(current, "account_head", {"nature"}, row=head)
    if (
        account.kind != "GENERAL"
        or account.party_id is not None
        or account.status != "ACTIVE"
        or account.posting_policy != "MANUAL_ALLOWED"
        or head.nature not in {"ASSET", "LIABILITY"}
        or (account.currency_mode == "FIXED" and account.currency != current.context.base_currency)
    ):
        raise ValidationFailedError(
            "clearing requires an active non-party general balance-sheet account in base currency"
        )


async def require_account_identity(db: AsyncSession, current: Any, batch: OpeningBatch) -> None:
    """A declaration cannot silently move its balances to a different party or role."""
    rev = await revision(db, current, batch)
    if rev.header["declaration"]["coverage_mode"] == "YTD_SUMMARY":
        await validate_ytd(db, current, await declaration(db, current, batch))
    if rev.header["declaration"].get("clearing_account_id"):
        await require_clearing_account(
            db, current, uuid.UUID(rev.header["declaration"]["clearing_account_id"])
        )
    changed = await db.scalar(
        select(FinancialOpeningEntry.id)
        .join(Account, Account.id == FinancialOpeningEntry.account_id)
        .where(
            FinancialOpeningEntry.company_id == batch.company_id,
            FinancialOpeningEntry.revision_id == rev.id,
            (Account.party_id.is_distinct_from(FinancialOpeningEntry.party_id))
            | (Account.party_role.is_distinct_from(FinancialOpeningEntry.role)),
        )
        .limit(1)
    )
    if changed:
        raise ConflictError("account party identity changed; replace and review the declaration")


async def detail(db: AsyncSession, current: Any, identity: uuid.UUID) -> OpeningWorkspaceDetail:
    require_read(current)
    batch = await company_object(db, OpeningBatch, identity, company_id=current.context.company_id)
    rev = await revision(db, current, batch)
    links = await chunks(db, current, batch)
    ids = [link.journal_id for link in links if link.journal_id]
    journals = (
        list(
            await db.scalars(
                select(Journal).where(Journal.company_id == batch.company_id, Journal.id.in_(ids))
            )
        )
        if ids
        else []
    )
    reversed_ids = (
        set(
            await db.scalars(
                select(Journal.reversal_of_id).where(
                    Journal.company_id == batch.company_id,
                    Journal.reversal_of_id.in_(ids),
                    Journal.status == "POSTED",
                )
            )
        )
        if ids
        else set()
    )
    posted = sum(row.status == "POSTED" and row.id not in reversed_ids for row in journals)
    blockers = []
    if len(ids) != len(links):
        blockers.append("OPENING_DRAFTS_NOT_PREPARED")
    if posted != len(links):
        blockers.append("OPENING_JOURNALS_NOT_POSTED")
    if batch.payload.get("opening_correction"):
        blockers.append("OPENING_CORRECTION_IN_PROGRESS")
    return OpeningWorkspaceDetail(
        id=batch.id,
        company_id=batch.company_id,
        status=batch.status,
        posting_date=batch.posting_date,
        expected_version=batch.row_version,
        revision_id=rev.id,
        manifest_hash=rev.manifest_hash,
        currency=rev.header["declaration"]["currency"],
        coverage_mode=rev.header["declaration"]["coverage_mode"],
        entry_count=rev.header["entry_count"],
        document_count=rev.header["document_count"],
        expected_debit=rev.header["total_debit"],
        expected_credit=rev.header["total_debit"],
        journal_ids=ids,
        posted_journals=posted,
        blockers=blockers,
        effect_kind="POSTED"
        if batch.status == "FINALIZED"
        else "PARTIALLY_POSTED"
        if posted
        else "PREPARATION",
    )


async def reject_withdrawn_party_balances(
    db: AsyncSession, current: Any, body: OpeningDeclaration
) -> None:
    """A balance withdrawn from a party import must not come back through a stale worksheet."""
    from sqlalchemy import func

    from accounting.models.party_opening import PartyOpeningBalance
    from accounting.tasks.master_opening import validate_sources

    await validate_sources(db, current, body)

    held = {
        entry.source_key.lower()
        for entry in body.entries
        if entry.source_key.lower().startswith("pob-")
    }
    if held and await db.scalar(
        select(PartyOpeningBalance.id)
        .where(
            PartyOpeningBalance.company_id == current.context.company_id,
            PartyOpeningBalance.status == "WITHDRAWN",
            func.lower(PartyOpeningBalance.source_key).in_(held),
        )
        .limit(1)
    ):
        raise ValidationFailedError(
            "a held party balance that was withdrawn cannot be included in the declaration"
        )


async def validate(db: AsyncSession, current: Any, body: OpeningDeclaration) -> list[OpeningCreate]:
    require_read(current)
    facts = financial_context(current)
    if body.posting_date != facts.books_begin_date:
        raise ValidationFailedError("opening declaration must use company books begin")
    await validate_ytd(db, current, body)
    if body.clearing_account_id is not None:
        await require_clearing_account(db, current, body.clearing_account_id)
    await reject_withdrawn_party_balances(db, current, body)
    credit_cash = await db.scalar(
        select(Account.id)
        .where(
            Account.company_id == current.context.company_id,
            Account.kind == "CASH",
            Account.id.in_({entry.account_id for entry in body.entries if entry.side == "CREDIT"}),
        )
        .limit(1)
    )
    if credit_cash and not body.credit_cash_reviewed:
        raise ValidationFailedError(
            "credit cash requires explicit opening review and an explanation"
        )
    result = execution_chunks(
        body, current.context.base_currency, facts.amount_precision, facts.rounding_mode
    )
    references = set()
    sources = set()
    for entry in body.entries:
        for bill in entry.documents:
            reference = (entry.account_id, entry.currency, bill.reference.casefold())
            if reference in references or (
                bill.source_key is not None and bill.source_key.casefold() in sources
            ):
                raise ValidationFailedError(
                    "opening document references and source keys must be unique across all chunks"
                )
            references.add(reference)
            if bill.source_key:
                sources.add(bill.source_key.casefold())
    for chunk in result:
        await preview(db, current, chunk)
    return result


async def require_capture_write(db: AsyncSession, current: Any, body: OpeningDeclaration) -> None:
    """Capture cannot become a JSON side door around native changed-field policies."""
    from accounting.domain.ledger import base_value
    from accounting.financial_resources import FINANCIAL_BY_NAME
    from accounting.tasks.access import writable

    facts = financial_context(current)
    account_ids = {entry.account_id for entry in body.entries}
    accounts = {
        row.id: row for row in await db.scalars(select(Account).where(Account.id.in_(account_ids)))
    }
    for identity in account_ids:
        if identity not in accounts or accounts[identity].company_id != current.context.company_id:
            await company_object(db, Account, identity, company_id=current.context.company_id)
    for entry in body.entries:
        account = accounts[entry.account_id]
        amount = entry.base_amount or base_value(
            entry.amount,
            entry.currency,
            entry.exchange_rate,
            body.currency,
            facts.amount_precision,
            facts.rounding_mode,
        )
        writable(
            current,
            FINANCIAL_BY_NAME["journal_line"],
            {},
            {
                "account_id": entry.account_id,
                "side": entry.side,
                "currency": entry.currency,
                "amount": entry.amount,
                "exchange_rate": entry.exchange_rate,
                "base_amount": amount,
                "base_currency": body.currency,
                "party_id": account.party_id,
                "role": account.party_role,
                "description": entry.description,
                "opening_base_amount": amount,
            },
        )
        for bill in entry.documents:
            writable(
                current,
                FINANCIAL_BY_NAME["open_item"],
                {},
                {
                    "account_id": entry.account_id,
                    "party_id": account.party_id,
                    "role": account.party_role,
                    "direction": "DEBT"
                    if (account.party_role == "CUSTOMER") == (entry.side == "DEBIT")
                    else "CREDIT",
                    "reference": bill.reference,
                    "currency": entry.currency,
                    "amount": bill.amount,
                    "base_currency": body.currency,
                    "base_amount": bill.base_amount,
                    "document_date": bill.document_date,
                    "due_date": bill.due_date,
                    "posting_date": body.posting_date,
                    "terms": bill.model_dump(mode="json"),
                },
            )


async def write_revision(
    db: AsyncSession,
    current: Any,
    batch: OpeningBatch,
    body: OpeningDeclaration,
    plans: list[OpeningCreate],
    number: int,
    review_reason: str | None = None,
) -> None:
    from accounting.domain.ledger import base_value

    await require_capture_write(db, current, body)
    facts = financial_context(current)
    valued = [
        entry.base_amount
        or base_value(
            entry.amount,
            entry.currency,
            entry.exchange_rate,
            body.currency,
            facts.amount_precision,
            facts.rounding_mode,
        )
        for entry in body.entries
    ]
    header = {
        "review_reason": review_reason or body.reason,
        "declaration": body.model_dump(mode="json", exclude={"entries"}),
        "entry_count": len(body.entries),
        "document_count": sum(len(entry.documents) for entry in body.entries),
        "total_debit": str(
            sum(
                (
                    amount
                    for entry, amount in zip(body.entries, valued, strict=True)
                    if entry.side == "DEBIT"
                ),
                Decimal(0),
            )
        ),
    }
    rev = cast(
        FinancialOpeningRevision,
        record(
            current,
            FinancialOpeningRevision,
            batch_id=batch.id,
            revision=number,
            manifest_hash=declaration_hash(body),
            header=header,
        ),
    )
    db.add(rev)
    await db.flush()
    audit(db, current, rev, "create")
    accounts = {
        row.id: row
        for row in await db.scalars(
            select(Account).where(
                Account.company_id == batch.company_id,
                Account.id.in_({entry.account_id for entry in body.entries}),
            )
        )
    }
    for index, (entry, amount) in enumerate(zip(body.entries, valued, strict=True), 1):
        account = accounts[entry.account_id]
        row = record(
            current,
            FinancialOpeningEntry,
            revision_id=rev.id,
            ordinal=index,
            source_key=entry.source_key,
            account_id=entry.account_id,
            party_id=account.party_id,
            role=account.party_role,
            side=entry.side,
            currency=entry.currency,
            amount=entry.amount,
            base_amount=amount,
            document_count=len(entry.documents),
            payload=entry.model_dump(mode="json"),
        )
        db.add(row)
        audit(db, current, row, "create")
    offset = 0
    for index, plan in enumerate(plans, 1):
        count = sum(line.account_id != body.clearing_account_id for line in plan.lines)
        source_keys = [entry.source_key for entry in body.entries[offset : offset + count]]
        offset += count
        row = record(
            current,
            FinancialOpeningChunk,
            batch_id=batch.id,
            revision_id=rev.id,
            ordinal=index,
            journal_id=None,
            payload=plan.model_dump(mode="json") | {"entry_source_keys": source_keys},
        )
        db.add(row)
        audit(db, current, row, "create")
    await db.flush()
    await change_row(
        db,
        current,
        "opening_batch",
        batch,
        "update",
        payload={
            "workspace_revision_id": str(rev.id),
            "coverage": {
                "mode": body.coverage_mode,
                "posting_date": body.posting_date.isoformat(),
                "covered_through": body.covered_through.isoformat(),
                "originating_year_start": body.originating_year_start.isoformat()
                if body.originating_year_start
                else None,
                "source_system": body.source_system,
                "source_id": body.source_id,
                "manifest_hash": rev.manifest_hash,
                "ytd_summary": [entry.model_dump(mode="json") for entry in body.ytd_summary]
                if body.ytd_summary is not None
                else None,
            },
            "journal_ids": [],
        },
    )


async def create_in_workspace(
    db: AsyncSession, current: Any, body: OpeningDeclaration
) -> OpeningBatch:
    await require_available(db, current, body.replacement_of_id)
    if await db.scalar(
        select(Journal.id)
        .where(
            Journal.company_id == current.context.company_id,
            Journal.status.in_(["PREPARED", "POSTED"]),
            Journal.kind.not_in(["OPENING", "REVERSAL"]),
        )
        .limit(1)
    ):
        raise ConflictError(
            "existing trading history requires controller review; do not create another opening"
        )
    plans = await validate(db, current, body)
    await require_opening_revision_window(db, current, body.posting_date)
    batch = cast(
        OpeningBatch,
        await create_row(
            db,
            current,
            "opening_batch",
            status="DRAFT",
            posting_date=body.posting_date,
            description=body.reason,
            payload={},
            replacement_of_id=body.replacement_of_id,
            journal_id=None,
            finalized_at=None,
        ),
    )
    await write_revision(db, current, batch, body, plans, 1)
    return batch


async def create(
    factory: async_sessionmaker[AsyncSession], current: Any, body: OpeningDeclaration, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> OpeningBatch:
        return await create_in_workspace(db, current, body)

    return await command(factory, current, "create", body, key, mutate)


async def matching(
    db: AsyncSession,
    current: Any,
    identity: uuid.UUID,
    body: OpeningRevisionCommand,
    *,
    allow_correction: bool = False,
) -> OpeningBatch:
    batch = await company_object(db, OpeningBatch, identity, company_id=current.context.company_id)
    rev = await revision(db, current, batch)
    if batch.row_version != body.expected_version or rev.manifest_hash != body.manifest_hash:
        raise ConflictError("opening declaration changed; reload and review its current version")
    if batch.status != "DRAFT" or (
        batch.payload.get("opening_correction") and not allow_correction
    ):
        raise ConflictError("only an unposted current opening declaration can change")
    return batch


async def replace(
    factory: async_sessionmaker[AsyncSession],
    current: Any,
    identity: uuid.UUID,
    body: OpeningReplace,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> OpeningBatch:
        batch = await matching(db, current, identity, body)
        links = await chunks(db, current, batch)
        ids = [link.journal_id for link in links if link.journal_id]
        journals = list(
            await db.scalars(
                select(Journal).where(Journal.company_id == batch.company_id, Journal.id.in_(ids))
            )
        )
        if any(row.status not in {"DRAFT", "VOID"} for row in journals):
            raise ConflictError(
                "resolve prepared or posted effects before replacing this declaration"
            )
        rev = await revision(db, current, batch)
        plans = await validate(db, current, body.declaration)
        await require_opening_revision_window(db, current, body.declaration.posting_date)
        if body.declaration.replacement_of_id != batch.replacement_of_id:
            raise ConflictError("a revision cannot change its predecessor")
        for row in journals:
            if row.status == "DRAFT":
                await change_row(db, current, "journal", row, "void", status="VOID")
        if batch.journal_id is not None:
            await change_row(db, current, "opening_batch", batch, "update", journal_id=None)
        await write_revision(
            db, current, batch, body.declaration, plans, rev.revision + 1, body.reason
        )
        return batch

    return await command(factory, current, "replace", body, key, mutate, identity)


async def prepare_in_transaction(
    db: AsyncSession, current: Any, batch: OpeningBatch
) -> OpeningBatch:
    await require_opening_revision_window(db, current, batch.posting_date)
    await require_account_identity(db, current, batch)
    count = 0
    first_journal = batch.journal_id
    for link in await chunks(db, current, batch):
        if link.journal_id:
            continue
        plan = opening_plan(link.payload)
        await preview(db, current, plan)
        journal = await create_in_transaction(
            db,
            current,
            JournalCreate(
                document_date=plan.posting_date,
                posting_date=plan.posting_date,
                description=plan.description,
                lines=plan.lines,
            ),
            kind="OPENING",
            source_system="accounting",
            source_type="financial_opening_chunk",
            source_id=str(link.id),
        )
        link.journal_id = journal.id
        link.row_version += 1
        link.updated_by = current.actor.user_id
        audit(db, current, link, "update", before={"journal_id": None})
        if not first_journal:
            first_journal = journal.id
        count += 1
        if count == 2:
            break
    if count:
        await change_row(
            db,
            current,
            "opening_batch",
            batch,
            "update",
            journal_id=first_journal,
            payload=batch.payload
            | {
                "journal_ids": [
                    str(link.journal_id)
                    for link in await chunks(db, current, batch)
                    if link.journal_id
                ]
            },
        )
    return batch


async def execute(
    factory: async_sessionmaker[AsyncSession],
    current: Any,
    identity: uuid.UUID,
    body: OpeningRevisionCommand,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> OpeningBatch:
        batch = await matching(db, current, identity, body)
        return await prepare_in_transaction(db, current, batch)

    return await command(factory, current, "execute", body, key, mutate, identity)


async def finalize(
    factory: async_sessionmaker[AsyncSession],
    current: Any,
    identity: uuid.UUID,
    body: OpeningRevisionCommand,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> OpeningBatch:
        batch = await matching(db, current, identity, body)
        await require_account_identity(db, current, batch)
        await require_opening_revision_window(db, current, batch.posting_date)
        links = await chunks(db, current, batch)
        ids = [link.journal_id for link in links if link.journal_id]
        journals = list(
            await db.scalars(
                select(Journal).where(Journal.company_id == batch.company_id, Journal.id.in_(ids))
            )
        )
        if (
            len(journals) != len(links)
            or not links
            or any(row.status != "POSTED" for row in journals)
        ):
            raise ConflictError(
                "post every reviewed opening journal before finalizing the company opening"
            )
        from accounting.tasks.stock_opening_control import pending

        if await pending(db, batch.company_id):
            raise ConflictError(
                "native execution confirmation is pending; refresh owner status before finalization"
            )
        from accounting.tasks.financial_opening_reconciliation import reconcile

        reconciliation = await reconcile(db, current, batch.id)
        if not reconciliation.ready_to_finalize:
            raise ConflictError(
                "opening reconciliation has unresolved differences; review reconciliation"
            )
        await change_row(
            db,
            current,
            "opening_batch",
            batch,
            "finalize",
            status="FINALIZED",
            finalized_at=utcnow(),
            payload=batch.payload | {"finalization_reason": body.reason},
        )
        return batch

    return await command(factory, current, "finalize", body, key, mutate, identity)


async def void(
    factory: async_sessionmaker[AsyncSession],
    current: Any,
    identity: uuid.UUID,
    body: OpeningRevisionCommand,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> OpeningBatch:
        batch = await matching(db, current, identity, body, allow_correction=True)
        await require_opening_revision_window(db, current, batch.posting_date)
        links = await chunks(db, current, batch)
        ids = [link.journal_id for link in links if link.journal_id]
        journals = list(
            await db.scalars(
                select(Journal).where(Journal.company_id == batch.company_id, Journal.id.in_(ids))
            )
        )
        reversed_ids = set(
            await db.scalars(
                select(Journal.reversal_of_id).where(
                    Journal.company_id == batch.company_id,
                    Journal.reversal_of_id.in_(ids),
                    Journal.status == "POSTED",
                )
            )
        )
        if any(
            row.status not in {"DRAFT", "VOID"} and row.id not in reversed_ids for row in journals
        ):
            raise ConflictError(
                "resolve prepared or posted opening effects through native journal recovery"
            )
        for row in journals:
            if row.status == "DRAFT":
                await change_row(db, current, "journal", row, "void", status="VOID")
        await change_row(
            db,
            current,
            "opening_batch",
            batch,
            "reverse" if batch.payload.get("opening_correction") else "void",
            status="REVERSED" if batch.payload.get("opening_correction") else "VOID",
            reversal_reason=body.reason,
        )
        return batch

    return await command(factory, current, "void", body, key, mutate, identity)
