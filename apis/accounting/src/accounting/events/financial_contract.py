"""Version-one financial fact contracts for future Billing/Payments consumers."""

import datetime as dt
import uuid
from typing import Literal

from billing_platform.outbox import emit
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.models.fiscal import FiscalPeriod
from accounting.models.ledger import Journal
from accounting.schemas.masters import DecimalInput, Input
from accounting.tasks.journal_drafts import lines

EVENT_TYPES = frozenset({"accounting.journal.posted", "accounting.fiscal_period.changed"})


class PostedLine(Input):
    id: uuid.UUID
    account_id: uuid.UUID
    party_id: uuid.UUID | None
    role: str | None
    component: str
    side: str
    currency: str
    amount: DecimalInput
    exchange_rate: DecimalInput
    base_currency: str
    base_amount: DecimalInput


class JournalPosted(Input):
    version: Literal[1] = 1
    company_id: uuid.UUID
    journal_id: uuid.UUID
    number: str
    kind: str
    posting_date: dt.date
    source_system: str
    source_type: str
    source_id: str
    reversal_of_id: uuid.UUID | None
    authorization_journal_id: uuid.UUID | None
    lines: list[PostedLine] = Field(min_length=2, max_length=200)


class PeriodChanged(Input):
    version: Literal[1] = 1
    company_id: uuid.UUID
    period_id: uuid.UUID
    fiscal_year_id: uuid.UUID
    row_version: int
    start_date: dt.date
    end_date: dt.date
    status: Literal["FUTURE", "OPEN", "SOFT_CLOSED", "CLOSED", "LOCKED"]


async def journal_posted(db: AsyncSession, row: Journal) -> None:
    if row.status != "POSTED" or row.number is None:
        raise ValueError("only committed-shape journal facts may be staged")
    records = await lines(db, row.company_id, row.id)
    payload = JournalPosted(
        company_id=row.company_id,
        journal_id=row.id,
        number=row.number,
        kind=row.kind,
        posting_date=row.posting_date,
        source_system=row.source_system,
        source_type=row.source_type,
        source_id=row.source_id,
        reversal_of_id=row.reversal_of_id,
        authorization_journal_id=row.authorization_journal_id,
        lines=[
            PostedLine.model_validate({key: getattr(line, key) for key in PostedLine.model_fields})
            for line in records
        ],
    )
    emit(
        db,
        aggregate_type="accounting.journal",
        aggregate_id=row.id,
        event_type="accounting.journal.posted",
        tenant_id=row.tenant_id,
        payload=payload.model_dump(mode="json"),
    )


def period_changed(db: AsyncSession, row: FiscalPeriod) -> None:
    payload = PeriodChanged.model_validate(
        {
            "company_id": row.company_id,
            "period_id": row.id,
            "fiscal_year_id": row.fiscal_year_id,
            "row_version": row.row_version,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "status": row.status,
        }
    )
    emit(
        db,
        aggregate_type="accounting.fiscal_period",
        aggregate_id=row.id,
        event_type="accounting.fiscal_period.changed",
        tenant_id=row.tenant_id,
        payload=payload.model_dump(mode="json"),
    )
