"""Typed hierarchy reads and bounded presentation choices for frozen Trial Balance."""

import uuid
from typing import Annotated, Literal

from billing_platform.listing import PageMeta
from pydantic import Field
from reporting_contract.contract import Contract

from reports.schemas.framework import DrilldownLink
from reports.schemas.trial_balance_options import NodeKey, Period

Amount = Annotated[str, Field(pattern=r"^\d{1,34}\.\d{4}$", max_length=39)]
Difference = Annotated[str, Field(pattern=r"^-?\d{1,34}\.\d{4}$", max_length=40)]


class TrialAmounts(Contract):
    opening_debit: Amount
    opening_credit: Amount
    period_debit: Amount
    period_credit: Amount
    closing_debit: Amount
    closing_credit: Amount


class TrialTotals(TrialAmounts):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    account_count: int = Field(ge=0)
    opening_difference: Difference
    period_difference: Difference
    closing_difference: Difference
    display_residual: dict[str, Difference] = Field(default_factory=dict)


class TrialNode(TrialAmounts):
    row_kind: Literal["HEAD", "GROUP", "ACCOUNT"]
    node_key: NodeKey
    parent_key: str = Field(max_length=48)
    code: str = Field(max_length=40)
    name: str = Field(max_length=160)
    period: Period
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    depth: int = Field(ge=0)
    child_count: int = Field(ge=0)
    group_child_count: int = Field(ge=0)
    account_count: int = Field(ge=0)
    is_zero: bool
    head_id: uuid.UUID
    group_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    display_residual: dict[str, str] = Field(default_factory=dict)


class TrialHierarchyRow(Contract):
    ordinal: int = Field(ge=1)
    data: TrialNode
    drilldowns: tuple[DrilldownLink, ...] = ()


class TrialHierarchyPage(Contract):
    items: list[TrialHierarchyRow]
    page: PageMeta
    summary: TrialTotals
    periods: tuple[Period, ...]
