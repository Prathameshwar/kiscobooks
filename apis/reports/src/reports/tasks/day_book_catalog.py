"""A materialized Day Book definition, separate from retained ledger runtimes."""

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from reporting_contract.contract import Control, Fact

from reports.domain.day_book import Parameters, calculate_activity
from reports.domain.reporting.contracts import Column, ReportDefinition, View, fingerprint
from reports.domain.reporting.registry import Registration
from reports.tasks.access import INPUT_PERMISSIONS
from reports.tasks.report_catalog import ReferenceAdapter, implementation_hash


@dataclass(frozen=True)
class DayBookAdapter(ReferenceAdapter):
    def execute(
        self,
        facts: list[Fact],
        generation_id: uuid.UUID,
        values: Mapping[str, Any],
        control: Control,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return calculate_activity(facts, generation_id, dict(values), control)


def registration() -> Registration[ReferenceAdapter]:
    handler = DayBookAdapter("DAY_BOOK_ACTIVITY", Parameters)
    common = (
        Column("date", "Posting date", "DATE"),
        Column("kind", "Voucher kind"),
        Column("number", "Voucher number"),
        Column("particulars", "Particulars"),
        Column("currency", "Currency"),
        Column("debit", "Debit", "MONEY", "currency"),
        Column("credit", "Credit", "MONEY", "currency"),
        Column("narration", "Narration"),
        Column("status", "Status"),
    )
    accounting = (
        common[:4]
        + (
            Column("account_code", "Account code"),
            Column("account_name", "Account"),
        )
        + common[4:]
    )
    identity = hashlib.sha256()
    identity.update(implementation_hash().encode())
    for path in ("domain/day_book.py", "tasks/day_book_catalog.py"):
        identity.update(files("reports").joinpath(path).read_bytes().replace(b"\r\n", b"\n"))
    return Registration(
        ReportDefinition(
            code="DAY_BOOK_ACTIVITY",
            version=1,
            title="Day Book",
            description="Whole vouchers and journal entries from a verified company snapshot.",
            implementation_hash=identity.hexdigest(),
            parameter_schema_hash=fingerprint(handler.parameters()),
            datasets=("journal_line",),
            metrics=(),
            permissions=tuple(sorted(INPUT_PERMISSIONS)),
            views=(
                View("default", "Vouchers", common),
                View("accounting", "Accounting", accounting),
            ),
            resource_class="BULK",
        ),
        handler,
    )
