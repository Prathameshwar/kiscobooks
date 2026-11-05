"""Bounded source-component scans pinned to a verified Accounting cut."""

import datetime as dt
import itertools
import uuid
from typing import Any

from billing_platform.errors import ConflictError
from reporting_contract.contract import Manifest
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from reports.models.core import ReportGeneration
from reports.models.framework import ReportJob
from reports.models.source_versions import ReportFactVersion, ReportSourceCut
from reports.queries.source_versions import COMPONENT_BYTES, SourceView, bounded_rows
from reports.tasks.gstr3b_catalog import result


async def execute(
    db: AsyncSession, generation: ReportGeneration, job: ReportJob, maximum: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cut = await db.scalar(
        select(ReportSourceCut).where(
            ReportSourceCut.company_id == generation.company_id,
            ReportSourceCut.generation_id == generation.id,
        )
    )
    if cut is None or cut.verification is None or not generation.manifest:
        raise ConflictError("GSTR-3B requires a verified native source cut")
    source = SourceView(generation.company_id, cut.epoch_id, cut.sequence)
    captured = job.parameters["_gst_context"]
    records = await bounded_rows(
        db,
        source.rows("gst_return_record").where(
            ReportFactVersion.data["registration_id"].as_string() == captured["registration"]["id"],
            ReportFactVersion.data["return_date"].as_string() >= captured["date_from"],
            ReportFactVersion.data["return_date"].as_string() <= captured["date_to"],
        ),
        maximum=maximum,
    )
    values = [row.data | {"id": str(row.source_id)} for row in records if row.data]
    supplies = await bounded_rows(
        db,
        source.rows("invoice_supply_fact").where(
            ReportFactVersion.data["company_registration_id"].as_string()
            == captured["registration"]["id"],
            or_(
                ReportFactVersion.data["tax_point_date"].as_string().is_(None),
                (ReportFactVersion.data["tax_point_date"].as_string() >= captured["date_from"])
                & (ReportFactVersion.data["tax_point_date"].as_string() <= captured["date_to"]),
            ),
        ),
        maximum=maximum,
    )
    allocated = {
        row["source_id"]
        for row in values
        if row["source_entity"] == "invoice_supply_fact"
        and row["category"] not in {"3.2", "COVERAGE"}
    }
    unresolved = [
        str(row.source_id)
        for row in supplies
        if row.data
        and row.data.get("company_registration_id") == captured["registration"]["id"]
        and (
            row.data["tax_point_date"] is None
            or captured["date_from"] <= row.data["tax_point_date"] <= captured["date_to"]
        )
        and str(row.source_id) not in allocated
    ]
    actions = await bounded_rows(
        db,
        source.rows("invoice_credit_action").where(
            ReportFactVersion.data["event_date"].as_string() >= captured["date_from"],
            ReportFactVersion.data["event_date"].as_string() <= captured["date_to"],
        ),
        maximum=maximum,
    )
    allocated_actions = {
        row["source_id"] for row in values if row["source_entity"] == "invoice_credit_action"
    }

    async def related(kind: str, identities: set[str]) -> dict[str, dict[str, Any]]:
        related_rows: dict[str, dict[str, Any]] = {}
        size = 0
        for batch in itertools.batched(sorted(identities), 200):
            found = await source.lookup(db, kind, [uuid.UUID(identity) for identity in batch])
            for identity, item in found.items():
                if item.data:
                    related_rows[str(identity)] = item.data
                    size += item.wire_bytes
            if len(related_rows) > maximum or size > COMPONENT_BYTES:
                raise ConflictError("GST source relationships exceed their supported bound")
        return related_rows

    action_journals = await related(
        "journal",
        {row.data["journal_id"] for row in actions if row.data and row.data["journal_id"]},
    )
    actions = [
        row
        for row in actions
        if row.data
        and row.data["kind"] != "VERIFY"
        and action_journals.get(row.data["journal_id"], {}).get("status") == "POSTED"
    ]
    components = await related(
        "invoice_tax_component", {row.data["component_id"] for row in actions if row.data}
    )
    action_supplies = await related(
        "invoice_supply_fact", {item["supply_id"] for item in components.values()}
    )
    action_registration = {
        str(row.source_id): action_supplies.get(
            components.get(row.data["component_id"], {}).get("supply_id", ""), {}
        ).get("company_registration_id")
        for row in actions
        if row.data
    }
    unresolved.extend(
        str(row.source_id)
        for row in actions
        if row.data
        and action_registration.get(str(row.source_id)) == captured["registration"]["id"]
        and row.data["kind"] != "VERIFY"
        and str(row.source_id) not in allocated_actions
    )
    source_journal = aliased(ReportFactVersion)
    legacy = await bounded_rows(
        db,
        source.rows("journal_tax")
        .join(
            source_journal,
            (ReportFactVersion.relation_id == source_journal.source_id)
            & source.predicate(source_journal)
            & (source_journal.entity == "journal"),
        )
        .where(
            ReportFactVersion.data["company_registration_id"].as_string()
            == captured["registration"]["id"],
            source_journal.source_status == "POSTED",
            source_journal.posting_date >= dt.date.fromisoformat(captured["date_from"]),
            source_journal.posting_date <= dt.date.fromisoformat(captured["date_to"]),
        ),
        maximum=maximum,
    )
    journal_allocated = {row["source_id"] for row in values if row["source_entity"] == "journal"}
    unresolved.extend(
        row.data["journal_id"]
        for row in legacy
        if row.data and row.data["journal_id"] not in journal_allocated
    )
    supply_by_id = {str(row.source_id): row.data for row in supplies if row.data}
    action_by_id = {str(row.source_id): row.data for row in actions if row.data}
    supply_by_id.update(
        await related(
            "invoice_supply_fact",
            {
                row["source_id"]
                for row in values
                if row["source_entity"] == "invoice_supply_fact"
                and row["source_id"] not in supply_by_id
            },
        )
    )
    action_by_id.update(
        await related(
            "invoice_credit_action",
            {
                row["source_id"]
                for row in values
                if row["source_entity"] == "invoice_credit_action"
                and row["source_id"] not in action_by_id
            },
        )
    )
    for row in values:
        if row["source_entity"] == "invoice_supply_fact":
            supply_data = supply_by_id.get(row["source_id"])
            if supply_data:
                row["invoice_id"] = supply_data["invoice_id"]
        elif row["source_entity"] == "invoice_credit_action":
            action_data = action_by_id.get(row["source_id"])
            if action_data:
                row["invoice_id"] = action_data["invoice_id"]
                row["journal_id"] = action_data.get("journal_id")
        elif row["source_entity"] == "journal":
            row["journal_id"] = row["source_id"]
    invoice_ids_for_links = {row["invoice_id"] for row in values if row.get("invoice_id")}
    if invoice_ids_for_links:
        invoice_by_id = await related("invoice_record", invoice_ids_for_links)
        intent_by_id = await related(
            "voucher_money_intent", {item["intent_id"] for item in invoice_by_id.values()}
        )
        for row in values:
            invoice = invoice_by_id.get(row.get("invoice_id", ""))
            intent = intent_by_id.get(invoice["intent_id"]) if invoice else None
            if intent:
                row["voucher_id"] = intent["voucher_id"]
                row["journal_id"] = intent.get("journal_id")
    return result(
        values, job.parameters, Manifest.model_validate(generation.manifest).sequence, unresolved
    )
