"""Opening balances that arrive with a party import wait here for the opening declaration.

The import creates the party's ledger account and one held line. Nothing is posted and nothing is
added to a declaration: the declaration must balance as a whole, and only the actor reviewing it
can say what balances these lines. The workspace lists held lines and copies the ones the actor
chooses into the declaration they are building.
"""

import datetime as dt
import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import CommandResult, canonical_json
from billing_platform.ids import uuid7
from billing_platform.listing import Page, SortColumn, fetch_page, resolve_sort
from billing_platform.outbox import audit_payload, emit
from billing_platform.pagination import CursorCodec
from pydantic import BaseModel
from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.config import Settings
from accounting.domain import party_opening as rules
from accounting.events.audit_contract import audit_event
from accounting.models.financial_opening import FinancialOpeningChunk, FinancialOpeningEntry
from accounting.models.ledger import Journal
from accounting.models.masters import Account
from accounting.models.party_opening import PartyOpeningBalance
from accounting.models.subledger import OpeningBatch
from accounting.resources import BY_NAME
from accounting.schemas.financial_opening import (
    OnAccountOpeningDocument,
    OpeningDeclaration,
    OpeningDocument,
    OpeningEntry,
)
from accounting.schemas.masters import AccountCreate
from accounting.schemas.party_opening import (
    OPENING_FIELDS,
    PartyOpeningItem,
    PartyOpeningQuery,
    PartyOpeningWithdraw,
    ReadyPartyCreate,
)
from accounting.tasks.access import authority_fingerprint, authorize
from accounting.tasks.commands import create_active
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.financial_opening import command, require_capture_write, require_read
from accounting.tasks.financial_opening_reads import opening_state
from accounting.tasks.party_ledger import (
    LedgerPlan,
    account_values,
    create_party_ledger,
    standard_group,
)


def audit(
    db: AsyncSession,
    access: Access,
    row: PartyOpeningBalance,
    action: str,
    *,
    reason: str | None = None,
) -> None:
    event = audit_event("party_opening_balance", action)
    # Creation records the whole held line; withdrawal changes only its status.
    changes: dict[str, Any] = {
        "status": {"from": None if action == "create" else "PENDING", "to": row.status}
    }
    if action == "create":
        changes |= {
            "party_id": {"from": None, "to": str(row.party_id)},
            "role": {"from": None, "to": row.role},
            "account_id": {"from": None, "to": str(row.account_id)},
            "side": {"from": None, "to": row.side},
            "currency": {"from": None, "to": row.currency},
            "amount": {"from": None, "to": str(row.amount)},
            "base_amount": {"from": None, "to": str(row.base_amount)},
            "base_currency": {"from": None, "to": access.context.base_currency},
        }
    emit(
        db,
        aggregate_type="accounting.party_opening_balance",
        aggregate_id=row.id,
        tenant_id=access.actor.tenant_id,
        event_type=event,
        payload=audit_payload(
            action=event,
            category="money",
            entity_type="accounting.party_opening_balance",
            entity_id=row.id,
            actor_user_id=access.actor.user_id,
            company_id=row.company_id,
            changes=changes,
            reason=reason,
        )
        | {"actor_type": "user"},
    )


async def is_resumable(db: AsyncSession, batch: OpeningBatch | None) -> bool:
    """An unfinished worksheet declaration with no posted journal can still take new lines."""
    if batch is None or batch.status != "DRAFT" or not batch.payload.get("workspace_revision_id"):
        return False
    posted = await db.scalar(
        select(Journal.id)
        .join(FinancialOpeningChunk, FinancialOpeningChunk.journal_id == Journal.id)
        .where(
            FinancialOpeningChunk.company_id == batch.company_id,
            FinancialOpeningChunk.batch_id == batch.id,
            Journal.status == "POSTED",
        )
        .limit(1)
    )
    return posted is None


async def stage(
    db: AsyncSession,
    access: Access,
    settings: Settings,
    *,
    party_id: uuid.UUID,
    role: rules.Role,
    body: ReadyPartyCreate,
) -> dict[str, Any]:
    """Create the party's ledger account, and hold its opening line when the row carries one.

    The account is never optional: a row with no opening columns gets the standard one and
    nothing is held. Runs inside the import's aggregate transaction, so a failure here also
    discards the party.
    """
    if all(getattr(body, name) is None for name in OPENING_FIELDS):
        # Most rows carry no balance, and need no financial context at all.
        plain = await create_party_ledger(
            db,
            access,
            settings,
            party_id=party_id,
            role=role,
            party_code=body.code,
            party_name=body.name,
        )
        return {"account_id": str(plain.id)}
    facts = financial_context(access)
    covered_through = facts.books_begin_date - dt.timedelta(days=1)
    staged = rules.plan(
        role=role,
        balance_type=body.opening_balance_type,
        amount=body.opening_amount,
        currency=body.opening_currency,
        exchange_rate=body.opening_exchange_rate,
        base_amount=body.opening_base_amount,
        account_code=body.opening_account_code,
        bill_reference=body.opening_bill_reference,
        bill_date=body.opening_bill_date,
        due_date=body.opening_bill_due_date,
        base_currency=access.context.base_currency,
        covered_through=covered_through,
    )
    if staged is None:
        return {}
    company = access.context.company_id
    # Capturing a balance is financial authority, separate from the right to import parties.
    access.actor.require_scope("accounting.finance.manage", target=ScopePath(company_id=company))
    for action in ("manage", "read"):
        authorize(access, BY_NAME["account"], action)
    batch, _, blockers = await opening_state(db, access)
    closed = rules.refused_blockers(blockers, resumable=await is_resumable(db, batch))
    if closed:
        raise rules.reject(
            "opening_amount", "opening balances can no longer be added: " + ", ".join(closed)
        )
    foreign = staged.currency != access.context.base_currency
    if foreign:
        if "multi_currency" not in access.context.features:
            raise rules.reject("opening_currency", "multicurrency is not enabled for this company")
        if staged.currency not in access.context.allowed_currencies:
            raise rules.reject("opening_currency", "this currency is not enabled for the company")
    group = await standard_group(db, company, role)
    if group is None:
        raise rules.reject(
            "opening_amount",
            "the standard debtors/creditors account group is missing; create the ledger account "
            "yourself and use the account opening import",
        )
    code = body.opening_account_code or body.code
    if await db.scalar(
        select(Account.id).where(Account.company_id == company, Account.code == code)
    ):
        raise rules.reject("opening_account_code", "a ledger account already uses this code")
    account = await create_active(
        db,
        access,
        BY_NAME["account"],
        AccountCreate.model_validate(
            account_values(
                LedgerPlan(
                    code,
                    body.name,
                    group.id,
                    "FIXED" if foreign else "BASE",
                    staged.currency if foreign else None,
                ),
                party_id=party_id,
                role=role,
            )
        ),
        settings,
    )
    await db.flush()
    key = rules.source_key(party_id)
    document: OpeningDocument | OnAccountOpeningDocument
    if staged.document_kind == "ON_ACCOUNT":
        document = OnAccountOpeningDocument(
            reference=staged.document_reference,
            amount=staged.amount,
            document_kind="ON_ACCOUNT",
            base_amount=staged.base_amount if foreign else None,
        )
    else:
        assert staged.document_date is not None and staged.due_date is not None
        document = OpeningDocument(
            reference=staged.document_reference,
            amount=staged.amount,
            document_date=staged.document_date,
            due_date=staged.due_date,
            document_kind=staged.document_kind,
            base_amount=staged.base_amount if foreign else None,
        )
    # The held line must be something the workspace could capture, for this actor, right now.
    await require_capture_write(
        db,
        access,
        OpeningDeclaration(
            posting_date=facts.books_begin_date,
            currency=access.context.base_currency,
            source_system="party-import",
            source_id=key,
            covered_through=covered_through,
            reason="Opening balance captured with a party import",
            entries=[
                OpeningEntry(
                    source_key=key,
                    account_id=account.id,
                    side=staged.side,
                    currency=staged.currency,
                    amount=staged.amount,
                    exchange_rate=staged.exchange_rate,
                    base_amount=staged.base_amount if foreign else None,
                    documents=[document],
                )
            ],
        ),
    )
    row = PartyOpeningBalance(
        id=uuid7(),
        tenant_id=access.actor.tenant_id,
        company_id=company,
        created_by=access.actor.user_id,
        updated_by=access.actor.user_id,
        row_version=1,
        party_id=party_id,
        role=role,
        account_id=account.id,
        source_key=key,
        status="PENDING",
        side=staged.side,
        currency=staged.currency,
        amount=staged.amount,
        exchange_rate=staged.exchange_rate,
        base_amount=staged.base_amount,
        document_kind=staged.document_kind,
        document_reference=staged.document_reference,
        document_date=staged.document_date,
        due_date=staged.due_date,
    )
    db.add(row)
    await db.flush()
    audit(db, access, row, "create")
    return {"account_id": str(account.id), "party_opening_balance_id": str(row.id)}


async def current_revision(db: AsyncSession, company: uuid.UUID) -> uuid.UUID | None:
    from accounting.tasks.master_opening_posting import company_batches

    batch = await db.scalar(
        select(OpeningBatch)
        .where(
            OpeningBatch.company_id == company,
            OpeningBatch.status.in_(["DRAFT", "FINALIZED"]),
            company_batches(),
        )
        .order_by(OpeningBatch.id.desc())
        .limit(1)
    )
    marker = batch.payload.get("workspace_revision_id") if batch else None
    return uuid.UUID(marker) if marker else None


def in_declaration(revision: uuid.UUID | None) -> Any:
    if revision is None:
        return false()
    # Built from the ORM entity so the tenant filter reaches the correlated subquery.
    return (
        select(FinancialOpeningEntry.id)
        .where(
            FinancialOpeningEntry.company_id == PartyOpeningBalance.company_id,
            FinancialOpeningEntry.revision_id == revision,
            FinancialOpeningEntry.source_key == PartyOpeningBalance.source_key,
        )
        .correlate(PartyOpeningBalance)
        .exists()
    )


async def balances(
    db: AsyncSession, current: Access, query: PartyOpeningQuery, secret: bytes
) -> Page[PartyOpeningItem]:
    require_read(current)
    if query.q:
        raise ValidationFailedError("held party balances accept typed filters only")
    company = current.context.company_id
    revision = await current_revision(db, company)
    names = tuple(name for name in PartyOpeningItem.model_fields if name != "included")
    statement = select(
        *(getattr(PartyOpeningBalance, name).label(name) for name in names),
        in_declaration(revision).label("included"),
    ).where(PartyOpeningBalance.company_id == company)
    for key in ("status", "role", "party_id"):
        if (value := getattr(query, key)) is not None:
            statement = statement.where(getattr(PartyOpeningBalance, key) == value)
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(PartyOpeningBalance.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    context = canonical_json(
        {
            "resource": "party-opening-balances",
            "company": str(company),
            "tenant": str(current.actor.tenant_id),
            "revision": str(revision),
            "authority": authority_fingerprint(current),
            "query": query.model_dump(mode="json", exclude={"cursor"}),
        }
    ).decode()

    def project(row: Mapping[str, Any]) -> PartyOpeningItem:
        data = dict(row)
        for key in ("amount", "exchange_rate", "base_amount"):
            data[key] = format(Decimal(data[key]), "f")
        return PartyOpeningItem.model_validate(data)

    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=CursorCodec(secret, context=context),
        project=project,
    )


async def item(db: AsyncSession, current: Access, identity: uuid.UUID) -> BaseModel:
    row = await company_object(
        db, PartyOpeningBalance, identity, company_id=current.context.company_id
    )
    revision = await current_revision(db, row.company_id)
    included = bool(
        revision
        and await db.scalar(
            select(FinancialOpeningEntry.id).where(
                FinancialOpeningEntry.company_id == row.company_id,
                FinancialOpeningEntry.revision_id == revision,
                FinancialOpeningEntry.source_key == row.source_key,
            )
        )
    )
    return PartyOpeningItem.model_validate(
        {name: getattr(row, name) for name in PartyOpeningItem.model_fields if name != "included"}
        | {
            key: format(getattr(row, key), "f")
            for key in ("amount", "exchange_rate", "base_amount")
        }
        | {"included": included}
    )


async def withdraw(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    identity: uuid.UUID,
    body: PartyOpeningWithdraw,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> PartyOpeningBalance:
        row = await company_object(
            db, PartyOpeningBalance, identity, company_id=current.context.company_id, lock=True
        )
        if row.row_version != body.expected_version:
            raise ConflictError("the held balance changed; reload it")
        if row.status != "PENDING":
            raise ConflictError("this balance was already withdrawn")
        revision = await current_revision(db, row.company_id)
        if revision and await db.scalar(
            select(FinancialOpeningEntry.id).where(
                FinancialOpeningEntry.company_id == row.company_id,
                FinancialOpeningEntry.revision_id == revision,
                FinancialOpeningEntry.source_key == row.source_key,
            )
        ):
            raise ConflictError("this balance is in the opening declaration; change it there")
        row.status = "WITHDRAWN"
        row.row_version += 1
        row.updated_by = current.actor.user_id
        await db.flush()
        audit(db, current, row, "withdraw", reason=body.reason.strip())
        return row

    return await command(
        factory,
        current,
        "withdraw_party_balance",
        body,
        key,
        mutate,
        identity,
        scope_model=PartyOpeningBalance,
        renderer=item,
    )
