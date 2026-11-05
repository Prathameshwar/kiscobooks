"""Period-indexed GSTR-1 extraction from a reconciled Accounting snapshot."""

import datetime as dt
import itertools
import uuid
from collections import defaultdict
from typing import Any

from billing_platform.errors import ConflictError
from reporting_contract.contract import Manifest
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from reports.models.core import ReportGeneration
from reports.models.framework import ReportJob
from reports.models.source_versions import ReportFactVersion, ReportSourceCut
from reports.queries.source_versions import COMPONENT_BYTES, SourceView, bounded_rows
from reports.tasks.gstr1_catalog import result


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
        raise ConflictError("GSTR-1 requires a verified native source cut")
    source = SourceView(generation.company_id, cut.epoch_id, cut.sequence)
    captured = job.parameters["_gst_context"]
    registration_id = uuid.UUID(captured["registration"]["id"])
    start, end = (
        dt.date.fromisoformat(captured["date_from"]),
        dt.date.fromisoformat(captured["date_to"]),
    )
    found = await bounded_rows(
        db,
        source.rows("gst_outward_record").where(
            ReportFactVersion.relation_id == registration_id,
            ReportFactVersion.posting_date >= start,
            ReportFactVersion.posting_date <= end,
        ),
        maximum=maximum,
    )
    records = [row.data | {"id": str(row.source_id)} for row in found if row.data]

    relation_bytes: dict[str, int] = defaultdict(int)
    relation_ids: dict[str, set[str]] = defaultdict(set)

    def retain(entity: str, item: ReportFactVersion) -> None:
        identity = str(item.source_id)
        if identity not in relation_ids[entity]:
            relation_ids[entity].add(identity)
            relation_bytes[entity] += item.wire_bytes
        if len(relation_ids[entity]) > maximum or relation_bytes[entity] > COMPONENT_BYTES:
            raise ConflictError("GSTR-1 source relationships exceed their supported bound")

    async def related(entity: str, identities: set[str]) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for batch in itertools.batched(sorted(identities), 200):
            items = await source.lookup(db, entity, [uuid.UUID(identity) for identity in batch])
            for identity, item in items.items():
                if item.data:
                    retain(entity, item)
                    output[str(identity)] = item.data | {"id": str(identity)}
        return output

    originals = await related(
        "gst_outward_record",
        {row["original_record_id"] for row in records if row["original_record_id"]},
    )
    for _ in range(32):
        parents = {
            row["original_record_id"] for row in originals.values() if row.get("original_record_id")
        } - originals.keys()
        if not parents:
            break
        additional = await related("gst_outward_record", parents)
        if not additional:
            break
        originals.update(additional)
    else:
        raise ConflictError("GSTR-1 amendment history exceeds its supported depth")
    baselines = {
        row["original_record_id"]
        for row in records
        if row["kind"] == "AMENDMENT" and row.get("original_record_id")
    }
    for batch in itertools.batched(sorted(baselines), 200):
        previous = await bounded_rows(
            db,
            source.rows("gst_outward_record").where(
                ReportFactVersion.origin_id.in_([uuid.UUID(identity) for identity in batch]),
                ReportFactVersion.source_status == "AMENDMENT",
                ReportFactVersion.posting_date < start,
            ),
            maximum=maximum,
        )
        for history in previous:
            if history.data:
                retain("gst_outward_record", history)
                originals[str(history.source_id)] = history.data | {"id": str(history.source_id)}
    original_invoice = aliased(ReportFactVersion)

    def outward(model: Any) -> Any:
        original_sales = (
            select(original_invoice.id)
            .where(
                source.predicate(original_invoice),
                original_invoice.entity == "invoice_record",
                original_invoice.source_id == model.origin_id,
                original_invoice.data["kind"].as_string() == "SALES",
            )
            .exists()
        )
        return or_(
            model.data["kind"].as_string() == "SALES",
            and_(model.data["kind"].as_string().in_(("CREDIT_NOTE", "DEBIT_NOTE")), original_sales),
        )

    invoices = await bounded_rows(
        db,
        source.rows("invoice_record").where(
            ReportFactVersion.posting_date >= start,
            ReportFactVersion.posting_date <= end,
            outward(ReportFactVersion),
        ),
        maximum=maximum,
    )
    invoice_data = {
        str(row.source_id): row.data | {"id": str(row.source_id)} for row in invoices if row.data
    }
    native_ids = {row["source_id"] for row in records if row["source_entity"] == "invoice_record"}
    invoice_data.update(await related("invoice_record", native_ids - invoice_data.keys()))
    invoice_data.update(
        await related(
            "invoice_record",
            {
                row["source_invoice_id"]
                for row in invoice_data.values()
                if row.get("source_invoice_id")
            },
        )
    )
    supply_invoice = aliased(ReportFactVersion)
    eligible_supply = (
        select(supply_invoice.id)
        .where(
            source.predicate(supply_invoice),
            supply_invoice.entity == "invoice_record",
            supply_invoice.source_id == ReportFactVersion.relation_id,
            outward(supply_invoice),
        )
        .exists()
    )
    supplies = await bounded_rows(
        db,
        source.rows("invoice_supply_fact").where(
            ReportFactVersion.data["company_registration_id"].as_string() == str(registration_id),
            eligible_supply,
            or_(
                and_(
                    ReportFactVersion.data["tax_point_date"].as_string() >= start.isoformat(),
                    ReportFactVersion.data["tax_point_date"].as_string() <= end.isoformat(),
                ),
                and_(
                    ReportFactVersion.data["tax_point_date"].as_string().is_(None),
                    ReportFactVersion.relation_id.in_(
                        [uuid.UUID(identity) for identity in invoice_data]
                    ),
                ),
            ),
        ),
        maximum=maximum,
    )
    missing_invoices = {
        row.data["invoice_id"] for row in supplies if row.data
    } - invoice_data.keys()
    invoice_data.update(await related("invoice_record", missing_invoices))
    invoice_data.update(
        await related(
            "invoice_record",
            {
                row["source_invoice_id"]
                for row in invoice_data.values()
                if row.get("source_invoice_id")
            }
            - invoice_data.keys(),
        )
    )
    intents = await related(
        "voucher_money_intent", {row["intent_id"] for row in invoice_data.values()}
    )
    unresolved: set[str] = set()
    for supply in supplies:
        if not supply.data:
            continue
        identity = supply.data["invoice_id"]
        invoice = invoice_data.get(identity)
        if not invoice:
            continue
        original = invoice_data.get(invoice.get("source_invoice_id", ""))
        if invoice["kind"] != "SALES" and not (
            invoice["kind"] in {"CREDIT_NOTE", "DEBIT_NOTE"}
            and original
            and original["kind"] == "SALES"
        ):
            continue
        intent = intents.get(invoice["intent_id"])
        if intent and intent["status"] == "COMMITTED" and identity not in native_ids:
            unresolved.add(identity)
    for row in records:
        if row["source_entity"] == "invoice_record":
            invoice = invoice_data.get(row["source_id"])
            intent = intents.get(invoice["intent_id"]) if invoice else None
            if intent:
                row["voucher_id"] = intent["voucher_id"]
                row["journal_id"] = intent.get("journal_id") or ""
    comparison = None
    if job.parameters.get("comparison_job_id"):
        from reports.domain.gstr3b import CALCULATION_VERSION as THREE_B_CALCULATION_VERSION

        other = await db.scalar(
            select(ReportJob).where(
                ReportJob.company_id == generation.company_id,
                ReportJob.id == uuid.UUID(job.parameters["comparison_job_id"]),
            )
        )
        if (
            other is None
            or other.actor_id != job.actor_id
            or other.permission_hash != job.permission_hash
            or other.status != "COMPLETE"
            or not other.result
            or other.definition["code"] != "GSTR3B"
            or other.result.get("evidence", {}).get("gstr3b", {}).get("calculation_version")
            != THREE_B_CALCULATION_VERSION
            or (
                other.parameters["registration_id"] != job.parameters["registration_id"]
                or other.parameters["period"] != job.parameters["period"]
                or other.generation_id != generation.id
            )
        ):
            raise ConflictError(
                "GSTR-3B comparison requires a completed preparation for this "
                "GSTIN, period and source cut"
            )
        comparison = other.result["evidence"]["gstr3b"]
    return result(
        records,
        job.parameters,
        Manifest.model_validate(generation.manifest).sequence,
        sorted(unresolved),
        originals,
        comparison,
    )
