"""Signed, scoped owner facts for Vouchers; never a cross-service database read."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import (
    authenticate_snapshot,
    authorize_snapshot,
    require_snapshot_scope,
    response_headers,
)
from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
OWNER = "accounting"


# Service authentication: explicit Vouchers credential plus company grant.
@router.get(
    "/internal/v1/voucher-sources/{tenant_id}/{company_id}/{entity}", include_in_schema=False
)
async def voucher_sources(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    entity: str,
    request: Request,
    after: uuid.UUID | None = None,
    limit: int = Query(default=128, ge=1, le=128),
) -> Response:
    credential, framed, key_id = authenticate_snapshot(
        request.app.state.settings.voucher_snapshot_credentials,
        owner=OWNER,
        headers=request.headers,
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        body=await request.body(),
    )
    if set(request.query_params) - {"after", "limit"} or len(request.query_params) != len(
        request.query_params.multi_items()
    ):
        raise ValidationFailedError("unsupported snapshot query")
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            enrolled = False
            if credential.allow_enrolled_companies:
                from accounting.models.masters import AccountingSetup

                enrolled = (
                    await db.scalar(
                        select(AccountingSetup.id).where(AccountingSetup.company_id == company_id)
                    )
                    is not None
                )
            require_snapshot_scope(
                credential, tenant_id=tenant_id, company_id=company_id, enrolled=enrolled
            )
            bundle, next_after = await facts(db, tenant_id, company_id, entity, after, limit)
    body = canonical_json({"bundle": bundle, "next_after": str(next_after) if next_after else None})
    return Response(
        body,
        media_type="application/json",
        headers=response_headers(
            credential, owner=OWNER, key_id=key_id, request_bytes=framed, body=body
        ),
    )


async def facts(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    entity: str,
    after: uuid.UUID | None,
    limit: int,
) -> tuple[dict[str, Any], uuid.UUID | None]:
    from accounting.models.fiscal import FiscalPeriod
    from accounting.models.masters import Account, Party, PartyDrugLicence, PartyRole

    if entity == "broker_party":
        role_statement = select(PartyRole).where(
            PartyRole.company_id == company_id, PartyRole.role == "BROKER"
        )
        if after is not None:
            role_statement = role_statement.where(PartyRole.id > after)
        roles = list(await db.scalars(role_statement.order_by(PartyRole.id).limit(limit + 1)))
        selected_roles = roles[:limit]
        broker_facts = []
        for role in selected_roles:
            party = await db.get(Party, role.party_id)
            if party is None or party.company_id != company_id:
                raise ValidationFailedError("broker party source is unavailable")
            broker_facts.append(
                {
                    "entity_type": "broker_party",
                    "source_id": str(role.party_id),
                    "source_version": int(
                        max(role.updated_at, party.updated_at).timestamp() * 1000000
                    ),
                    "status": (
                        "ACTIVE"
                        if role.status == "ACTIVE" and party.status == "ACTIVE"
                        else "RETIRED"
                    ),
                    "facts": {"party_id": str(role.party_id), "name": party.name},
                }
            )
        return {
            "message_id": str(uuid7()),
            "tenant_id": str(tenant_id),
            "company_id": str(company_id),
            "definitions": [],
            "masters": broker_facts,
        }, selected_roles[-1].id if len(roles) > limit else None

    models: dict[str, Any] = {
        "party": Party,
        "account": Account,
        "fiscal_period": FiscalPeriod,
        "party_drug_licence": PartyDrugLicence,
    }
    if entity not in models:
        raise ValidationFailedError("unsupported Accounting source entity")
    model = models[entity]
    statement = select(model).where(model.company_id == company_id)
    if after:
        statement = statement.where(model.id > after)
    rows = list(await db.scalars(statement.order_by(model.id).limit(limit + 1)))
    selected = rows[:limit]
    bundle = {
        "message_id": str(uuid7()),
        "tenant_id": str(tenant_id),
        "company_id": str(company_id),
        "definitions": [],
        "masters": [
            {
                "entity_type": entity,
                "source_id": str(row.id),
                "source_version": row.row_version,
                "status": "ACTIVE"
                if entity == "party_drug_licence" or row.status in {"ACTIVE", "OPEN"}
                else "RETIRED",
                "facts": (
                    {
                        "party_id": str(row.party_id),
                        "address_id": str(row.address_id),
                        "licence_form": row.licence_form,
                        "licence_number": row.licence_number,
                        "valid_from": row.valid_from.isoformat(),
                        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
                        "source_sha256": row.source_sha256,
                        "reviewed_at": row.reviewed_at.isoformat(),
                        "reviewed_by": str(row.reviewed_by),
                    }
                    if entity == "party_drug_licence"
                    else {
                        key: str(getattr(row, key)) if getattr(row, key) is not None else None
                        for key in (
                            (
                                "kind",
                                "currency_mode",
                                "currency",
                                "party_id",
                                "party_role",
                                "posting_policy",
                            )
                            if entity == "account"
                            else ("start_date", "end_date", "status", "fiscal_year_id")
                            if entity == "fiscal_period"
                            else ()
                        )
                    }
                ),
            }
            for row in selected
        ],
    }
    return bundle, selected[-1].id if len(rows) > limit else None


CODE = r"^[^\x00-\x1f]{1,40}$"
GSTIN = r"^[0-9A-Z]{15}$"


class BillLookup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    account_id: uuid.UUID
    reference: str = Field(min_length=1, max_length=120)


class InvoiceLookup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["SALES", "PURCHASE"]
    party_account_id: uuid.UUID
    bill_reference: str = Field(min_length=1, max_length=120)


class MasterLookup(BaseModel):
    """Exact company-scoped code lookup; display names and private facts never leave."""

    model_config = ConfigDict(extra="forbid")
    party_codes: list[Annotated[str, Field(pattern=CODE)]] = Field(default=[], max_length=500)
    party_gstins: list[Annotated[str, Field(pattern=GSTIN)]] = Field(default=[], max_length=500)
    account_codes: list[Annotated[str, Field(pattern=CODE)]] = Field(default=[], max_length=500)
    # Open bills a payment/receipt line settles: exact ledger + bill reference.
    bills: list[BillLookup] = Field(default=[], max_length=500)
    # Original invoices a credit/debit note returns against.
    invoices: list[InvoiceLookup] = Field(default=[], max_length=200)


def lookup_status(status: str) -> str:
    return "ACTIVE" if status in {"ACTIVE", "OPEN"} else "RETIRED"


# Service authentication: the same Vouchers snapshot credential and company grant.
@router.post("/internal/v1/voucher-lookups/{tenant_id}/{company_id}", include_in_schema=False)
async def voucher_lookups(
    tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request
) -> Response:
    raw = await request.body()
    credential, framed, key_id = authorize_snapshot(
        request.app.state.settings.voucher_snapshot_credentials,
        owner=OWNER,
        tenant_id=tenant_id,
        company_id=company_id,
        headers=request.headers,
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        body=raw,
    )
    if request.url.query:
        raise ValidationFailedError("unsupported lookup query")
    try:
        query = MasterLookup.model_validate_json(raw)
    except PydanticValidationError as error:
        raise ValidationFailedError("invalid master lookup") from error
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            result = await lookups(db, company_id, query)
    body = canonical_json(result)
    return Response(
        body,
        media_type="application/json",
        headers=response_headers(
            credential, owner=OWNER, key_id=key_id, request_bytes=framed, body=body
        ),
    )


async def lookups(db: AsyncSession, company_id: uuid.UUID, query: MasterLookup) -> dict[str, Any]:
    from accounting.models.masters import Account, Party, PartyTaxRegistration

    registrations = (
        list(
            await db.scalars(
                select(PartyTaxRegistration)
                .where(
                    PartyTaxRegistration.company_id == company_id,
                    PartyTaxRegistration.scheme == "GST_IN",
                    PartyTaxRegistration.registration_number.in_(set(query.party_gstins)),
                )
                .order_by(PartyTaxRegistration.id)
                .limit(1001)
            )
        )
        if query.party_gstins
        else []
    )
    parties = (
        list(
            await db.scalars(
                select(Party)
                .where(Party.company_id == company_id, Party.code.in_(set(query.party_codes)))
                .order_by(Party.id)
            )
        )
        if query.party_codes
        else []
    )
    party_ids = {row.id for row in parties} | {row.party_id for row in registrations}
    party_accounts = (
        list(
            await db.scalars(
                select(Account)
                .where(
                    Account.company_id == company_id,
                    Account.kind == "PARTY",
                    Account.party_id.in_(party_ids),
                )
                .order_by(Account.id)
                .limit(5001)
            )
        )
        if party_ids
        else []
    )
    accounts = (
        list(
            await db.scalars(
                select(Account)
                .where(Account.company_id == company_id, Account.code.in_(set(query.account_codes)))
                .order_by(Account.id)
            )
        )
        if query.account_codes
        else []
    )
    if len(registrations) > 1000 or len(party_accounts) > 5000:
        raise ValidationFailedError("master lookup exceeds its supported bound")
    if registrations:
        parties.extend(
            await db.scalars(
                select(Party)
                .where(
                    Party.company_id == company_id,
                    Party.id.in_({row.party_id for row in registrations} - {p.id for p in parties}),
                )
                .order_by(Party.id)
            )
        )
    return {
        "parties": [
            {
                "code": row.code,
                "source_id": str(row.id),
                "source_version": row.row_version,
                "status": lookup_status(row.status),
            }
            for row in parties
        ],
        "registrations": [
            {
                "registration_number": row.registration_number,
                "party_id": str(row.party_id),
                "valid_from": row.valid_from.isoformat() if row.valid_from else None,
                "valid_to": row.valid_to.isoformat() if row.valid_to else None,
            }
            for row in registrations
        ],
        "party_accounts": [
            {
                "code": row.code,
                "source_id": str(row.id),
                "source_version": row.row_version,
                "status": lookup_status(row.status),
                "party_id": str(row.party_id),
                "party_role": row.party_role,
                "currency": row.currency,
            }
            for row in party_accounts
        ],
        "accounts": [
            {
                "code": row.code,
                "source_id": str(row.id),
                "source_version": row.row_version,
                "status": lookup_status(row.status),
                "kind": row.kind,
                "currency": row.currency,
                "party_id": str(row.party_id) if row.party_id else None,
                "party_role": row.party_role,
                "posting_policy": row.posting_policy,
            }
            for row in accounts
        ],
        "bills": await open_bills(db, company_id, query.bills),
        "invoices": await original_invoices(db, company_id, query.invoices),
    }


async def open_bills(
    db: AsyncSession, company_id: uuid.UUID, wanted: list[BillLookup]
) -> list[dict[str, Any]]:
    """Active open items with their remaining amount today; posted allocations only."""
    from accounting.models.subledger import OpenItem
    from accounting.tasks.subledger_reads import active, remaining

    if not wanted:
        return []
    today = dt.date.today()
    rows = list(
        await db.execute(
            select(OpenItem, remaining(today))
            .where(
                OpenItem.company_id == company_id,
                OpenItem.account_id.in_({row.account_id for row in wanted}),
                # Account narrows by index; references compare case-insensitively on any engine.
                func.lower(OpenItem.reference).in_({row.reference.lower() for row in wanted}),
                active(today),
            )
            .order_by(OpenItem.id)
            .limit(1001)
        )
    )
    if len(rows) > 1000:
        raise ValidationFailedError("bill lookup exceeds its supported bound")
    pairs = {(row.account_id, row.reference.casefold()) for row in wanted}
    return [
        {
            "item_id": str(item.id),
            "account_id": str(item.account_id),
            "reference": item.reference,
            "direction": item.direction,
            "currency": item.currency,
            "remaining": format(left, "f"),
        }
        for item, left in rows
        if (item.account_id, item.reference.casefold()) in pairs
    ]


async def has_components(db: AsyncSession, company_id: uuid.UUID, invoice_id: uuid.UUID) -> bool:
    from accounting.models.invoice import InvoiceComponentFact, InvoiceTaxComponent

    for model in (InvoiceComponentFact, InvoiceTaxComponent):
        if await db.scalar(
            select(model.id)
            .where(model.company_id == company_id, model.invoice_id == invoice_id)
            .limit(1)
        ):
            return True
    return False


async def original_invoices(
    db: AsyncSession, company_id: uuid.UUID, wanted: list[InvoiceLookup]
) -> list[dict[str, Any]]:
    """Original invoices with each supply line's remaining return entitlement."""
    from accounting.models.invoice import InvoiceRecord, InvoiceSupplyFact
    from accounting.tasks.invoice_execution import claimed, committed_source

    result: list[dict[str, Any]] = []
    # One original per kind, ledger and number however the caller cased it.
    for want in {(row.kind, row.party_account_id, row.bill_reference.lower()) for row in wanted}:
        kind, account_id, reference = want
        records = list(
            await db.scalars(
                select(InvoiceRecord)
                .where(
                    InvoiceRecord.company_id == company_id,
                    InvoiceRecord.kind == kind,
                    InvoiceRecord.party_account_id == account_id,
                    func.lower(InvoiceRecord.bill_reference) == reference.lower(),
                )
                .order_by(InvoiceRecord.id)
                .limit(11)
            )
        )
        for record in records[:10]:
            consumed = await claimed(db, company_id, record.id)
            lines = list(
                await db.scalars(
                    select(InvoiceSupplyFact)
                    .where(
                        InvoiceSupplyFact.company_id == company_id,
                        InvoiceSupplyFact.invoice_id == record.id,
                    )
                    .order_by(InvoiceSupplyFact.sequence)
                    .limit(201)
                )
            )
            result.append(
                {
                    "source_id": str(record.id),
                    "kind": record.kind,
                    "party_account_id": str(record.party_account_id),
                    "bill_reference": record.bill_reference,
                    "currency": record.currency,
                    "posting_date": record.posting_date.isoformat(),
                    "committed": await committed_source(db, company_id, record),
                    # Only untaxed originals without adjustments support financial notes.
                    "simple": not record.tax_total
                    and not record.rounding
                    and not await has_components(db, company_id, record.id),
                    "lines": [
                        {
                            "line_key": str(line.line_key),
                            "sequence": line.sequence,
                            "account_id": str(line.account_id),
                            "supply_kind": line.supply_kind,
                            "untaxed": line.tax_profile == "UNTAXED_ACCOUNT",
                            "commercial": format(line.commercial, "f"),
                            "remaining": format(
                                line.commercial - consumed.get(line.line_key, Decimal(0)), "f"
                            ),
                        }
                        for line in lines[:200]
                    ],
                }
            )
    return result
