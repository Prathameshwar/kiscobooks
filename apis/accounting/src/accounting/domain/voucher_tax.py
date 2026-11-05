"""Pure voucher-tax rules: place of supply, posting purposes and the party amount.

No framework or database imports. The task layer resolves masters by ``posting_date`` and
feeds them here; everything that decides an amount or an account purpose lives in this
module so it can be tested without a database.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from billing_platform.idempotency import canonical_json
from billing_platform.tax_calc import (
    BuyerType,
    SupplyContext,
    SupplyDetermination,
    SupplyReason,
    TaxComputation,
    place_of_supply,
)

Side = Literal["DEBIT", "CREDIT"]
Direction = Literal["SALE", "PURCHASE"]
ZERO = Decimal(0)
SNAPSHOT_VERSION = 1

#: Every reason a voucher's Tax Analysis can be in exception. Posting refuses all of them.
EXCEPTION_CODES = frozenset(
    {
        "FOREIGN_CURRENCY",
        "DEFAULT_MISSING",
        "COMPANY_REGISTRATION_MISSING",
        "COMPANY_REGISTRATION_AMBIGUOUS",
        "COMPANY_REGISTRATION_EXPIRED",
        "PARTY_REGISTRATION_MISSING",
        "PARTY_REGISTRATION_EXPIRED",
        "PLACE_OF_SUPPLY_MISSING",
        "MIXED_REVERSE_CHARGE",
        "RULE_MISSING",
        "RULE_INACTIVE",
        "RATE_MISSING",
        "RATE_AMBIGUOUS",
        "REGIME_REFUSED",
        "COMPUTATION_REFUSED",
        "MAPPING_MISSING",
        "WITHHOLDING_KIND",
        "WITHHOLDING_UNRESOLVED",
        "FISCAL_YEAR_MISSING",
        "PARTY_AMOUNT_MISMATCH",
        "UNBALANCED",
        "LINE_LIMIT",
    }
)

#: Supplier registrations that charge GST on their own invoice. A composition, unregistered,
#: UIN or overseas supplier does not; tax then arises only under reverse charge.
CHARGING_SUPPLIERS = frozenset({"REGULAR", "SEZ_UNIT", "SEZ_DEVELOPER", "CASUAL", "NRTP"})
_OFFSHORE = frozenset({"OVERSEAS", "SEZ_UNIT", "SEZ_DEVELOPER"})


@dataclass(frozen=True, slots=True)
class TaxException:
    code: str
    message: str
    line: int | None = None

    def __post_init__(self) -> None:
        if self.code not in EXCEPTION_CODES:
            raise ValueError(f"unknown voucher tax exception {self.code}")


@dataclass(frozen=True, slots=True)
class TaxedLine:
    """One voucher line carrying a resolved account tax default."""

    key: str
    account_id: uuid.UUID
    reverse_charge: bool
    #: Input credit recoverable on this line (default ELIGIBLE and a recovering regime).
    recover: bool


@dataclass(frozen=True, slots=True)
class Posting:
    """A generated journal effect: a mapping purpose, or a direct account (capitalized tax)."""

    side: Side
    amount: Decimal
    purpose: str | None = None
    account_id: uuid.UUID | None = None


def bare_state(code: str | None) -> str | None:
    """``IN-MH`` and ``MH`` compare equal; Catalog compares states the same way."""
    if code is None or not code.strip():
        return None
    value = code.strip().upper()
    return value.split("-", 1)[1] if "-" in value else value


def side_of(direction: Direction) -> Side:
    """The side a taxable line sits on: income is credited, purchases are debited."""
    return "CREDIT" if direction == "SALE" else "DEBIT"


def opposite(side: Side) -> Side:
    return "DEBIT" if side == "CREDIT" else "CREDIT"


def determine(
    direction: Direction,
    company_state: str,
    party_type: str,
    party_state: str | None,
    place: str | None,
    *,
    utgst_states: frozenset[str],
) -> SupplyDetermination | TaxException:
    """Classify the supply. Purchases take the supplier's state as the origin.

    A sale's place of supply is the explicit one, else the buyer's state. A purchase lands in
    the company's state unless stated otherwise. Imports and SEZ supplies to the company are
    inter-state and taxable (tax then arises by reverse charge or customs, never zero-rated).
    """
    utgst = frozenset(state for code in utgst_states if (state := bare_state(code)))
    if direction == "SALE":
        destination = bare_state(place) or party_state
        if destination is None and party_type not in _OFFSHORE:
            return TaxException("PLACE_OF_SUPPLY_MISSING", "the sale has no place of supply")
        return place_of_supply(company_state, destination, party_type, utgst_states=utgst)
    if party_type in _OFFSHORE:
        return SupplyDetermination(SupplyContext.INTER_STATE, False, SupplyReason.DIFFERENT_STATE)
    if party_state is None:
        return TaxException("PLACE_OF_SUPPLY_MISSING", "the supplier's state is unknown")
    destination = bare_state(place) or company_state
    return place_of_supply(party_state, destination, BuyerType.REGULAR, utgst_states=utgst)


def supplier_charges(direction: Direction, party_type: str) -> bool:
    """Whether the counterparty's own document carries GST (always true for our sale)."""
    return direction == "SALE" or party_type in CHARGING_SUPPLIERS


def gst_postings(
    direction: Direction, computation: TaxComputation, lines: Sequence[TaxedLine]
) -> list[Posting]:
    """Tax lines for a computation, in line then component order.

    SALE credits OUTPUT_<c>. PURCHASE debits INPUT_<c> when the credit is recoverable,
    otherwise the line's own expense or asset account (the tax is part of its cost).
    Reverse charge additionally credits RCM_<c>, the liability the recipient owes.
    """
    by_key = {line.key: line for line in lines}
    output: list[Posting] = []
    for result in computation.lines:
        line = by_key[result.key]
        for component in result.components:
            amount = component.tax_amount
            if amount == ZERO:
                continue
            code = component.component.value
            if direction == "SALE":
                output.append(Posting("CREDIT", amount, purpose=f"OUTPUT_{code}"))
                continue
            output.append(
                Posting("DEBIT", amount, purpose=f"INPUT_{code}")
                if line.recover
                else Posting("DEBIT", amount, account_id=line.account_id)
            )
            if line.reverse_charge:
                output.append(Posting("CREDIT", amount, purpose=f"RCM_{code}"))
    return output


def supplier_tax(computation: TaxComputation | None, lines: Sequence[TaxedLine]) -> Decimal:
    """Tax the counterparty bills: everything except reverse-charge tax."""
    if computation is None:
        return ZERO
    reverse = {line.key for line in lines if line.reverse_charge}
    return sum(
        (result.tax_total for result in computation.lines if result.key not in reverse), ZERO
    )


def withholding_base(kind: str, taxable: Decimal, gross: Decimal, amount: Decimal) -> Decimal:
    """The amount a section's threshold and rate apply to.

    BILL: the taxable value, excluding GST shown separately. PAYMENT: the amount paid.
    INVOICE (TCS): the gross consideration including GST.
    """
    if kind == "BILL":
        return taxable
    if kind == "PAYMENT":
        return amount
    return gross


def party_amount(
    kind: str, taxable: Decimal, charged: Decimal, tax_total: Decimal, withheld: Decimal
) -> Decimal:
    """What the party line must carry for the voucher to balance."""
    if kind == "INVOICE":
        return taxable + tax_total + withheld
    if kind == "BILL":
        return taxable + charged - withheld
    return taxable


def aggregate(
    postings: Iterable[tuple[uuid.UUID, Side, Decimal]],
) -> list[tuple[uuid.UUID, Side, Decimal]]:
    """Merge generated effects by (account, side), keeping first-appearance order."""
    totals: dict[tuple[uuid.UUID, Side], Decimal] = {}
    for account, side, amount in postings:
        totals[(account, side)] = totals.get((account, side), ZERO) + amount
    return [(account, side, amount) for (account, side), amount in totals.items() if amount]


def balance(lines: Iterable[tuple[Side, Decimal]]) -> Decimal:
    """Debits minus credits."""
    return sum((amount if side == "DEBIT" else -amount for side, amount in lines), ZERO)


def snapshot_hash(snapshot: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(snapshot)).hexdigest()
