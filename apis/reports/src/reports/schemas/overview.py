"""Covered posted activity and as-of positions over one verified owner cut."""

import datetime as dt
import uuid

from pydantic import Field
from reporting_contract.contract import Contract


class OverviewTotals(Contract):
    cash: str
    bank: str
    net_receivable: str
    net_payable: str
    income: str
    expenses: str
    net_income: str


class OverviewDay(Contract):
    date: dt.date
    income: str
    expenses: str


class OverviewPosition(Contract):
    """Closing cash plus bank balance at the end of one day."""

    date: dt.date
    cash_and_bank: str


class OverviewBuckets(Contract):
    """Bills by days past due at the period end; ``unknown`` has no due date."""

    current: str
    days_1_30: str
    days_31_60: str
    days_61_90: str
    days_over_90: str
    unknown: str


class OverviewParty(Contract):
    """One party, however many ledgers it holds: balances are summed across them.

    ``name`` is the party's own name (a ledger's name only if the source carries none).
    ``outstanding`` is bills less unapplied credit; ``overdue`` is bills past due.
    """

    party_id: uuid.UUID
    name: str
    outstanding: str
    overdue: str


class OverviewOpenItems(Contract):
    """One role's open bills: ``gross`` less ``advances`` is ``net``; ``overdue`` is gross."""

    gross: str
    advances: str
    net: str
    overdue: str
    buckets: OverviewBuckets
    parties: list[OverviewParty]


class OverviewLedger(Contract):
    """An expense ledger whose net for the period is a positive amount (a debit balance)."""

    account_id: uuid.UUID
    name: str
    amount: str


class CompanyOverview(Contract):
    """Covered posted activity and as-of positions over one verified owner cut.

    ``top_expenses`` lists at most five ledgers with a positive net. ``other_expenses`` is the
    net of *every other* expense ledger, so it can be negative when one of them ends with a
    credit balance (purchase returns, say). It is never clamped:
    ``sum(top_expenses.amount) + other_expenses == totals.expenses`` exactly.
    """

    company_id: uuid.UUID
    generation_id: uuid.UUID
    snapshot_id: uuid.UUID
    source_created_at: dt.datetime
    fiscal_year_id: uuid.UUID
    year_start: dt.date
    coverage_start: dt.date
    date_from: dt.date
    date_to: dt.date
    currency: str
    earlier_history_unavailable: bool
    totals: OverviewTotals
    series: list[OverviewDay]
    position: list[OverviewPosition]
    receivables: OverviewOpenItems
    payables: OverviewOpenItems
    top_expenses: list[OverviewLedger]
    other_expenses: str = Field(
        description=(
            "Net of every expense ledger outside top_expenses; may be negative. "
            "sum(top_expenses) + other_expenses equals totals.expenses exactly."
        )
    )
