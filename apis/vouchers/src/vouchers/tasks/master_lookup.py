"""Signed exact-code master lookup at the owner, outside every voucher transaction."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Literal

import httpx
from billing_platform.errors import AuthenticationRequiredError, ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import request_headers, verify_response
from billing_platform.service_auth import service_request_bytes
from pydantic import BaseModel, ConfigDict, Field

from vouchers.domain.imports import (
    AccountFacts,
    Master,
    OpenBill,
    OriginalInvoice,
    OriginalLine,
    Resolution,
)
from vouchers.schemas.owners import Owner


class _Exact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LookupParty(_Exact):
    code: str
    source_id: uuid.UUID
    source_version: int = Field(ge=1)
    status: Literal["ACTIVE", "RETIRED"]


class LookupRegistration(_Exact):
    registration_number: str
    party_id: uuid.UUID
    valid_from: str | None
    valid_to: str | None


class LookupPartyAccount(LookupParty):
    party_id: uuid.UUID
    party_role: str | None
    currency: str | None


class LookupAccount(LookupParty):
    kind: str
    currency: str | None
    party_id: uuid.UUID | None = None
    party_role: str | None = None
    posting_policy: str | None = None


class LookupBill(_Exact):
    item_id: uuid.UUID
    account_id: uuid.UUID
    reference: str
    direction: Literal["DEBT", "CREDIT"]
    currency: str
    remaining: Decimal


class LookupInvoiceLine(_Exact):
    line_key: uuid.UUID
    sequence: int
    account_id: uuid.UUID
    supply_kind: str
    untaxed: bool
    commercial: Decimal
    remaining: Decimal


class LookupInvoice(_Exact):
    source_id: uuid.UUID
    kind: Literal["SALES", "PURCHASE"]
    party_account_id: uuid.UUID
    bill_reference: str
    currency: str
    posting_date: dt.date
    committed: bool
    simple: bool
    lines: tuple[LookupInvoiceLine, ...] = Field(max_length=200)


class LookupResult(_Exact):
    parties: tuple[LookupParty, ...] = Field(max_length=1500)
    registrations: tuple[LookupRegistration, ...] = Field(max_length=1000)
    party_accounts: tuple[LookupPartyAccount, ...] = Field(max_length=5000)
    accounts: tuple[LookupAccount, ...] = Field(max_length=500)
    bills: tuple[LookupBill, ...] = Field(default=(), max_length=1000)
    invoices: tuple[LookupInvoice, ...] = Field(default=(), max_length=2000)


BATCH = 500
INVOICE_BATCH = 200
Bill = tuple[uuid.UUID, str]
Invoice = tuple[str, uuid.UUID, str]


def owner_for(
    owner: Owner | None, tenant_id: uuid.UUID, company_id: uuid.UUID, purpose: str = "master lookup"
) -> Owner:
    """The configured Accounting owner, explicitly granted this tenant and company."""
    if (
        owner is None
        or owner.owner != "accounting"
        or not any(
            scope.tenant_id == tenant_id and scope.company_id == company_id
            for scope in owner.scopes
        )
    ):
        raise ConflictError(f"{purpose} owner is not configured for this company")
    return owner


def chunks[T](values: list[T], size: int, count: int) -> list[list[T]]:
    return [values[index * size : (index + 1) * size] for index in range(count)]


async def lookup(
    client: httpx.AsyncClient,
    owner: Owner,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    *,
    party_codes: set[str],
    party_gstins: set[str],
    account_codes: set[str],
    bills: set[Bill] | None = None,
    invoices: set[Invoice] | None = None,
) -> Resolution:
    """Every list stays within the owner's per-request bound; results are merged."""
    lists: list[list[Any]] = [
        sorted(party_codes),
        sorted(party_gstins),
        sorted(account_codes),
        sorted(bills or set(), key=str),
        sorted(invoices or set(), key=str),
    ]
    sizes = [BATCH, BATCH, BATCH, BATCH, INVOICE_BATCH]
    count = (
        max((len(values) + size - 1) // size for values, size in zip(lists, sizes, strict=True))
        or 1
    )
    parts = [chunks(values, size, count) for values, size in zip(lists, sizes, strict=True)]
    results = [
        await _request(client, owner, tenant_id, company_id, *(part[index] for part in parts))
        for index in range(count)
    ]
    return resolution(
        LookupResult.model_construct(
            parties=tuple(row for result in results for row in result.parties),
            registrations=tuple(row for result in results for row in result.registrations),
            party_accounts=tuple(row for result in results for row in result.party_accounts),
            accounts=tuple(row for result in results for row in result.accounts),
            bills=tuple(row for result in results for row in result.bills),
            invoices=tuple(row for result in results for row in result.invoices),
        )
    )


async def _request(
    client: httpx.AsyncClient,
    owner: Owner,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    party_codes: list[str],
    party_gstins: list[str],
    account_codes: list[str],
    bills: list[Bill],
    invoices: list[Invoice],
) -> LookupResult:
    body = canonical_json(
        {
            "party_codes": party_codes,
            "party_gstins": party_gstins,
            "account_codes": account_codes,
            "bills": [{"account_id": str(a), "reference": r} for a, r in bills],
            "invoices": [
                {"kind": k, "party_account_id": str(a), "bill_reference": r} for k, a, r in invoices
            ],
        }
    )
    url = httpx.URL(owner.origin + f"/internal/v1/voucher-lookups/{tenant_id}/{company_id}")
    framed = service_request_bytes(method="POST", path=url.path, query="", body=body)
    secret = owner.secret.get_secret_value().encode()
    response = await client.post(
        url,
        content=body,
        headers=request_headers(
            requester="vouchers",
            owner="accounting",
            key_id=owner.key_id,
            secret=secret,
            framed=framed,
        )
        | {"Content-Type": "application/json"},
    )
    response.raise_for_status()
    verify_response(
        requester="vouchers",
        owner="accounting",
        key_id=owner.key_id,
        secret=secret,
        framed=framed,
        body=response.content,
        headers=response.headers,
    )
    result = LookupResult.model_validate_json(response.content)
    # Owner codes are collated case-insensitively; anything else was never asked for.
    asked_parties = {code.casefold() for code in party_codes}
    asked_accounts = {code.casefold() for code in account_codes}
    asked_bills = {(account, reference.casefold()) for account, reference in bills}
    asked_invoices = {(k, a, r.casefold()) for k, a, r in invoices}
    registered = {row.party_id for row in result.registrations}
    if (
        any(row.registration_number not in party_gstins for row in result.registrations)
        or any(
            row.code.casefold() not in asked_parties and row.source_id not in registered
            for row in result.parties
        )
        or any(row.code.casefold() not in asked_accounts for row in result.accounts)
        or any(
            (row.account_id, row.reference.casefold()) not in asked_bills for row in result.bills
        )
        or any(
            (row.kind, row.party_account_id, row.bill_reference.casefold()) not in asked_invoices
            for row in result.invoices
        )
    ):
        raise AuthenticationRequiredError("owner returned masters that were not requested")
    return result


def resolution(result: LookupResult) -> Resolution:
    def master(row: LookupParty) -> Master:
        return Master(row.source_id, row.source_version, row.status)

    gstins: dict[str, list[uuid.UUID]] = {}
    for registration in result.registrations:
        ids = gstins.setdefault(registration.registration_number, [])
        if registration.party_id not in ids:
            ids.append(registration.party_id)
    ledgers: dict[uuid.UUID, list[tuple[str, Master, str | None]]] = {}
    for account in result.party_accounts:
        ledgers.setdefault(account.party_id, []).append(
            (account.code, master(account), account.party_role)
        )
    bills: dict[tuple[uuid.UUID, str], list[OpenBill]] = {}
    for bill in result.bills:
        bills.setdefault((bill.account_id, bill.reference.casefold()), []).append(
            OpenBill(bill.item_id, bill.direction, bill.currency, bill.remaining)
        )
    invoices: dict[tuple[str, uuid.UUID, str], list[OriginalInvoice]] = {}
    for invoice in result.invoices:
        invoices.setdefault(
            (invoice.kind, invoice.party_account_id, invoice.bill_reference.casefold()), []
        ).append(
            OriginalInvoice(
                invoice.source_id,
                invoice.currency,
                invoice.posting_date,
                invoice.committed and invoice.simple,
                tuple(
                    OriginalLine(
                        line.line_key,
                        line.sequence,
                        line.account_id,
                        line.supply_kind,
                        line.untaxed,
                        line.remaining,
                    )
                    for line in invoice.lines
                ),
            )
        )
    return Resolution(
        parties={row.code: master(row) for row in result.parties},
        gstin_parties={key: tuple(value) for key, value in gstins.items()},
        party_ids={row.source_id: master(row) for row in result.parties},
        party_ledgers={
            key: tuple((code, row) for code, row, _ in value) for key, value in ledgers.items()
        },
        accounts={row.code: master(row) for row in result.accounts},
        ledger_roles={row.source_id: role for value in ledgers.values() for _, row, role in value},
        account_facts={
            row.source_id: AccountFacts(
                row.kind, row.party_id, row.party_role, row.posting_policy, row.currency
            )
            for row in result.accounts
        },
        bills={key: tuple(value) for key, value in bills.items()},
        invoices={key: tuple(value) for key, value in invoices.items()},
    )
