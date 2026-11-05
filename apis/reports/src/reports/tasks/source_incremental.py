"""Reuse verified history for complete new posting and invoice components.

Any previously visible update/deletion or another entity family takes the full verifier.
The optimization never infers validity from the owner's control totals alone.
"""

import itertools
import uuid
from collections import Counter
from decimal import Decimal, localcontext
from typing import Any

from billing_platform.errors import ConflictError
from reporting_contract.contract import Manifest
from reporting_contract.invoice import INVOICE_FACT_MODELS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.invoice_reconciliation import reconcile_invoices
from reports.domain.reconcile import RULE_HASH, fixed, money, validate_source_record, validated_line
from reports.models.source_versions import (
    ReportFactVersion,
    ReportGenerationRequest,
    ReportSourceCut,
)
from reports.queries.source_versions import SourceView, bounded_rows


async def verify_append(db: AsyncSession, cut: ReportSourceCut) -> dict[str, Any] | None:
    from reports.tasks.source_verification import (
        closure,
        invoice_component,
        journal_controls,
        verify_note_entitlements,
    )

    request = await db.scalar(
        select(ReportGenerationRequest).where(
            ReportGenerationRequest.company_id == cut.company_id,
            ReportGenerationRequest.generation_id == cut.generation_id,
        )
    )
    if request is None or request.strategy != "REFRESH" or request.parent_cut_id is None:
        return None
    parent = await db.scalar(
        select(ReportSourceCut).where(
            ReportSourceCut.company_id == cut.company_id,
            ReportSourceCut.id == request.parent_cut_id,
        )
    )
    if (
        parent is None
        or parent.epoch_id != cut.epoch_id
        or parent.sequence > cut.sequence
        or parent.verification is None
        or parent.verification.get("projection_version") != 1
        or parent.verification.get("rule_hash") != RULE_HASH
    ):
        return None
    prior, proof = Manifest.model_validate(parent.manifest), Manifest.model_validate(cut.manifest)
    if (
        prior.schema_hash != proof.schema_hash
        or prior.control.coverage_kind != proof.control.coverage_kind
        or prior.control.coverage_start != proof.control.coverage_start
        or proof.control.coverage_start is None
    ):
        return None
    # An interval closed at/before this cut means a previously verified identity changed.
    changed_old = await db.scalar(
        select(ReportFactVersion.id)
        .where(
            ReportFactVersion.company_id == cut.company_id,
            ReportFactVersion.epoch_id == cut.epoch_id,
            ReportFactVersion.valid_from_sequence <= parent.sequence,
            ReportFactVersion.valid_to_sequence > parent.sequence,
            ReportFactVersion.valid_to_sequence <= cut.sequence,
        )
        .limit(1)
    )
    if changed_old is not None:
        return None
    view = SourceView(cut.company_id, cut.epoch_id, cut.sequence)
    # Check final tombstones and unhandled families before choosing the fast path.
    final = select(ReportFactVersion).where(
        view.predicate(live=False),
        ReportFactVersion.valid_from_sequence > parent.sequence,
    )
    unsupported = await db.scalar(
        final.with_only_columns(ReportFactVersion.id)
        .where(
            ReportFactVersion.entity.not_in(
                {
                    "journal",
                    "journal_line",
                    "source_document",
                    "voucher_execution",
                    "voucher_money_intent",
                    "voucher_money_allocation",
                    "open_item",
                    "allocation",
                    *INVOICE_FACT_MODELS,
                }
            )
            | ReportFactVersion.data.is_(None)
        )
        .limit(1)
    )
    if unsupported is not None:
        return None
    # A large change window remains supported by the bounded full verifier.
    try:
        changed = await bounded_rows(db, final, maximum=20000)
    except ConflictError:
        return None
    counts = dict(prior.control.counts)
    for entity, amount in Counter(row.entity for row in changed).items():
        counts[entity] += amount
    if counts != proof.control.counts:
        raise ConflictError("incremental source grain counts differ")
    live = await closure(db, view, changed)

    def require(entity: str, identity: Any) -> dict[str, Any]:
        row = live.get((entity, str(identity)))
        if row is None:
            raise ConflictError("required source reference is missing")
        return row

    journals = {row.source_id for row in changed if row.entity == "journal"}
    journal_keys = {str(identity) for identity in journals}
    for row in changed:
        assert row.data is not None
        validate_source_record(row.entity, str(row.source_id), row.data, require)
        if row.entity == "journal":
            if row.source_status != "POSTED":
                return None
        if row.entity == "journal_line":
            if row.relation_id not in journals:
                return None  # A pre-existing draft posting needs its complete retained component.
            validated_line(str(row.source_id), row.data, require, proof.control.coverage_start)
        if row.entity == "open_item":
            line = require("journal_line", row.data["journal_line_id"])
            if line["journal_id"] not in journal_keys:
                return None  # A new bill on an old invoice can change its verified source grain.
    invoices: set[uuid.UUID] = set()
    for row in changed:
        if row.entity in INVOICE_FACT_MODELS:
            invoice_id = row.source_id if row.entity == "invoice_record" else row.relation_id
            if invoice_id is not None:
                invoices.add(invoice_id)
    originals: set[uuid.UUID] = set()
    for batch in itertools.batched(sorted(invoices), 10):
        headers = await view.lookup(db, "invoice_record", batch)
        if len(headers) != len(batch):
            raise ConflictError("incremental invoice source header is missing")
        reconcile_invoices(await invoice_component(db, view, list(headers.values())))
        originals.update(row.origin_id or row.source_id for row in headers.values())
    for batch in itertools.batched(sorted(originals), 200):
        # Existing sibling credit notes also consume the original supply entitlement.
        await verify_note_entitlements(db, view, list(batch))
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        new_totals: dict[str, dict[str, str]] = {}
        for row in changed:
            if row.entity != "journal":
                continue
            assert row.data is not None
            currency = row.data["base_currency"]
            values = new_totals.setdefault(currency, {"DEBIT": "0.0000", "CREDIT": "0.0000"})
            for side, field in (("DEBIT", "total_debit"), ("CREDIT", "total_credit")):
                values[side] = fixed(money(values[side]) + money(row.data[field]))
        # Native sums verify every newly appended journal against its entire current lines.
        await journal_controls(
            db,
            view,
            proof.control.model_copy(update={"base_totals": new_totals}),
            identities=journals,
        )
        totals: dict[str, dict[str, Decimal]] = {
            currency: {side: money(value) for side, value in values.items()}
            for currency, values in prior.control.base_totals.items()
        }
        for currency, values in new_totals.items():
            for side, value in values.items():
                existing = totals.setdefault(currency, {"DEBIT": Decimal(0), "CREDIT": Decimal(0)})
                existing[side] += money(value)
        actual = {
            currency: {side: fixed(value) for side, value in values.items()}
            for currency, values in totals.items()
        }
        expected = {
            currency: {side: fixed(money(value)) for side, value in values.items()}
            for currency, values in proof.control.base_totals.items()
        }
        if actual != expected:
            raise ConflictError("incremental owner control totals differ")
    return {
        "counts": counts,
        "base_totals": actual,
        "coverage_kind": proof.control.coverage_kind,
        "coverage_start": str(proof.control.coverage_start),
        "rule_hash": RULE_HASH,
        "differences": [],
        "projection_version": 1,
        "incremental_from": str(parent.id),
    }
