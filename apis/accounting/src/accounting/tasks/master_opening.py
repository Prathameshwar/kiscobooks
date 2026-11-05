"""Immutable master opening capture and retained evidence for automatic native posting."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import CommandResult, canonical_json
from billing_platform.ids import uuid7
from billing_platform.listing import Page, SortColumn, fetch_page, resolve_sort
from billing_platform.pagination import CursorCodec
from pydantic import BaseModel
from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.master_opening import entry, reject
from accounting.models.financial_opening import FinancialOpeningEntry
from accounting.models.master_opening import MasterOpeningBalance
from accounting.models.masters import Account
from accounting.schemas.financial_opening import OpeningDeclaration, OpeningEntry
from accounting.schemas.master_opening import (
    MasterOpeningCapture,
    MasterOpeningInput,
    MasterOpeningItem,
    MasterOpeningQuery,
)
from accounting.schemas.party_opening import PartyOpeningWithdraw
from accounting.tasks.access import authority_fingerprint
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.financial_opening import (
    audit,
    capture_permissions,
    command,
    require_capture_write,
    require_read,
)
from accounting.tasks.financial_opening_reads import opening_state
from accounting.tasks.party_opening import current_revision


def capture_access(current: Access) -> None:
    require_read(current)
    current.actor.require_scope(
        "accounting.finance.manage", target=ScopePath(company_id=current.context.company_id)
    )
    from accounting.tasks.master_opening_posting import require_posting

    require_posting(current)


async def creation_blockers(db: AsyncSession, current: Access) -> list[str]:
    _, _, blockers = await opening_state(db, current)
    return [
        value
        for value in blockers
        if value
        not in {
            "OPENING_ALREADY_FINALIZED",
            "RESUME_EXISTING_OPENING",
            "LEGACY_ACTIVITY_REQUIRES_REVIEW",
        }
    ]


def declaration(current: Access, value: OpeningEntry, date: dt.date) -> OpeningDeclaration:
    return OpeningDeclaration(
        posting_date=date,
        currency=current.context.base_currency,
        source_system="master-creation",
        source_id=value.source_key,
        covered_through=date - dt.timedelta(days=1),
        reason="Opening captured with master creation",
        entries=[value],
    )


async def replay_access(db: AsyncSession, current: Access, identity: uuid.UUID) -> None:
    capture_access(current)
    row = await company_object(
        db, MasterOpeningBalance, identity, company_id=current.context.company_id
    )
    value = OpeningEntry.model_validate(row.entry)
    await require_capture_write(db, current, declaration(current, value, row.opening_date))


async def capture_metadata(db: AsyncSession, current: Access) -> MasterOpeningCapture:
    require_read(current)
    facts = financial_context(current)
    refused = await creation_blockers(db, current)
    target = ScopePath(company_id=current.context.company_id)
    if not all(
        current.actor.allows_scope(key, target=target)
        for key in ("accounting.finance.manage", "ledger.post_journal", "period.post")
    ):
        refused.append("OPENING_POSTING_PERMISSION_REQUIRED")
    permissions = capture_permissions(current)
    return MasterOpeningCapture(
        company_id=current.context.company_id,
        opening_date=facts.books_begin_date,
        currency=current.context.base_currency,
        blockers=refused,
        can_capture=not refused and all(permissions["journal_lines"].values()),
        capture=MasterOpeningInput.model_json_schema(),
        capture_permissions=permissions,
    )


async def stage(
    db: AsyncSession, current: Access, account_id: uuid.UUID, body: MasterOpeningInput
) -> uuid.UUID:
    capture_access(current)
    account = await company_object(db, Account, account_id, company_id=current.context.company_id)
    facts = financial_context(current)
    refused = await creation_blockers(db, current)
    if refused:
        raise reject("amount", "Opening balances are unavailable: " + ", ".join(refused))
    if account.inventory_affected or account.kind == "INVENTORY_CONTROL":
        raise reject("amount", "Record inventory openings through the stock opening worksheet.")
    currency = (
        account.currency if account.currency_mode == "FIXED" else current.context.base_currency
    )
    if currency is None:
        raise reject("amount", "This account's currency is unavailable.")
    if currency != current.context.base_currency and (
        "multi_currency" not in current.context.features
        or currency not in current.context.allowed_currencies
    ):
        raise reject("amount", "This foreign currency is not enabled for the company.")
    value = entry(
        body,
        account_id=account.id,
        role=account.party_role,
        party=account.kind == "PARTY",
        currency=currency,
        base_currency=current.context.base_currency,
        opening_date=facts.books_begin_date,
    )
    if account.kind == "CASH" and body.side == "CREDIT":
        reason = body.credit_cash_reason or ""
        if len(reason.strip()) < 3 or any(ord(char) < 32 or ord(char) == 127 for char in reason):
            raise reject("credit_cash_reason", "Explain the credit cash opening for review.")
        value.description = reason.strip()
    await require_capture_write(db, current, declaration(current, value, body.opening_date))
    # Keep the evidence bounded independently of the HTTP request-size guard.
    canonical_json(value.model_dump(mode="json"), maximum_bytes=1048576)
    row = MasterOpeningBalance(
        id=uuid7(),
        tenant_id=current.actor.tenant_id,
        company_id=current.context.company_id,
        created_by=current.actor.user_id,
        updated_by=current.actor.user_id,
        row_version=1,
        account_id=account.id,
        source_key=value.source_key,
        status="POSTING",
        opening_date=body.opening_date,
        entry=value.model_dump(mode="json"),
    )
    db.add(row)
    await db.flush()
    audit(db, current, row, "create")
    from accounting.tasks.master_opening_posting import prepare

    await prepare(db, current, row)
    return row.id


def inclusion(revision: uuid.UUID | None) -> Any:
    if revision is None:
        return false()
    return (
        select(FinancialOpeningEntry.id)
        .where(
            FinancialOpeningEntry.company_id == MasterOpeningBalance.company_id,
            FinancialOpeningEntry.revision_id == revision,
            FinancialOpeningEntry.source_key == MasterOpeningBalance.source_key,
        )
        .correlate(MasterOpeningBalance)
        .exists()
    )


def project(row: MasterOpeningBalance, included: bool) -> MasterOpeningItem:
    return MasterOpeningItem.model_validate(
        {name: getattr(row, name) for name in MasterOpeningItem.model_fields if name != "included"}
        | {"included": included}
    )


async def item(db: AsyncSession, current: Access, identity: uuid.UUID) -> MasterOpeningItem:
    require_read(current)
    row = await company_object(
        db, MasterOpeningBalance, identity, company_id=current.context.company_id
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
    return project(row, included)


async def balances(
    db: AsyncSession, current: Access, query: MasterOpeningQuery, secret: bytes
) -> Page[MasterOpeningItem]:
    require_read(current)
    if query.q:
        raise ValidationFailedError("held openings accept typed filters only")
    if query.account_id:
        await company_object(db, Account, query.account_id, company_id=current.context.company_id)
    revision = await current_revision(db, current.context.company_id)
    names = tuple(name for name in MasterOpeningItem.model_fields if name != "included")
    statement = select(
        *(getattr(MasterOpeningBalance, name).label(name) for name in names),
        inclusion(revision).label("included"),
    ).where(MasterOpeningBalance.company_id == current.context.company_id)
    for name in ("account_id", "status"):
        if (value := getattr(query, name)) is not None:
            statement = statement.where(getattr(MasterOpeningBalance, name) == value)
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(MasterOpeningBalance.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    context = canonical_json(
        {
            "resource": "master-opening-balances",
            "company": str(current.context.company_id),
            "tenant": str(current.actor.tenant_id),
            "revision": str(revision),
            "authority": authority_fingerprint(current),
            "query": query.model_dump(mode="json", exclude={"cursor"}),
        }
    ).decode()
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=CursorCodec(secret, context=context),
        project=MasterOpeningItem.model_validate,
    )


async def withdraw(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    identity: uuid.UUID,
    body: PartyOpeningWithdraw,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> MasterOpeningBalance:
        row = await company_object(
            db, MasterOpeningBalance, identity, company_id=current.context.company_id, lock=True
        )
        if row.row_version != body.expected_version or row.status != "PENDING":
            raise ConflictError("The held opening changed; reload it.")
        if (await item(db, current, identity)).included:
            raise ConflictError("This balance is in the opening declaration; change it there.")
        row.status = "WITHDRAWN"
        row.row_version += 1
        row.updated_by = current.actor.user_id
        await db.flush()
        audit(
            db, current, row, "withdraw", before={"status": "PENDING"}, reason=body.reason.strip()
        )
        return row

    return await command(
        factory,
        current,
        "withdraw_master_balance",
        body,
        key,
        mutate,
        identity,
        scope_model=MasterOpeningBalance,
        renderer=item,
    )


async def validate_sources(db: AsyncSession, current: Access, body: OpeningDeclaration) -> None:
    wanted = {
        value.source_key.casefold(): value
        for value in body.entries
        if value.source_key.casefold().startswith("mob-")
    }
    if not wanted:
        return
    from sqlalchemy import func

    rows = list(
        await db.scalars(
            select(MasterOpeningBalance).where(
                MasterOpeningBalance.company_id == current.context.company_id,
                func.lower(MasterOpeningBalance.source_key).in_(wanted),
            )
        )
    )
    if len(rows) != len(wanted):
        raise ValidationFailedError("A held master opening is unavailable for this company.")
    for row in rows:
        if (
            row.status != "PENDING"
            or row.account_id != wanted[row.source_key.casefold()].account_id
            or row.opening_date != body.posting_date
        ):
            raise ValidationFailedError(
                "A withdrawn, moved or differently dated held opening cannot be included."
            )
