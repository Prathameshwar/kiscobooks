"""Deterministic opening declarations and native journal boundaries; no I/O."""

import hashlib
from decimal import Decimal
from typing import Any

from billing_platform.constants import MONEY_MAX
from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.money import RoundingMode

from accounting.domain.ledger import Entry, base_value, value_entries
from accounting.schemas.financial_opening import OpeningDeclaration
from accounting.schemas.ledger import JournalLineCreate
from accounting.schemas.subledger import OpeningBill, OpeningCreate


def opening_plan(payload: dict[str, Any]) -> OpeningCreate:
    return OpeningCreate.model_validate(
        {key: value for key, value in payload.items() if key != "entry_source_keys"}
    )


def declaration_hash(body: OpeningDeclaration) -> str:
    try:
        encoded = canonical_json(body.model_dump(mode="json"), maximum_bytes=2097152)
    except ValueError as problem:
        raise ValidationFailedError("opening declaration exceeds the two MiB limit") from problem
    return hashlib.sha256(encoded).hexdigest()


def execution_chunks(
    body: OpeningDeclaration, currency: str, precision: int, rounding: RoundingMode
) -> list[OpeningCreate]:
    if body.currency != currency:
        raise ValidationFailedError("opening declaration must use company base currency")
    amounts = [
        entry.base_amount
        or base_value(
            entry.amount, entry.currency, entry.exchange_rate, currency, precision, rounding
        )
        for entry in body.entries
    ]
    debit = sum(
        (
            value
            for entry, value in zip(body.entries, amounts, strict=True)
            if entry.side == "DEBIT"
        ),
        Decimal(0),
    )
    credit = sum(
        (
            value
            for entry, value in zip(body.entries, amounts, strict=True)
            if entry.side == "CREDIT"
        ),
        Decimal(0),
    )
    if debit != credit or debit > MONEY_MAX:
        raise ValidationFailedError(
            "opening debits and credits must balance within the supported monetary range"
        )
    large = len(body.entries) > 200 or sum(len(entry.documents) for entry in body.entries) > 1000
    if large and body.clearing_account_id is None:
        raise ValidationFailedError(
            "large openings require a configured migration clearing account"
        )
    if body.clearing_account_id in {entry.account_id for entry in body.entries}:
        raise ValidationFailedError("migration clearing cannot also be a declared opening account")

    groups: list[list[int]] = []
    group: list[int] = []
    documents = 0
    for index, entry in enumerate(body.entries):
        if group and (
            len(group) >= (199 if large else 200) or documents + len(entry.documents) > 1000
        ):
            groups.append(group)
            group = []
            documents = 0
        group.append(index)
        documents += len(entry.documents)
    if group:
        groups.append(group)
    result = []
    for indexes in groups:
        lines = [
            JournalLineCreate(
                account_id=body.entries[index].account_id,
                side=body.entries[index].side,
                currency=body.entries[index].currency,
                amount=body.entries[index].amount,
                exchange_rate=body.entries[index].exchange_rate,
                description=body.entries[index].description,
                opening_base_amount=amounts[index],
            )
            for index in indexes
        ]
        difference = sum(
            (
                amounts[index] if body.entries[index].side == "DEBIT" else -amounts[index]
                for index in indexes
            ),
            Decimal(0),
        )
        if difference:
            if body.clearing_account_id is None:
                raise ValidationFailedError(
                    "bounded native execution requires a configured clearing account"
                )
            lines.append(
                JournalLineCreate(
                    account_id=body.clearing_account_id,
                    side="CREDIT" if difference > 0 else "DEBIT",
                    currency=currency,
                    amount=abs(difference),
                    exchange_rate=Decimal(1),
                    opening_base_amount=abs(difference),
                    description="Reviewed migration clearing; final net balance must be zero",
                )
            )
        value_entries(
            tuple(
                Entry(line.account_id, line.side, line.currency, line.amount, line.exchange_rate)
                for line in lines
            ),
            currency,
            precision,
            rounding,
            opening_values=tuple(line.opening_base_amount for line in lines),
        )
        bills = [
            OpeningBill.model_validate(document.model_dump() | {"line_sequence": sequence})
            for sequence, index in enumerate(indexes, 1)
            for document in body.entries[index].documents
        ]
        result.append(
            OpeningCreate(
                posting_date=body.posting_date, description=body.reason, lines=lines, bills=bills
            )
        )
    if (
        sum(
            (
                sum(
                    (
                        line.opening_base_amount or line.amount
                        for line in plan.lines
                        if line.side == "DEBIT"
                    ),
                    Decimal(0),
                )
                for plan in result
            ),
            Decimal(0),
        )
        > MONEY_MAX
    ):
        raise ValidationFailedError(
            "opening execution including clearing exceeds the supported monetary range"
        )
    return result
