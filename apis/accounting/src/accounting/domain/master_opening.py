"""Exact pending balances and historical bills, independent of I/O and posting."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.errors import ValidationFailedError

from accounting.schemas.financial_opening import OnAccountOpeningDocument, OpeningEntry
from accounting.schemas.master_opening import MasterOpeningInput


def reject(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError(message, fields={"opening." + field: message})


def entry(
    body: MasterOpeningInput,
    *,
    account_id: uuid.UUID,
    role: str | None,
    party: bool,
    currency: str,
    base_currency: str,
    opening_date: dt.date,
) -> OpeningEntry:
    if body.opening_date != opening_date:
        raise reject("opening_date", "Opening date must match the company's books-begin date.")
    foreign = currency != base_currency
    if foreign and (body.exchange_rate is None or body.base_amount is None):
        raise reject("base_amount", "Enter the exchange rate and historical carrying value.")
    if not foreign and (
        body.exchange_rate not in (None, Decimal(1)) or body.base_amount not in (None, body.amount)
    ):
        raise reject("base_amount", "Company-currency opening uses rate 1 and an equal base value.")
    carrying = body.base_amount if foreign else body.amount
    rate = body.exchange_rate if foreign else Decimal(1)
    assert carrying is not None and rate is not None
    documents = list(body.documents)
    if documents and (not party or role not in {"CUSTOMER", "SUPPLIER"}):
        raise reject("documents", "Bill-wise openings require a customer or supplier ledger.")
    references: set[str] = set()
    debt = (role == "CUSTOMER") == (body.side == "DEBIT")
    kinds = {"INVOICE" if role == "CUSTOMER" else "BILL"} if debt else {"ADVANCE", "CREDIT_NOTE"}
    for index, bill in enumerate(documents):
        field = f"documents.{index}"
        if bill.line_sequence != 1:
            raise reject(
                field + ".line_sequence", "Each bill belongs to this opening account line."
            )
        if bill.document_kind not in kinds:
            raise reject(
                field + ".document_kind", "Choose a bill type matching this role and Dr/Cr."
            )
        if bill.original_amount is None or bill.original_amount <= 0 or bill.amount <= 0:
            raise reject(field + ".amount", "Enter positive original and pending bill amounts.")
        if bill.document_date >= opening_date or bill.due_date < bill.document_date:
            raise reject(
                field + ".document_date",
                "Bill must predate opening; due date cannot precede bill date.",
            )
        reference = bill.reference.strip().casefold()
        if reference in references:
            raise reject(field + ".reference", "Bill numbers must be unique for this account.")
        references.add(reference)
        if foreign and (bill.base_amount is None or bill.base_amount <= 0):
            raise reject(
                field + ".base_amount",
                "Enter each bill's historical pending value in company currency.",
            )
        if not foreign and bill.base_amount not in (None, bill.amount):
            raise reject(
                field + ".base_amount", "Company-currency pending and base amounts must match."
            )
    if documents and sum((bill.amount for bill in documents), Decimal(0)) != body.amount:
        raise reject("amount", "Opening must equal the total pending bill amount.")
    if (
        documents
        and foreign
        and sum((bill.base_amount or Decimal(0) for bill in documents), Decimal(0)) != carrying
    ):
        raise reject(
            "base_amount", "Bill carrying values must equal this account's carrying value."
        )
    key = "mob-" + account_id.hex
    result = OpeningEntry(
        source_key=key,
        account_id=account_id,
        side=body.side,
        currency=currency,
        amount=body.amount,
        exchange_rate=rate,
        base_amount=carrying,
        documents=[
            bill.model_copy(
                update={
                    "reference": bill.reference.strip(),
                    "base_amount": bill.base_amount if foreign else bill.amount,
                }
            )
            for bill in documents
        ],
    )
    if party and not documents:
        result.documents = [
            OnAccountOpeningDocument(
                reference="ON_ACCOUNT",
                amount=body.amount,
                base_amount=carrying,
                document_kind="ON_ACCOUNT",
            )
        ]
    return result
