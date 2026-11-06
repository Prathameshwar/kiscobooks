"""Commit-bound source capture and company-fenced snapshot materialization.

All data reads use this owner's ORM. Transport publishes only committed rows.
Savepoint changes are re-read from final transaction state; rolled-back values never escape.
"""

import hashlib
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from reporting_contract.contract import FACT_MODELS, Control, Fact, Manifest, digest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, SessionTransaction

from accounting.domain.reporting_controls import Contribution, advance
from accounting.models import fiscal, ledger, masters, subledger
from accounting.models.bank_reconciliation import (
    BankAdjustmentProposal,
    BankMatchEvent,
    BankOpeningItem,
    BankReconciliationSession,
    BankStatementEntry,
    BankStatementImport,
)
from accounting.models.gst_outward import GstOutwardRecord
from accounting.models.gst_return import GstReturnRecord
from accounting.models.inventory_reporting import InventoryReportRecord
from accounting.models.invoice import INVOICE_MODELS, InvoiceSupplyFact
from accounting.models.invoice_credit import INVOICE_CREDIT_MODELS
from accounting.models.reporting import (
    ReportChange,
    ReportChangeFact,
    ReportSnapshot,
    ReportSnapshotFact,
)
from accounting.models.voucher_execution import VoucherExecution
from accounting.models.voucher_money import VOUCHER_MONEY_MODELS
from accounting.models.voucher_tax import JournalTax

SOURCES: dict[str, type[masters.Record]] = {
    model.__tablename__: model
    for model in (
        InventoryReportRecord,
        GstReturnRecord,
        GstOutwardRecord,
        JournalTax,
        *VOUCHER_MONEY_MODELS,
        BankStatementImport,
        BankStatementEntry,
        BankMatchEvent,
        BankOpeningItem,
        BankReconciliationSession,
        BankAdjustmentProposal,
        *INVOICE_MODELS,
        *INVOICE_CREDIT_MODELS,
        masters.Party,
        fiscal.FiscalTransition,
        masters.AccountHead,
        masters.AccountGroup,
        masters.Account,
        fiscal.FinancialSetup,
        fiscal.FiscalYear,
        fiscal.FiscalPeriod,
        ledger.Journal,
        ledger.JournalLine,
        subledger.OpeningBatch,
        subledger.SourceDocument,
        subledger.OpenItem,
        subledger.Allocation,
        VoucherExecution,
    )
}
SOURCE_TYPES = tuple(SOURCES.values())
KEY = "accounting_reporting_touched"
CONTROL_KEY = "accounting_reporting_before"


def contribution(entity: str, data: dict[str, Any] | None) -> Contribution:
    if data is None:
        return Contribution(False)
    if entity == "journal" and data["status"] == "POSTED":
        return Contribution(
            True, data["base_currency"], Decimal(data["total_debit"]), Decimal(data["total_credit"])
        )
    return Contribution(True)


def before(db: Session, row: masters.Record) -> Contribution:
    """Read database columns, never the already-mutated ORM identity-map instance."""
    if row in db.new:
        return Contribution(False)
    if isinstance(row, ledger.Journal):
        stored = (
            db.execute(
                select(
                    ledger.Journal.status,
                    ledger.Journal.base_currency,
                    ledger.Journal.total_debit,
                    ledger.Journal.total_credit,
                ).where(ledger.Journal.company_id == row.company_id, ledger.Journal.id == row.id)
            )
            .mappings()
            .first()
        )
        return contribution("journal", dict(stored) if stored is not None else None)
    model = SOURCES[row.__tablename__]
    query = select(model.id).where(model.company_id == row.company_id, model.id == row.id)
    if isinstance(row, VoucherExecution):
        query = query.where(VoucherExecution.result["outcome"].as_string() == "COMMITTED")
    return Contribution(db.scalar(query) is not None)


def incremental_controls(
    db: Session,
    company: uuid.UUID,
    previous: ReportChange | None,
    changes: list[tuple[str, Contribution, Contribution]],
) -> Control:
    if previous is None:
        return controls(db, company)
    prior = Control.model_validate(previous.manifest["control"])
    if set(prior.counts) != set(SOURCES):
        return controls(db, company)  # Schema expansion requires an independent recount.
    counts, totals = advance(
        prior.counts,
        {
            currency: {str(side): value for side, value in sides.items()}
            for currency, sides in prior.base_totals.items()
        },
        changes,
    )
    setup = db.scalar(
        select(fiscal.FinancialSetup).where(fiscal.FinancialSetup.company_id == company)
    )
    return Control.model_validate(
        {
            "counts": counts,
            "base_totals": totals,
            "coverage_start": setup.books_begin_date if setup else None,
            "coverage_kind": "RETAINED_LEDGER" if setup else "INCOMPLETE",
        }
    )


def fact(row: masters.Record | None, entity: str, source_id: uuid.UUID) -> Fact:
    data = None
    if row is not None:
        values = (
            {name: row.command[name] for name in ("voucher_id", "revision_id")}
            | {
                "execution_id": row.execution_id,
                "request_hash": row.request_hash,
                "result": row.result,
                "kind": row.command.get("kind"),
                "profile": row.command.get("profile"),
                "purpose": row.command.get("purpose"),
                "configuration_hash": row.command.get("configuration_hash"),
                "reversal_of_execution_id": row.command.get("reversal_of_execution_id"),
                "type_revision_id": row.command.get("source_payload", {}).get("type_revision_id"),
                "class_id": row.command.get("source_payload", {}).get("class_id"),
            }
            if isinstance(row, VoucherExecution)
            else (
                {
                    name: getattr(row, name)
                    for name in FACT_MODELS[entity].model_fields
                    if name not in {"coverage", "journal_ids"}
                }
                | {
                    "coverage": row.payload.get("coverage"),
                    "journal_ids": row.payload.get("journal_ids", []),
                }
            )
            if isinstance(row, subledger.OpeningBatch)
            else {
                name: row.source_evidence.get("item_line_key")
                if isinstance(row, InvoiceSupplyFact) and name == "item_line_key"
                else getattr(row, name)
                for name in FACT_MODELS[entity].model_fields
            }
        )
        # Native DECIMAL values are serialized explicitly; binary floats are never accepted.
        from decimal import Decimal

        values = {
            name: format(value, "f") if isinstance(value, Decimal) else value
            for name, value in values.items()
        }
        data = FACT_MODELS[entity].model_validate(values).model_dump(mode="json")
    value = {"entity": entity, "source_id": str(source_id), "data": data}
    return Fact.model_validate(value | {"content_hash": digest(value)})


def lock(db: Session, company: uuid.UUID) -> masters.AccountingSetup:
    setup = db.scalar(
        select(masters.AccountingSetup)
        .where(masters.AccountingSetup.company_id == company)
        .with_for_update()
    )
    if setup is None:
        raise ConflictError("Accounting setup is required for a report barrier")
    return setup


def head(db: Session, company: uuid.UUID) -> ReportChange | None:
    return db.scalar(
        select(ReportChange)
        .where(ReportChange.company_id == company)
        .order_by(ReportChange.sequence.desc())
        .limit(1)
    )


def controls(db: Session, company: uuid.UUID) -> Control:
    counts = {
        name: db.scalar(
            select(func.count(model.id)).where(
                model.company_id == company,
                *(
                    [VoucherExecution.result["outcome"].as_string() == "COMMITTED"]
                    if model is VoucherExecution
                    else []
                ),
            )
        )
        or 0
        for name, model in SOURCES.items()
    }
    totals: dict[str, dict[str, str]] = {}
    line, journal = ledger.JournalLine, ledger.Journal
    for currency, side, amount in db.execute(
        select(line.base_currency, line.side, func.sum(line.base_amount))
        .join(journal, (journal.id == line.journal_id) & (journal.company_id == line.company_id))
        .where(line.company_id == company, journal.status == "POSTED")
        .group_by(line.base_currency, line.side)
    ):
        totals.setdefault(currency, {"DEBIT": "0.0000", "CREDIT": "0.0000"})[side] = format(
            amount, "f"
        )
    setup = db.scalar(
        select(fiscal.FinancialSetup).where(fiscal.FinancialSetup.company_id == company)
    )
    return Control.model_validate(
        {
            "counts": counts,
            "base_totals": totals,
            "coverage_start": setup.books_begin_date if setup else None,
            "coverage_kind": "RETAINED_LEDGER" if setup else "INCOMPLETE",
        }
    )


def source_generation(previous: ReportChange | None) -> int:
    """Reporting lineage is sealed feed identity, not an administration write counter."""
    return Manifest.model_validate(previous.manifest).generation if previous else 1


def manifest(
    db: Session,
    setup: masters.AccountingSetup,
    identity: uuid.UUID,
    kind: str,
    sequence: int,
    count: int,
    checksum: str,
    control: Control | None = None,
    *,
    generation: int | None = None,
) -> Manifest:
    if generation is None:
        generation = source_generation(head(db, setup.company_id))
    scope = digest(
        {
            "owner": "accounting",
            "tenant_id": str(setup.tenant_id),
            "company_id": str(setup.company_id),
            "grains": sorted(SOURCES),
        }
    )
    return Manifest.model_validate(
        {
            "id": identity,
            "tenant_id": setup.tenant_id,
            "company_id": setup.company_id,
            "kind": kind,
            "sequence": sequence,
            "generation": generation,
            "scope_hash": scope,
            "permission_hash": scope,
            "fact_count": count,
            "facts_hash": checksum,
            "control": control if control is not None else controls(db, setup.company_id),
        }
    )


def reconcile_head(db: Session, company: uuid.UUID) -> ReportChange | None:
    """Fence and seal a new snapshot lineage if the physical source outgrew its feed.

    A missing historical change cannot be safely inserted into an already consumed
    sequence. The empty marker changes the owner generation, forcing Reports to
    create a fresh epoch from the complete source snapshot instead of applying an
    incomplete delta to an old cut.
    """
    setup = lock(db, company)
    previous = head(db, company)
    actual = controls(db, company)
    if previous is not None and Manifest.model_validate(previous.manifest).control == actual:
        return previous
    if previous is None and not any(actual.counts.values()):
        return None
    identity = uuid7()
    row = ReportChange(
        id=identity,
        tenant_id=setup.tenant_id,
        company_id=company,
        sequence=previous.sequence + 1 if previous else 1,
        manifest=manifest(
            db,
            setup,
            identity,
            "CHANGE",
            previous.sequence + 1 if previous else 1,
            0,
            hashlib.sha256(b"").hexdigest(),
            control=actual,
            generation=source_generation(previous) + 1 if previous else 1,
        ).model_dump(mode="json"),
    )
    db.add(row)
    evidence_audit(db, setup, identity, "reconciled")
    return row


def evidence_audit(
    db: Session, setup: masters.AccountingSetup, identity: uuid.UUID, action: str
) -> None:
    emit(
        db,
        aggregate_type="accounting.reporting",
        aggregate_id=identity,
        event_type="accounting.reporting." + action,
        tenant_id=setup.tenant_id,
        payload=audit_payload(
            action="accounting.reporting." + action,
            category="admin",
            entity_type="accounting.reporting",
            entity_id=identity,
            actor_user_id=setup.updated_by,
            company_id=setup.company_id,
            changes={},
        )
        | {"actor_type": "service"},
    )


@event.listens_for(Session, "before_flush")
def collect(db: Session, context: object, instances: object) -> None:
    touched = db.info.setdefault(KEY, set())
    originals = db.info.setdefault(CONTROL_KEY, {})
    for row in db.new | db.dirty | db.deleted:
        if isinstance(row, VoucherExecution) and row.result.get("outcome") != "COMMITTED":
            continue
        if isinstance(row, SOURCE_TYPES):
            if getattr(row, "id", None) is None:
                row.id = uuid7()
            key = (row.tenant_id, row.company_id, row.__tablename__, row.id)
            if key not in originals:
                originals[key] = before(db, row)
            touched.add(key)


@event.listens_for(Session, "before_commit")
def capture(db: Session) -> None:
    if db.in_nested_transaction():
        return
    db.flush()
    touched = db.info.get(KEY, set())
    if not touched:
        return
    originals = db.info[CONTROL_KEY]
    companies = sorted({key[1] for key in touched})
    for company in companies:
        setup = lock(db, company)
        previous = head(db, company)
        sequence = previous.sequence + 1 if previous else 1
        identity, checksum, count = uuid7(), hashlib.sha256(), 0
        bundle = ReportChange(
            id=identity,
            tenant_id=setup.tenant_id,
            company_id=company,
            sequence=sequence,
            manifest={},
        )
        db.add(bundle)
        # Parent must exist before children; populate final manifest before the next flush.
        selected = []
        changes = []
        for _tenant, source_company, entity, source_id in sorted(
            touched, key=lambda key: (key[1], key[2], key[3])
        ):
            if source_company != company:
                continue
            model = SOURCES[entity]
            row = db.scalar(
                select(model)
                .where(model.company_id == company, model.id == source_id)
                .execution_options(populate_existing=True)
            )
            if isinstance(row, VoucherExecution) and row.result.get("outcome") != "COMMITTED":
                row = None
            wire = fact(row, entity, source_id).model_dump(mode="json")
            changes.append(
                (
                    entity,
                    originals[(_tenant, source_company, entity, source_id)],
                    contribution(entity, wire["data"]),
                )
            )
            selected.append(wire)
            checksum.update(canonical_json(wire) + b"\n")
        count = len(selected)
        bundle.manifest = manifest(
            db,
            setup,
            identity,
            "CHANGE",
            sequence,
            count,
            checksum.hexdigest(),
            control=incremental_controls(db, company, previous, changes),
            generation=source_generation(previous),
        ).model_dump(mode="json")
        db.flush()
        for ordinal, wire in enumerate(selected, 1):
            db.add(
                ReportChangeFact(
                    tenant_id=setup.tenant_id,
                    company_id=company,
                    change_id=identity,
                    ordinal=ordinal,
                    fact=wire,
                )
            )
        evidence_audit(db, setup, identity, "captured")
    db.info.pop(KEY, None)
    db.info.pop(CONTROL_KEY, None)


@event.listens_for(Session, "after_transaction_end")
def reset(db: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        db.info.pop(KEY, None)
        db.info.pop(CONTROL_KEY, None)


def source_rows(db: Session, company: uuid.UUID) -> Iterator[Fact]:
    for name, model in sorted(SOURCES.items()):
        after = None
        while True:
            query = select(model).where(model.company_id == company)
            if model is VoucherExecution:
                query = query.where(VoucherExecution.result["outcome"].as_string() == "COMMITTED")
            if after:
                query = query.where(model.id > after)
            rows = list(db.scalars(query.order_by(model.id).limit(200)))
            for row in rows:
                yield fact(row, name, row.id)
            if len(rows) < 200:
                break
            after = rows[-1].id


def snapshot(db: Session, company: uuid.UUID, identity: uuid.UUID) -> Manifest:
    setup = lock(db, company)
    prior = db.scalar(
        select(ReportSnapshot).where(
            ReportSnapshot.company_id == company, ReportSnapshot.id == identity
        )
    )
    if prior:
        return Manifest.model_validate(prior.manifest)
    reconcile_head(db, company)
    latest = head(db, company)
    # Defer parent insert until its immutable manifest has been calculated.
    checksum, count, pages = hashlib.sha256(), 0, []
    for item in source_rows(db, company):
        wire = item.model_dump(mode="json")
        count += 1
        checksum.update(canonical_json(wire) + b"\n")
        pages.append(wire)
        if count > 100000:
            raise ConflictError("snapshot exceeds the initial 100000-fact bound")
    result = manifest(
        db,
        setup,
        identity,
        "SNAPSHOT",
        latest.sequence if latest else 0,
        count,
        checksum.hexdigest(),
    )
    db.add(
        ReportSnapshot(
            id=identity,
            tenant_id=setup.tenant_id,
            company_id=company,
            manifest=result.model_dump(mode="json"),
        )
    )
    db.flush()
    for ordinal, wire in enumerate(pages, 1):
        db.add(
            ReportSnapshotFact(
                tenant_id=setup.tenant_id,
                company_id=company,
                snapshot_id=identity,
                ordinal=ordinal,
                fact=wire,
            )
        )
        if ordinal % 200 == 0:
            db.flush()
    evidence_audit(db, setup, identity, "snapshotted")
    return result
