"""Atomic shared aggregates, immutable revisions and revision-bound workflow."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.domain.configuration import digest
from vouchers.domain.documents import fiscal_start, transition, validate_content
from vouchers.domain.duplicate_bill import (
    ACKNOWLEDGED_NOTE,
    AUTOMATIC_APPROVAL_NOTE,
    INCOMPLETE_NOTE,
    annotate,
)
from vouchers.domain.item_eligibility import assert_item_use
from vouchers.models import core as m
from vouchers.models.commercial import VoucherAssignment
from vouchers.models.counter import (
    CheckoutCounter,
    CounterOutlet,
    CounterSession,
    VoucherCounterContext,
)
from vouchers.schemas.documents import AssignmentInput, IssueRequest, VoucherInput
from vouchers.schemas.sources import ItemTransactionFacts
from vouchers.tasks import custom_fields, financial_details, invoice_details, stock_details
from vouchers.tasks.access import authorize, mask, writable
from vouchers.tasks.common import audit, expected, get, values
from vouchers.tasks.configuration import effective
from vouchers.tasks.duplicate_bills import DuplicateScan, refusal
from vouchers.tasks.duplicate_bills import find as find_duplicate_bills
from vouchers.tasks.unit_admission import validate_units

#: History reason when an edit returns a submitted, approved or rejected voucher to draft.
REOPEN_REASON = "edited after submission; earlier submission or approval withdrawn"
CHILDREN = (
    (m.VoucherParty, "parties"),
    (m.VoucherReference, "references"),
    (m.VoucherAttachment, "attachments"),
    (m.VoucherLink, "links"),
    (VoucherAssignment, "assignments"),
)


async def content(db: AsyncSession, current: Access, revision: m.VoucherRevision) -> dict[str, Any]:
    fields = set(VoucherInput.model_fields) - {
        "stock",
        "financial",
        "invoice",
        "fulfillment_terms",
        "lines",
        "parties",
        "references",
        "attachments",
        "links",
        "assignments",
        "counter",
    }
    data = {key: getattr(revision, key) for key in fields}
    financial = await financial_details.load(db, current, revision)
    stock = await stock_details.load(db, current, revision)
    if stock is not None:
        data["stock"] = stock
    if financial is not None:
        data["financial"] = financial
    invoice = await invoice_details.load(db, current, revision)
    if invoice is not None:
        data["invoice"] = invoice
    terms = await db.scalar(
        select(m.VoucherFulfillmentTerms).where(
            m.VoucherFulfillmentTerms.company_id == current.context.company_id,
            m.VoucherFulfillmentTerms.revision_id == revision.id,
        )
    )
    if terms is not None:
        data["fulfillment_terms"] = {
            key: getattr(terms, key)
            for key in (
                "purpose",
                "valid_until",
                "required_by",
                "destination_reference",
                "delivery_terms",
                "payment_terms",
            )
        }
    lines = list(
        await db.scalars(
            select(m.VoucherLine)
            .where(
                m.VoucherLine.company_id == current.context.company_id,
                m.VoucherLine.revision_id == revision.id,
                m.VoucherLine.line_kind == "ITEM",
            )
            .order_by(m.VoucherLine.sequence)
        )
    )
    item_rows = {
        row.line_id: row
        for row in await db.scalars(
            select(m.VoucherItemDetail).where(
                m.VoucherItemDetail.company_id == current.context.company_id,
                m.VoucherItemDetail.revision_id == revision.id,
            )
        )
    }
    data["lines"] = [
        {
            "line_key": line.line_key,
            "line_kind": line.line_kind,
            "description": line.description,
            "item": {
                key: getattr(item_rows[line.id], key)
                for key in (
                    "item_id",
                    "item_version",
                    "unit_id",
                    "actual_quantity",
                    "billed_quantity",
                    "planned_quantity",
                    "custom_fields",
                )
            },
        }
        for line in lines
    ]
    for model, key in CHILDREN:
        rows = list(
            await db.scalars(
                select(model)
                .where(
                    model.company_id == current.context.company_id, model.revision_id == revision.id
                )
                .order_by(model.id)
            )
        )
        data[key] = [
            {
                c.name: getattr(row, c.name)
                for c in model.__table__.columns
                if c.name
                not in {
                    "id",
                    "tenant_id",
                    "company_id",
                    "revision_id",
                    "row_version",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "updated_by",
                }
                and (model is not VoucherAssignment or c.name in AssignmentInput.model_fields)
            }
            for row in rows
        ]
    counter_context = await db.scalar(
        select(VoucherCounterContext).where(
            VoucherCounterContext.company_id == current.context.company_id,
            VoucherCounterContext.revision_id == revision.id,
        )
    )
    data["counter"] = (
        {"counter_id": counter_context.counter_id, "session_id": counter_context.session_id}
        if counter_context is not None
        else None
    )
    return VoucherInput.model_validate(data).model_dump(mode="json")


async def revision_for(db: AsyncSession, current: Access, voucher: m.Voucher) -> m.VoucherRevision:
    result = await db.scalar(
        select(m.VoucherRevision).where(
            m.VoucherRevision.company_id == current.context.company_id,
            m.VoucherRevision.voucher_id == voucher.id,
            m.VoucherRevision.revision_number == voucher.current_revision,
        )
    )
    if result is None:
        raise ConflictError("voucher revision is unavailable")
    return result


async def detail(
    db: AsyncSession, current: Access, voucher_id: uuid.UUID, revision_id: uuid.UUID | None = None
) -> dict[str, Any]:
    authorize(current, "read")
    voucher = await get(db, current, m.Voucher, voucher_id)
    revision = (
        await get(db, current, m.VoucherRevision, revision_id)
        if revision_id
        else await revision_for(db, current, voucher)
    )
    if revision.voucher_id != voucher.id:
        raise ValidationFailedError("revision belongs to another voucher")
    data = await content(db, current, revision)
    assignment_rows = list(
        await db.scalars(
            select(VoucherAssignment)
            .where(
                VoucherAssignment.company_id == current.context.company_id,
                VoucherAssignment.revision_id == revision.id,
            )
            .order_by(VoucherAssignment.id)
        )
    )
    for accepted, stored in zip(data["assignments"], assignment_rows, strict=True):
        accepted["source_code"] = stored.source_code
        accepted["source_name"] = stored.source_name
    assignment = await db.scalar(
        select(m.VoucherNumberAssignment).where(
            m.VoucherNumberAssignment.company_id == current.context.company_id,
            m.VoucherNumberAssignment.revision_id == revision.id,
        )
    )
    data["issue_number"] = assignment.display_number if assignment else None
    counter_context = await db.scalar(
        select(VoucherCounterContext).where(
            VoucherCounterContext.company_id == current.context.company_id,
            VoucherCounterContext.revision_id == revision.id,
        )
    )
    data["cashier_id"] = counter_context.cashier_id if counter_context else None
    stock_restricted = stock_details.restricted(current, data)
    if stock_restricted:
        data.pop("stock", None)
    data["lines"] = [
        line | {"item": mask(current, "vouchers.voucher_item", line["item"])}
        for line in data["lines"]
    ]
    result = mask(
        current,
        "vouchers.voucher",
        data
        | {
            "id": str(voucher.id),
            "company_id": str(voucher.company_id),
            "row_version": voucher.row_version,
            "status": voucher.status,
            "kind": revision.configuration_evidence["kind"],
            "profile": revision.configuration_evidence["profile"],
            "revision_id": str(revision.id),
            "revision_number": revision.revision_number,
            "content_hash": revision.content_hash,
            "configuration_hash": revision.configuration_hash,
            "fiscal_start_date": revision.fiscal_start_date.isoformat(),
        },
    )
    if stock_restricted:
        result.pop("content_hash", None)
    return result


async def validate_masters(
    db: AsyncSession,
    current: Access,
    body: VoucherInput,
    *,
    capture: bool = True,
    kind: str | None = None,
    profile: str = "STANDARD",
) -> None:
    if body.stock is not None and "inventory" not in current.context.features:
        raise ConflictError("enable company inventory before capturing physical stock")
    if body.currency != current.context.base_currency and (
        "multi_currency" not in current.context.features
    ):
        raise ConflictError("foreign voucher currency requires multi_currency")
    if (
        capture
        and body.currency != current.context.base_currency
        and body.currency not in current.context.allowed_currencies
    ):
        raise ConflictError("voucher currency is not enabled for new documents")
    for assignment in body.assignments:
        if assignment.role in {"RETURN_HANDLER", "PAYMENT_HANDLER"}:
            if assignment.source_version != 1:
                raise ValidationFailedError("handler source version is invalid")
            if capture and assignment.principal_id != current.actor.user_id:
                raise PermissionDeniedError("handler must be the authenticated operator")
        if assignment.source_revision_id is not None and assignment.source_revision_id not in {
            link.source_revision_id for link in body.links
        }:
            raise ValidationFailedError("assignment source revision requires a voucher link")
    invoice_masters: list[tuple[str, str, uuid.UUID, int | None]] = []
    if body.invoice:
        invoice = body.invoice
        invoice_masters.append(
            ("accounting", "account", invoice.party_account_id, invoice.party_account_version)
        )
        invoice_masters.extend(
            ("accounting", "account", row.account_id, row.account_version)
            for row in invoice.supplies
        )
        invoice_masters.extend(
            ("accounting", "account", row.account_id, row.account_version)
            for row in invoice.components
            if row.account_id is not None
        )
        invoice_masters.extend(
            ("accounting", "account", row.account_id, row.account_version)
            for row in invoice.tenders
        )
        invoice_masters.extend(
            ("catalog", "unit", q.unit_id, None) for row in invoice.supplies for q in row.quantities
        )
        if invoice.rounding_account_id:
            invoice_masters.append(
                (
                    "accounting",
                    "account",
                    invoice.rounding_account_id,
                    invoice.rounding_account_version,
                )
            )
    ledger_key = ("accounting", "account", body.invoice.party_account_id) if body.invoice else None
    party_ledger: m.VoucherMasterEvidence | None = None
    for owner, entity, source, version in [
        *invoice_masters,
        *(("catalog", "item", line.item.item_id, line.item.item_version) for line in body.lines),
        *(("catalog", "unit", line.item.unit_id, None) for line in body.lines),
        *(("accounting", "party", party.party_id, party.source_version) for party in body.parties),
        *(
            ("identity", "salesperson", a.principal_id, a.source_version)
            for a in body.assignments
            if a.role in {"SELLER", "COLLECTOR"}
        ),
        *(
            ("accounting", "broker_party", a.principal_id, a.source_version)
            for a in body.assignments
            if a.role == "BROKER"
        ),
        *(
            ("accounting", "account", entry.account_id, entry.source_version)
            for entry in (body.financial.accounts if body.financial else ())
        ),
    ]:
        row = await db.scalar(
            select(m.VoucherMasterEvidence).where(
                m.VoucherMasterEvidence.company_id == current.context.company_id,
                m.VoucherMasterEvidence.owner == owner,
                m.VoucherMasterEvidence.entity_type == entity,
                m.VoucherMasterEvidence.source_id == source,
            )
        )
        if (
            row is None
            or row.status != "ACTIVE"
            or (version is not None and row.source_version != version)
        ):
            raise ConflictError("voucher master evidence is unavailable or stale")
        if (owner, entity, source) == ledger_key:
            party_ledger = row
    if party_ledger is not None:
        # The payable posts to the party ledger while the header and print show the party, so
        # the replicated ledger must belong to exactly the customer/supplier the header names.
        linked = party_ledger.facts.get("party_id")
        for party in body.parties:
            if party.role not in {"CUSTOMER", "SUPPLIER"}:
                continue
            if "party_id" not in party_ledger.facts:
                # Replicated before Accounting published party links: stale, not a mismatch.
                raise ValidationFailedError(
                    "invoice.party_account_id: the replicated account master carries no party "
                    "link; the account master must be re-synchronised from Accounting"
                )
            if linked != str(party.party_id):
                raise ValidationFailedError(
                    f"invoice.party_account_id is not the ledger of the {party.role} in parties[]: "
                    "the account belongs to another party or to none"
                )
    await validate_units(db, current, body, kind)
    if not capture and body.lines:
        if kind is None:
            raise ConflictError("voucher kind is required for item eligibility")
        ids = {line.item.item_id for line in body.lines}
        policies = {
            row.source_id: row
            for row in await db.scalars(
                select(m.VoucherMasterEvidence)
                .where(
                    m.VoucherMasterEvidence.company_id == current.context.company_id,
                    m.VoucherMasterEvidence.owner == "catalog",
                    m.VoucherMasterEvidence.entity_type == "item_transaction_policy",
                    m.VoucherMasterEvidence.source_id.in_(ids),
                )
                .with_for_update()
            )
        }
        if len(policies) != len(ids):
            raise ConflictError("item transaction policy evidence is unavailable")
        supplies = (
            {
                row.item_line_key: row
                for row in body.invoice.supplies
                if row.item_line_key is not None
            }
            if body.invoice is not None
            else {}
        )
        for line in body.lines:
            policy = policies[line.item.item_id]
            if policy.status != "ACTIVE":
                raise ConflictError("item is not active for this transaction")
            facts = ItemTransactionFacts.model_validate(policy.facts)
            if facts.item_version != line.item.item_version:
                raise ConflictError("item transaction policy is stale")
            supply = supplies.get(line.line_key)
            assert_item_use(
                facts,
                kind=kind,
                profile=profile,
                supply_kind=supply.supply_kind if supply is not None else None,
            )
    for link in body.links:
        source_voucher = await get(db, current, m.Voucher, link.source_voucher_id)
        source_revision = await get(db, current, m.VoucherRevision, link.source_revision_id)
        if source_revision.voucher_id != source_voucher.id:
            raise ValidationFailedError("source link revision belongs to another voucher")
    # Foundation attachment references are scoped metadata. Object existence/download
    # authority requires the future storage adapter; a key is never download authority.
    for attachment in body.attachments:
        if not attachment.object_key.startswith(
            str(current.actor.tenant_id) + "/" + str(current.context.company_id) + "/"
        ):
            raise PermissionDeniedError("attachment is outside the selected company")


async def validate_counter(
    db: AsyncSession, current: Access, body: VoucherInput, *, capture: bool = True
) -> None:
    if body.counter is None:
        return
    row = await get(db, current, CheckoutCounter, body.counter.counter_id)
    outlet = await get(db, current, CounterOutlet, row.outlet_id)
    if row.status != "ACTIVE" or outlet.status != "ACTIVE":
        raise ConflictError("counter or outlet is inactive")
    if body.counter.session_id is not None:
        shift = await get(db, current, CounterSession, body.counter.session_id, lock=True)
        if shift.counter_id != row.id or shift.status != "OPEN":
            raise ConflictError("counter session is unavailable")
        if capture and shift.opened_by != current.actor.user_id:
            raise PermissionDeniedError("counter session belongs to another cashier")
        if shift.currency != body.currency:
            raise ValidationFailedError("counter session currency differs from voucher")


async def inherited_assignments(
    db: AsyncSession, current: Access, body: VoucherInput, kind: str, policy: Any
) -> list[dict[str, Any]]:
    """Copy accepted header attribution from one party-matched source document."""
    controls = policy.commercial_attribution
    if controls is None or not body.links or body.assignments:
        return []
    compatible = {
        "SALES_ORDER": {"SALES_ORDER"},
        "DELIVERY_NOTE": {"SALES_ORDER"},
        "SALES": {"SALES_ORDER", "DELIVERY_NOTE"},
        "CREDIT_NOTE": {"SALES"},
        "PURCHASE_ORDER": {"PURCHASE_ORDER"},
        "PURCHASE": {"PURCHASE_ORDER"},
        "DEBIT_NOTE": {"PURCHASE"},
    }.get(kind, set())
    candidates: list[tuple[m.VoucherRevision, dict[str, Any]]] = []
    for link in body.links:
        source_revision = await get(db, current, m.VoucherRevision, link.source_revision_id)
        source_voucher = await get(db, current, m.Voucher, link.source_voucher_id)
        if source_revision.voucher_id != source_voucher.id:
            raise ValidationFailedError("assignment source link is inconsistent")
        if source_revision.configuration_evidence["kind"] not in compatible:
            continue
        if source_voucher.status not in {"ISSUED", "ACCEPTED", "POSTED"}:
            continue
        source = await content(db, current, source_revision)
        source_parties = {
            (row["role"], row["party_id"])
            for row in source["parties"]
            if row["role"] in {"CUSTOMER", "SUPPLIER"}
        }
        target_parties = {
            (row.role, str(row.party_id))
            for row in body.parties
            if row.role in {"CUSTOMER", "SUPPLIER"}
        }
        if not source_parties & target_parties:
            continue
        if source["assignments"]:
            candidates.append((source_revision, source))
    if len(candidates) > 1:
        raise ValidationFailedError("multiple attribution sources require explicit assignments")
    if not candidates:
        return []
    source_revision, source = candidates[0]
    copied = []
    for assignment in source["assignments"]:
        role = assignment["role"]
        setting = {"SELLER": "seller", "BROKER": "broker"}.get(role)
        if setting is None or getattr(controls, setting) == "OFF":
            continue
        if assignment["line_key"] is not None:
            raise ValidationFailedError("line attribution conversion requires explicit mapping")
        copied.append(assignment | {"source_revision_id": str(source_revision.id)})
    return copied


async def write(
    db: AsyncSession,
    current: Access,
    body: VoucherInput,
    *,
    voucher_id: uuid.UUID | None = None,
    version: int | None = None,
    assignment_override_reason: str = "",
    accepted_calculation_hash: str | None = None,
    payable_total: Decimal | None = None,
) -> m.Voucher:
    """Write one new immutable revision.

    ``accepted_calculation_hash`` is the only way an invoice revision carries an acceptance. It is
    supplied by the acceptance route after it has verified the hash against the owner's preview of
    this exact revision. Whatever the request body says is ignored: an acceptance is evidence about
    one revision's content, so every ordinary create or edit starts a fresh, unaccepted revision.
    """
    finance = current.context.finance
    if finance is None or not finance.company_active:
        raise ConflictError("active company calendar context is required")
    if (
        body.stock
        and body.stock.action == "OPENING"
        and (
            body.stock.stock_date != finance.books_begin_date
            or body.posting_date != finance.books_begin_date
        )
    ):
        raise ValidationFailedError("opening stock must use the company's books begin date")
    policy, evidence = await effective(
        db,
        current,
        body.type_revision_id,
        date=body.document_date,
        posting_date=body.posting_date,
        class_id=body.class_id,
    )
    defaults = {
        key: getattr(policy, "default_" + key)
        for key in ("mode", "narration")
        if key not in body.model_fields_set
    }
    body = body.model_copy(update=defaults)
    type_revision = await get(db, current, m.VoucherTypeRevision, body.type_revision_id)
    voucher = (
        await get(db, current, m.Voucher, voucher_id, lock=True)
        if voucher_id
        else m.Voucher(
            **values(current),
            type_id=type_revision.type_id,
            status="DRAFT",
            current_revision=1,
            row_version=1,
        )
    )
    previous = {}
    reopened_from = None
    if voucher_id:
        await guard_execution(db, current, voucher.id)
        expected(voucher, version or 0)
        if voucher.status not in {"DRAFT", "REJECTED", "APPROVED", "SUBMITTED"}:
            raise ConflictError("issued or cancelled voucher content cannot change")
        if voucher.type_id != type_revision.type_id:
            raise ValidationFailedError("voucher kind/type identity cannot change")
        previous = await content(db, current, await revision_for(db, current, voucher))
        voucher.current_revision += 1
        voucher.row_version += 1
        if voucher.status != "DRAFT":
            reopened_from = voucher.status
        voucher.status = "DRAFT"
        voucher.updated_by = current.actor.user_id
    else:
        db.add(voucher)
        await db.flush()
    raw = body.model_dump(mode="json")
    if not voucher_id and body.assignments and body.links:
        baseline = await inherited_assignments(
            db, current, body.model_copy(update={"assignments": ()}), evidence["kind"], policy
        )

        def identity(rows: list[dict[str, Any]]) -> set[tuple[str, str, str, Decimal, str]]:
            return {
                (
                    row["role"],
                    str(row["principal_id"]),
                    str(row["line_key"]),
                    Decimal(str(row["share"])),
                    str(row.get("source_revision_id")),
                )
                for row in rows
            }

        if baseline and identity(baseline) != identity(raw["assignments"]):
            authorize(current, "approve")
            if any(not row["override_reason"] for row in raw["assignments"]):
                raise ValidationFailedError("assignment override requires a reason")
    if voucher_id and "assignments" not in body.model_fields_set:
        raw["assignments"] = previous.get("assignments", [])
    attribution_changed = False
    if voucher_id and "assignments" in body.model_fields_set:

        def assignment_identity(
            rows: list[dict[str, Any]],
        ) -> set[tuple[str, str, str, Decimal, str]]:
            return {
                (
                    row["role"],
                    str(row["principal_id"]),
                    str(row["line_key"]),
                    Decimal(str(row["share"])),
                    str(row.get("source_revision_id")),
                )
                for row in rows
            }

        if assignment_identity(previous.get("assignments", [])) != assignment_identity(
            raw["assignments"]
        ):
            attribution_changed = True
            authorize(current, "approve")
            if not assignment_override_reason.strip():
                raise ValidationFailedError("assignment change requires an approval reason")
            raw["assignments"] = [
                row | {"override_reason": assignment_override_reason.strip()}
                for row in raw["assignments"]
            ]
    if not voucher_id and not raw["assignments"]:
        raw["assignments"] = await inherited_assignments(
            db, current, body, evidence["kind"], policy
        )
    writable(
        current,
        "vouchers.voucher",
        {k: v for k, v in previous.items() if k != "custom_fields"},
        {k: v for k, v in raw.items() if k != "custom_fields"},
    )
    if raw.get("invoice") is not None:
        raw["invoice"]["accepted_calculation_hash"] = accepted_calculation_hash
        raw["invoice"]["payable_total"] = str(payable_total) if payable_total is not None else None
    header, defs = await custom_fields.normalize(
        db,
        current,
        "vouchers.voucher",
        voucher.id,
        body.custom_fields,
        previous.get("custom_fields", {}),
        raw,
        allowed=policy.header_field_keys,
        day=body.document_date,
        creating=not bool(voucher_id),
    )
    raw["custom_fields"] = header
    line_defs = {}
    previous_lines = {line["line_key"]: line for line in previous.get("lines", [])}
    for line in raw["lines"]:
        old = previous_lines.get(line["line_key"], {}).get("item", {})
        writable(
            current,
            "vouchers.voucher_item",
            {k: v for k, v in old.items() if k != "custom_fields"},
            {k: v for k, v in line["item"].items() if k != "custom_fields"},
        )
        entity_id = uuid.uuid5(voucher.id, line["line_key"])
        custom, definitions = await custom_fields.normalize(
            db,
            current,
            "vouchers.voucher_item",
            entity_id,
            line["item"]["custom_fields"],
            old.get("custom_fields", {}),
            line["item"],
            allowed=policy.item_field_keys,
            day=body.document_date,
            creating=not bool(old),
        )
        line["item"]["custom_fields"] = custom
        line_defs[line["line_key"]] = definitions
    normalized = VoucherInput.model_validate(raw)
    today = utcnow().astimezone(ZoneInfo(finance.timezone)).date()
    validate_content(
        normalized,
        policy,
        kind=evidence["kind"],
        profile=evidence["profile"],
        stage="DRAFT",
        today=today,
    )
    await validate_masters(
        db, current, normalized, kind=evidence["kind"], profile=evidence["profile"]
    )
    if evidence["kind"] == "PURCHASE":
        from vouchers.tasks.supporting_files import validate_references

        await validate_references(
            db, current, voucher.id, normalized.attachments, previous.get("attachments", [])
        )
    await validate_counter(db, current, normalized)
    start = fiscal_start(
        body.document_date, finance.fiscal_year_start_month, finance.fiscal_year_start_day
    )
    presentations = {
        row.entity_type + ":" + row.field_key: row.presentation
        for row in await db.scalars(
            select(m.VoucherDefinitionProjection)
            .where(m.VoucherDefinitionProjection.company_id == current.context.company_id)
            .limit(257)
        )
    }
    revision = m.VoucherRevision(
        **values(current),
        voucher_id=voucher.id,
        revision_number=voucher.current_revision,
        **{
            key: getattr(normalized, key)
            for key in VoucherInput.model_fields
            if key
            not in {
                "stock",
                "financial",
                "invoice",
                "fulfillment_terms",
                "lines",
                "parties",
                "references",
                "attachments",
                "links",
                "assignments",
                "counter",
            }
        },
        fiscal_start_date=start,
        definition_snapshot={"header": defs, "items": line_defs, "presentation": presentations},
        configuration_evidence=evidence,
        configuration_hash=evidence["digest"],
        content_hash=digest(raw),
        assignment_override_reason=(
            assignment_override_reason.strip() if attribution_changed else None
        ),
    )
    db.add(revision)
    await db.flush()
    if reopened_from is not None:
        # Editing a submitted, approved or rejected bill withdraws that step; history says so.
        db.add(
            m.VoucherTransition(
                **values(current),
                voucher_id=voucher.id,
                revision_id=revision.id,
                action="reopen",
                from_status=reopened_from,
                to_status="DRAFT",
                reason=REOPEN_REASON,
                voucher_version=voucher.row_version,
            )
        )
    if normalized.financial is not None:
        await financial_details.store(db, current, revision, normalized.financial)
    for number, line in enumerate(normalized.lines, 1):
        row = m.VoucherLine(
            **values(current),
            revision_id=revision.id,
            line_key=line.line_key,
            sequence=number,
            line_kind=line.line_kind,
            description=line.description,
        )
        db.add(row)
        await db.flush()
        db.add(
            m.VoucherItemDetail(
                **values(current), revision_id=revision.id, line_id=row.id, **line.item.model_dump()
            )
        )
    if normalized.invoice is not None:
        await invoice_details.store(
            db, current, revision, normalized.invoice, kind=evidence["kind"]
        )
    if normalized.stock is not None:
        await stock_details.store(db, current, revision, normalized.stock, previous=previous)
    if normalized.fulfillment_terms is not None:
        db.add(
            m.VoucherFulfillmentTerms(
                **values(current),
                revision_id=revision.id,
                **normalized.fulfillment_terms.model_dump(),
            )
        )
    if normalized.counter is not None:
        db.add(
            VoucherCounterContext(
                **values(current),
                revision_id=revision.id,
                counter_id=normalized.counter.counter_id,
                session_id=normalized.counter.session_id,
                cashier_id=current.actor.user_id,
            )
        )
    for model, key in CHILDREN:
        for child in getattr(normalized, key):
            payload = child.model_dump()
            if model is VoucherAssignment and child.role in {"SELLER", "COLLECTOR", "BROKER"}:
                source_owner = "accounting" if child.role == "BROKER" else "identity"
                entity = "broker_party" if child.role == "BROKER" else "salesperson"
                source = await db.scalar(
                    select(m.VoucherMasterEvidence).where(
                        m.VoucherMasterEvidence.company_id == current.context.company_id,
                        m.VoucherMasterEvidence.owner == source_owner,
                        m.VoucherMasterEvidence.entity_type == entity,
                        m.VoucherMasterEvidence.source_id == child.principal_id,
                    )
                )
                if source is None or source.source_version != child.source_version:
                    raise ConflictError("assignment source changed during capture")
                source_code, source_name = source.facts.get("code"), source.facts.get("name")
                if (
                    source_code is not None
                    and (not isinstance(source_code, str) or len(source_code) > 40)
                ) or (
                    source_name is not None
                    and (not isinstance(source_name, str) or len(source_name) > 160)
                ):
                    raise ConflictError("assignment source label is invalid")
                payload["source_code"] = source_code
                payload["source_name"] = source_name
            db.add(model(**values(current), revision_id=revision.id, **payload))
    await custom_fields.indexes(
        db, current, "vouchers.voucher", voucher.id, voucher.id, revision.id, defs, header
    )
    for line in normalized.lines:
        await custom_fields.indexes(
            db,
            current,
            "vouchers.voucher_item",
            uuid.uuid5(voucher.id, str(line.line_key)),
            voucher.id,
            revision.id,
            line_defs[str(line.line_key)],
            line.item.custom_fields,
        )
    removed = set(previous_lines) - {str(line.line_key) for line in normalized.lines}
    for key in removed:
        old_item = previous_lines[key]["item"]
        writable(current, "vouchers.voucher_item", old_item, {})
        writable(current, "vouchers.voucher_item", old_item.get("custom_fields", {}), {})
        owner = uuid.uuid5(voucher.id, key)
        for custom_model in (m.VoucherCustomIndex, m.VoucherCustomClaim):
            for custom_row in await db.scalars(
                select(custom_model).where(
                    custom_model.company_id == current.context.company_id,
                    custom_model.entity_id == owner,
                )
            ):
                await db.delete(custom_row)
    audit(
        db,
        current,
        "voucher",
        voucher.id,
        "update" if voucher_id else "create",
        reason=REOPEN_REASON if reopened_from is not None else None,
    )
    return voucher


def default_series_code(type_code: str) -> str:
    """`D-` and the type code, within the 20-character series code; long codes keep a digest."""
    code = "D-" + type_code
    if len(code) <= 20:
        return code
    import hashlib

    return code[:14] + "-" + hashlib.sha256(type_code.encode()).hexdigest()[:5].upper()


async def type_default_series(
    db: AsyncSession, current: Access, type_revision_id: uuid.UUID
) -> uuid.UUID:
    """The automatic, year-reset series a type numbers from when its policy names none.

    Numbering is configuration a company may refine (its own series, a default, an allowed
    list), never a step that must happen before the first document can be issued. Created on
    first use, once per company and type: concurrent first issues meet on the unique code.
    """
    from billing_platform.db.claims import insert_candidate

    revision = await get(db, current, m.VoucherTypeRevision, type_revision_id)
    kind = await get(db, current, m.VoucherType, revision.type_id)
    code = default_series_code(kind.code)
    candidate = values(current) | {
        "code": code,
        "prefix": code[2:][:19] + "/",
        "suffix": "",
        "padding": 6,
        "start_value": 1,
        "numbering_mode": "AUTOMATIC",
        "reset_policy": "FINANCIAL_YEAR",
        "include_year": True,
        "status": "ACTIVE",
        "row_version": 1,
    }
    await insert_candidate(db, m.VoucherNumberSeries, candidate)
    series = await db.scalar(
        select(m.VoucherNumberSeries).where(
            m.VoucherNumberSeries.company_id == current.context.company_id,
            m.VoucherNumberSeries.code == code,
        )
    )
    if series is None:
        raise ConflictError("default issue series is unavailable")
    if series.status != "ACTIVE":
        raise ConflictError(
            f"the automatic series {code} is retired; choose a series for this type"
        )
    if series.id == candidate["id"]:
        audit(db, current, "series", series.id, "create", reason="default series for " + kind.code)
    return series.id


async def action(
    db: AsyncSession,
    current: Access,
    voucher_id: uuid.UUID,
    action_name: str,
    version: int,
    reason: str,
    issue: IssueRequest | None = None,
    *,
    acknowledge_duplicate_bill: bool = False,
) -> m.Voucher:
    finance = current.context.finance
    if finance is None or not finance.company_active:
        raise ConflictError("active company calendar context is required")
    if acknowledge_duplicate_bill and action_name != "submit":
        raise ValidationFailedError("acknowledge_duplicate_bill applies only to submit")
    voucher = await get(db, current, m.Voucher, voucher_id, lock=True)
    expected(voucher, version)
    await guard_execution(db, current, voucher.id)
    revision = await revision_for(db, current, voucher)
    nonposting_order = revision.configuration_evidence["kind"] in {
        "SALES_ORDER",
        "PURCHASE_ORDER",
    } or (
        revision.configuration_evidence["kind"] == "STOCK_JOURNAL"
        and revision.configuration_evidence["profile"] == "REQUISITION"
    )
    if action_name in {"reject", "cancel", "decline", "expire"}:
        from vouchers.schemas.configuration import Policy

        evidence = revision.configuration_evidence
        policy = Policy.model_validate(evidence["policy"])
    else:
        policy, evidence = await effective(
            db,
            current,
            revision.type_revision_id,
            date=revision.document_date,
            posting_date=revision.posting_date,
            class_id=revision.class_id,
        )
    if (
        action_name not in {"reject", "cancel", "decline", "expire"}
        and evidence["digest"] != revision.configuration_hash
    ):
        raise ConflictError("configuration changed; revise and reapprove this voucher")
    if (
        action_name == "approve"
        and policy.approval_required
        and not policy.self_approval_allowed
        and current.actor.user_id in await authors(db, current, voucher)
    ):
        raise PermissionDeniedError(
            "another authorized actor must approve this voucher: it cannot be approved by "
            "anyone who created it or any of its revisions"
        )
    if action_name in {"reject", "cancel", "decline"} and not reason.strip():
        raise ValidationFailedError("a reason is required")
    target = transition(
        voucher.status,
        action_name,
        approval_required=policy.approval_required,
        nonposting_order=nonposting_order,
    )
    # Where approval is not required, submit is the whole approval step. It is recorded as such,
    # in the transition history and the audit event, because no approval row exists to show it.
    auto_approved = action_name == "submit" and target == "APPROVED"
    notes: list[str] = [AUTOMATIC_APPROVAL_NOTE] if auto_approved else []
    changes: dict[str, Any] = (
        {"from_status": voucher.status, "to_status": target, "approval": "not_required"}
        if auto_approved
        else {}
    )
    body = VoucherInput.model_validate(await content(db, current, revision))
    if action_name not in {"reject", "cancel", "decline", "expire"}:
        await validate_counter(db, current, body, capture=False)
    today = utcnow().astimezone(ZoneInfo(finance.timezone)).date()
    if action_name == "expire" and (
        body.fulfillment_terms is None
        or body.fulfillment_terms.valid_until is None
        or today <= body.fulfillment_terms.valid_until
    ):
        raise ConflictError("fulfillment validity has not expired")
    if action_name not in {"reject", "cancel", "decline", "expire"}:
        validate_content(
            body,
            policy,
            kind=evidence["kind"],
            profile=evidence["profile"],
            stage=target,
            today=today,
        )
        await validate_masters(
            db, current, body, capture=False, kind=evidence["kind"], profile=evidence["profile"]
        )
    if action_name == "submit" and evidence["kind"] == "PURCHASE" and body.invoice is not None:
        scan = await supplier_duplicates(db, current, voucher.id, body)
        # A check that hit its ceiling is a possible duplicate: fail closed until acknowledged.
        if (scan.items or scan.truncated) and not acknowledge_duplicate_bill:
            raise refusal(current, scan, body.invoice.bill_reference)
        if scan.items or scan.truncated:
            notes.append(ACKNOWLEDGED_NOTE if scan.items else INCOMPLETE_NOTE)
            changes |= {
                "duplicate_bill_acknowledged": True,
                "duplicate_voucher_ids": [str(row.id) for row in scan.items],
            }
            if scan.truncated:
                changes["duplicate_check_incomplete"] = True
    transition_reason = annotate(reason, *notes)
    if action_name in {"approve", "reject"}:
        db.add(
            m.VoucherApproval(
                **values(current),
                revision_id=revision.id,
                action=action_name,
                reason=reason,
                configuration_hash=revision.configuration_hash,
            )
        )
    if action_name == "issue":
        if body.invoice is not None and evidence["kind"] in {
            "SALES",
            "PURCHASE",
            "CREDIT_NOTE",
            "DEBIT_NOTE",
        }:
            raise ConflictError(
                "statutory invoice issuance requires the supported tax document profile"
            )
        series_id = (issue.series_id if issue else None) or policy.default_series_id
        # Invoice kinds are numbered on posting only (CLAUDE.md 6.6), never by a fallback here.
        if (
            series_id is None
            and policy.allowed_series_ids is None
            and evidence["kind"] not in {"SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"}
        ):
            series_id = await type_default_series(db, current, revision.type_revision_id)
        if policy.allowed_series_ids is not None and series_id not in policy.allowed_series_ids:
            raise ValidationFailedError("issue series is not allowed by voucher configuration")
        if series_id is None:
            raise ValidationFailedError("issue series is required")
        series = await get(db, current, m.VoucherNumberSeries, series_id, lock=True)
        if series.status != "ACTIVE":
            raise ConflictError("issue series retired")
        reset_date = (
            revision.fiscal_start_date
            if series.reset_policy == "FINANCIAL_YEAR"
            else dt.date(1000, 1, 1)
        )
        requested = issue.requested_sequence if issue else None
        manual = issue.manual_number if issue else None
        if requested is not None and manual is not None:
            raise ValidationFailedError("provide either a requested sequence or a manual number")
        if series.numbering_mode == "AUTOMATIC" and (requested is not None or manual):
            raise ValidationFailedError("automatic series does not permit manual numbering")
        if series.numbering_mode == "AUTOMATIC_WITH_OVERRIDE" and manual:
            raise ValidationFailedError("number override must be a numeric sequence")
        if series.numbering_mode == "MANUAL" and (manual is None or requested is not None):
            raise ValidationFailedError("manual series requires a complete number")
        prefix = series.prefix + (
            f"{revision.fiscal_start_date.year}/" if series.include_year else ""
        )
        if manual is not None:
            if not manual.startswith(prefix) or not manual.endswith(series.suffix):
                raise ValidationFailedError("manual number does not match series format")
            numeric = manual[len(prefix) : len(manual) - len(series.suffix) or None]
            if not numeric.isascii() or not numeric.isdecimal() or len(numeric) > 19:
                raise ValidationFailedError("manual number needs a numeric sequence")
            sequence = int(numeric)
            if sequence < series.start_value or sequence >= 2**63 - 1:
                raise ValidationFailedError("manual sequence is outside series bounds")
            if manual != f"{prefix}{str(sequence).zfill(series.padding)}{series.suffix}":
                raise ValidationFailedError("manual number is not canonical for series")
        else:
            sequence = None
        counter = await db.scalar(
            select(m.VoucherNumberCounter)
            .where(
                m.VoucherNumberCounter.company_id == current.context.company_id,
                m.VoucherNumberCounter.series_id == series.id,
                m.VoucherNumberCounter.fiscal_start_date == reset_date,
            )
            .with_for_update()
        )
        if counter is None and series.numbering_mode != "MANUAL":
            counter = m.VoucherNumberCounter(
                **values(current),
                series_id=series.id,
                fiscal_start_date=reset_date,
                next_value=series.start_value,
            )
            db.add(counter)
            await db.flush()
        if requested is not None:
            if series.numbering_mode != "AUTOMATIC_WITH_OVERRIDE":
                raise ValidationFailedError("series does not allow numeric overrides")
            authorize(current, "series.manage")
            if not reason.strip() or requested < series.start_value:
                raise ValidationFailedError("override requires a reason and in-range sequence")
            sequence = requested
            assert counter is not None
            counter.next_value = max(counter.next_value, sequence + 1)
        elif series.numbering_mode != "MANUAL":
            assert counter is not None
            sequence = counter.next_value
            counter.next_value += 1
        assert sequence is not None
        if sequence >= 2**63 - 1:
            raise ConflictError("number sequence exhausted")
        exists = await db.scalar(
            select(m.VoucherNumberAssignment.id).where(
                m.VoucherNumberAssignment.company_id == current.context.company_id,
                m.VoucherNumberAssignment.series_id == series.id,
                m.VoucherNumberAssignment.fiscal_start_date == reset_date,
                m.VoucherNumberAssignment.sequence == sequence,
            )
        )
        if exists is not None:
            raise ConflictError("number already issued in this series and reset period")
        db.add(
            m.VoucherNumberAssignment(
                **values(current),
                series_id=series.id,
                revision_id=revision.id,
                fiscal_start_date=reset_date,
                sequence=sequence,
                display_number=f"{prefix}{str(sequence).zfill(series.padding)}{series.suffix}",
            )
        )
    db.add(
        m.VoucherTransition(
            **values(current),
            voucher_id=voucher.id,
            revision_id=revision.id,
            action=action_name,
            from_status=voucher.status,
            to_status=target,
            reason=transition_reason,
            voucher_version=voucher.row_version + 1,
        )
    )
    voucher.status = target
    voucher.row_version += 1
    voucher.updated_by = current.actor.user_id
    if notes:
        audit(
            db,
            current,
            "voucher",
            voucher.id,
            action_name,
            reason=transition_reason,
            changes=changes,
        )
    else:
        audit(db, current, "voucher", voucher.id, action_name)
    if target in {"ISSUED", "ACCEPTED"}:
        from vouchers.tasks.notifications import automatic

        await automatic(db, voucher, revision)
    elif target in {"CANCELLED", "DECLINED", "EXPIRED"}:
        from vouchers.tasks.notifications import emit_terminal_state

        emit_terminal_state(db, voucher)
    return voucher


async def authors(db: AsyncSession, current: Access, voucher: m.Voucher) -> set[uuid.UUID]:
    """Everyone who created the voucher, wrote any revision of it, or submitted it.

    Approval is separation of duties over the whole voucher: whoever wrote any part of what is being
    approved, acceptance revisions included, or put it forward for approval, is not an independent
    approver, whichever revision happens to be current. Every ``submit`` counts, so a resubmission
    after a rejection does not clear the earlier submitter.
    """
    people = set(
        await db.scalars(
            select(m.VoucherRevision.created_by)
            .where(
                m.VoucherRevision.company_id == current.context.company_id,
                m.VoucherRevision.voucher_id == voucher.id,
            )
            .distinct()
            .limit(1000)
        )
    )
    people |= set(
        await db.scalars(
            select(m.VoucherTransition.created_by)
            .where(
                m.VoucherTransition.company_id == current.context.company_id,
                m.VoucherTransition.voucher_id == voucher.id,
                m.VoucherTransition.action == "submit",
            )
            .distinct()
            .limit(1000)
        )
    )
    people.add(voucher.created_by)
    return {person for person in people if person is not None}


async def supplier_duplicates(
    db: AsyncSession, current: Access, voucher_id: uuid.UUID, body: VoucherInput
) -> DuplicateScan:
    """Other live Purchase bills with this bill number from the same supplier.

    The same supplier means any SUPPLIER named in the header or the payable ledger this bill
    posts to, so a Purchase that names no header party is still checked.
    """
    assert body.invoice is not None
    return await find_duplicate_bills(
        db,
        current,
        party_ids=[row.party_id for row in body.parties if row.role == "SUPPLIER"],
        party_account_id=body.invoice.party_account_id,
        bill_reference=body.invoice.bill_reference,
        document_date=body.document_date,
        exclude_voucher_id=voucher_id,
    )


async def guard_execution(db: AsyncSession, current: Access, voucher_id: uuid.UUID) -> None:
    pending = await db.scalar(
        select(m.VoucherOperation.id)
        .where(
            m.VoucherOperation.company_id == current.context.company_id,
            m.VoucherOperation.voucher_id == voucher_id,
            m.VoucherOperation.purpose.in_(["POST", "REVERSE"]),
            m.VoucherOperation.status.in_(["PENDING", "COMMITTED"]),
        )
        .limit(1)
    )
    if pending is not None:
        raise ConflictError("reconcile pending execution or use a supported posted correction")
