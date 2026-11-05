"""One versioned calculation with two interchangeable Trial Balance projections."""

import datetime as dt
import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from importlib.resources import files
from typing import Any

from reporting_contract.contract import Control, Fact

from reports.domain.reporting.contracts import Column, View
from reports.domain.reporting.registry import Registration
from reports.domain.statements import Facts
from reports.domain.trial_balance import VERSION, calculate
from reports.schemas.report_parameters import StatementParameters
from reports.tasks.report_catalog import ReferenceAdapter, columns
from reports.tasks.report_catalog import registration as base_registration


@dataclass(frozen=True)
class TrialBalanceAdapter(ReferenceAdapter):
    def execute(
        self,
        facts: list[Fact],
        generation_id: uuid.UUID,
        values: Mapping[str, Any],
        control: Control,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        query = self.request(generation_id, values, control.coverage_start or dt.date.max)
        return calculate(Facts(facts), query, control.coverage_start or dt.date.max)


def registration() -> Registration[ReferenceAdapter]:
    base = base_registration(
        "TRIAL_BALANCE", StatementParameters, "journal_line", columns("name"), "STATEMENT"
    )
    name = Column("name", "Account / Group")
    currency = Column("currency", "Currency")

    def money(key: str, title: str) -> Column:
        return Column(key, title, "MONEY", "currency")

    default = View(
        "default",
        "Closing balances",
        (name, money("closing_debit", "Debit"), money("closing_credit", "Credit"), currency),
        "STATEMENT",
    )
    detailed = View(
        "detailed",
        "Opening and movement",
        (
            name,
            *tuple(
                money(key, title)
                for key, title in (
                    ("opening_debit", "Opening Dr"),
                    ("opening_credit", "Opening Cr"),
                    ("period_debit", "Period Dr"),
                    ("period_credit", "Period Cr"),
                    ("closing_debit", "Closing Dr"),
                    ("closing_credit", "Closing Cr"),
                )
            ),
            currency,
        ),
        "STATEMENT",
        orientation="LANDSCAPE",
    )
    digest = hashlib.sha256(base.definition.implementation_hash.encode())
    for relative in (
        "domain/trial_balance.py",
        "tasks/trial_balance_catalog.py",
        "queries/trial_balance.py",
    ):
        digest.update(files("reports").joinpath(relative).read_bytes().replace(b"\r\n", b"\n"))
    return Registration(
        replace(
            base.definition,
            version=VERSION,
            views=(default, detailed),
            implementation_hash=digest.hexdigest(),
            description=(
                "Posted account balances with expandable groups, opening and period movement."
            ),
        ),
        TrialBalanceAdapter("TRIAL_BALANCE", StatementParameters),
    )
