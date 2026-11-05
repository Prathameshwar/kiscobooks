"""India GST calculation — one mechanism for Billing invoices and Accounting vouchers.

Pure and framework-free: no database, no HTTP, no clock. Callers resolve the
registration, rule and rate valid on the document's ``posting_date`` from their
local replicas and pass the result in; this module only computes, so the same
inputs produce the same amounts in every service (docs/tax-accounting-plan.md
Phase 4).

Vocabularies mirror Catalog's tax tables exactly (``tax_rate_component``,
``tax_rate_series.applicability``, ``tax_rule.treatment``) and Accounting's party
``registration_type``, so replica rows map onto these types without translation.

Arithmetic is exact (``Fraction``) until one documented rounding per amount:

* each percentage / fixed-cess component rounds once, by its own
  ``rounding_mode``, to the company's ``amount_precision``;
* a tax-inclusive line back-calculates its taxable value, rounds it by the
  document rounding mode, and absorbs the residual so
  ``taxable + Σtax == gross`` exactly;
* an assessable-value charge is apportioned by cumulative rounding, so shares
  are never negative and the last eligible line absorbs the residual.

Nothing statutory is hardcoded: which states use UTGST is reference data the
caller supplies, and rates come from Catalog's published rows.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Final

from billing_platform.constants import MONEY_MAX, MONEY_SCALE
from billing_platform.errors import ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.money import MoneyError, RoundingMode

#: Version of :meth:`TaxComputation.snapshot`. Bump on any shape change; posting
#: services persist the snapshot and reprints must read every version shipped.
SNAPSHOT_SCHEMA_VERSION: Final = 1

MAX_LINES: Final = 2000
MAX_COMPONENTS: Final = 16  # matches tax_rate_component.position BETWEEN 0 AND 15
MAX_CHARGES: Final = 64


class SupplyContext(StrEnum):
    """``tax_rate_series.applicability``."""

    INTRA_STATE = "INTRA_STATE"
    INTRA_UT = "INTRA_UT"
    INTER_STATE = "INTER_STATE"


class SupplyReason(StrEnum):
    """Why :func:`place_of_supply` chose its context; persisted in the snapshot."""

    EXPORT = "EXPORT"
    SEZ = "SEZ"
    SAME_STATE = "SAME_STATE"
    SAME_UT = "SAME_UT"
    DIFFERENT_STATE = "DIFFERENT_STATE"


class BuyerType(StrEnum):
    """Accounting party ``registration_type``."""

    REGULAR = "REGULAR"
    COMPOSITION = "COMPOSITION"
    UNREGISTERED = "UNREGISTERED"
    SEZ_UNIT = "SEZ_UNIT"
    SEZ_DEVELOPER = "SEZ_DEVELOPER"
    UIN = "UIN"
    OVERSEAS = "OVERSEAS"
    CASUAL = "CASUAL"
    NRTP = "NRTP"
    OTHER = "OTHER"


class SupplyKind(StrEnum):
    GOODS = "GOODS"
    SERVICE = "SERVICE"


class Treatment(StrEnum):
    """``tax_rule.treatment``."""

    TAXABLE = "TAXABLE"
    NIL_RATED = "NIL_RATED"
    EXEMPT = "EXEMPT"
    NON_GST = "NON_GST"


class ComponentCode(StrEnum):
    """``tax_rate_component.component``; declaration order is the output order."""

    CGST = "CGST"
    SGST = "SGST"
    UTGST = "UTGST"
    IGST = "IGST"
    CESS = "CESS"


class ComponentKind(StrEnum):
    PERCENT = "PERCENT"
    FIXED_PER_UNIT = "FIXED_PER_UNIT"


class ComponentRounding(StrEnum):
    """``tax_rate_component.rounding_mode``. ``UP`` is away from zero (a ceiling,
    since every amount here is non-negative)."""

    HALF_UP = "HALF_UP"
    UP = "UP"
    DOWN = "DOWN"


class PriceBasis(StrEnum):
    EXCLUSIVE = "EXCLUSIVE"
    INCLUSIVE = "INCLUSIVE"


class ChargeScope(StrEnum):
    """TallyPrime *Include in assessable value calculation for*."""

    GOODS = "GOODS"
    SERVICES = "SERVICES"
    BOTH = "BOTH"


class ApportionBy(StrEnum):
    VALUE = "VALUE"
    QUANTITY = "QUANTITY"


#: GST components (cess aside) each context requires — exactly these, once each.
CONTEXT_COMPONENTS: Final[dict[SupplyContext, Counter[ComponentCode]]] = {
    SupplyContext.INTRA_STATE: Counter({ComponentCode.CGST: 1, ComponentCode.SGST: 1}),
    SupplyContext.INTRA_UT: Counter({ComponentCode.CGST: 1, ComponentCode.UTGST: 1}),
    SupplyContext.INTER_STATE: Counter({ComponentCode.IGST: 1}),
}

_SEZ: Final = frozenset({BuyerType.SEZ_UNIT, BuyerType.SEZ_DEVELOPER})
_ORDER: Final = {code: index for index, code in enumerate(ComponentCode)}


def _fail(message: str, path: str, detail: str) -> ValidationFailedError:
    return ValidationFailedError(message, fields={path: detail})


def _enum[E: StrEnum](kind: type[E], value: object, path: str) -> E:
    """Coerce replica strings to the vocabulary; an unknown value is a 422."""
    try:
        if not isinstance(value, str):
            raise ValueError(value)
        return kind(value)
    except ValueError:
        raise _fail(f"unknown {kind.__name__} {value!r}", path, "not in vocabulary") from None


# --------------------------------------------------------------------------- place of supply


@dataclass(frozen=True, slots=True)
class SupplyDetermination:
    context: SupplyContext
    zero_rated: bool
    reason: SupplyReason

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", _enum(SupplyContext, self.context, "context"))
        object.__setattr__(self, "reason", _enum(SupplyReason, self.reason, "reason"))
        if type(self.zero_rated) is not bool:
            raise _fail("zero_rated must be a boolean", "zero_rated", "boolean required")


def _state(value: str, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 10:
        raise _fail("state code is required", path, "a state code of 1-10 characters")
    return value.strip().upper()


def place_of_supply(
    supplier_state: str,
    place_of_supply_state: str | None,
    buyer_type: BuyerType | str,
    *,
    utgst_states: frozenset[str],
) -> SupplyDetermination:
    """Classify a supply into the context whose rate series applies.

    ``utgst_states`` is the set of state codes (from reference data) that levy
    UTGST instead of SGST — Union Territories without a legislature.
    """
    supplier = _state(supplier_state, "supplier_state")
    buyer = _enum(BuyerType, buyer_type, "buyer_type")
    if buyer is BuyerType.OVERSEAS or place_of_supply_state is None:
        return SupplyDetermination(SupplyContext.INTER_STATE, True, SupplyReason.EXPORT)
    if buyer in _SEZ:
        return SupplyDetermination(SupplyContext.INTER_STATE, True, SupplyReason.SEZ)
    destination = _state(place_of_supply_state, "place_of_supply_state")
    if destination != supplier:
        return SupplyDetermination(SupplyContext.INTER_STATE, False, SupplyReason.DIFFERENT_STATE)
    if supplier in {_state(code, "utgst_states") for code in utgst_states}:
        return SupplyDetermination(SupplyContext.INTRA_UT, False, SupplyReason.SAME_UT)
    return SupplyDetermination(SupplyContext.INTRA_STATE, False, SupplyReason.SAME_STATE)


# --------------------------------------------------------------------------- request


@dataclass(frozen=True, slots=True)
class TaxComponent:
    """One ``tax_rate_component`` row of the rate valid on the posting date."""

    component: ComponentCode
    kind: ComponentKind
    rounding_mode: ComponentRounding
    position: int
    percentage: Decimal | None = None
    amount: Decimal | None = None
    currency: str | None = None
    unit_id: uuid.UUID | None = None
    basis_quantity: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "component", _enum(ComponentCode, self.component, "component"))
        object.__setattr__(self, "kind", _enum(ComponentKind, self.kind, "kind"))
        object.__setattr__(
            self, "rounding_mode", _enum(ComponentRounding, self.rounding_mode, "rounding_mode")
        )


@dataclass(frozen=True, slots=True)
class TaxLine:
    key: str
    supply_kind: SupplyKind
    value: Decimal
    treatment: Treatment
    components: tuple[TaxComponent, ...] = ()
    price_basis: PriceBasis = PriceBasis.EXCLUSIVE
    quantity: Decimal | None = None
    unit_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "supply_kind", _enum(SupplyKind, self.supply_kind, "supply_kind"))
        object.__setattr__(self, "treatment", _enum(Treatment, self.treatment, "treatment"))
        object.__setattr__(self, "price_basis", _enum(PriceBasis, self.price_basis, "price_basis"))
        object.__setattr__(self, "components", tuple(self.components))


@dataclass(frozen=True, slots=True)
class AssessableCharge:
    """A charge folded into eligible lines' taxable value before tax."""

    key: str
    amount: Decimal
    applies_to: ChargeScope
    apportion_by: ApportionBy

    def __post_init__(self) -> None:
        object.__setattr__(self, "applies_to", _enum(ChargeScope, self.applies_to, "applies_to"))
        object.__setattr__(
            self, "apportion_by", _enum(ApportionBy, self.apportion_by, "apportion_by")
        )


@dataclass(frozen=True, slots=True)
class TaxRequest:
    lines: tuple[TaxLine, ...]
    determination: SupplyDetermination
    currency: str
    amount_precision: int
    may_charge_tax: bool
    rounding_mode: RoundingMode = RoundingMode.HALF_UP
    #: Zero-rated supply under IGST payment (refund route) rather than LUT/bond.
    zero_rated_with_payment: bool = False
    charges: tuple[AssessableCharge, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines", tuple(self.lines))
        object.__setattr__(self, "charges", tuple(self.charges))
        object.__setattr__(
            self, "rounding_mode", _enum(RoundingMode, self.rounding_mode, "rounding_mode")
        )


# --------------------------------------------------------------------------- result


@dataclass(frozen=True, slots=True)
class ComponentResult:
    component: ComponentCode
    kind: ComponentKind
    rounding_mode: ComponentRounding
    position: int
    percentage: Decimal | None
    amount: Decimal | None
    basis_quantity: Decimal | None
    unit_id: uuid.UUID | None
    tax_amount: Decimal


@dataclass(frozen=True, slots=True)
class ChargeShare:
    key: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class LineResult:
    key: str
    supply_kind: SupplyKind
    treatment: Treatment
    price_basis: PriceBasis
    #: Net-of-tax line value before assessable charges.
    base_value: Decimal
    charges: tuple[ChargeShare, ...]
    #: ``base_value + Σcharges`` — the assessable value tax is computed on.
    taxable_value: Decimal
    components: tuple[ComponentResult, ...]
    tax_total: Decimal
    gross: Decimal


@dataclass(frozen=True, slots=True)
class ComponentTotal:
    component: ComponentCode
    tax_amount: Decimal


@dataclass(frozen=True, slots=True)
class TaxTotals:
    base_value: Decimal
    charges: Decimal
    taxable_value: Decimal
    tax_total: Decimal
    gross: Decimal


@dataclass(frozen=True, slots=True)
class TaxComputation:
    determination: SupplyDetermination
    currency: str
    amount_precision: int
    rounding_mode: RoundingMode
    may_charge_tax: bool
    zero_rated_with_payment: bool
    lines: tuple[LineResult, ...]
    component_totals: tuple[ComponentTotal, ...]
    totals: TaxTotals
    schema_version: int = field(default=SNAPSHOT_SCHEMA_VERSION)

    def snapshot(self) -> dict[str, object]:
        """JSON-safe *Tax Analysis*: decimals as strings, UUIDs as strings."""
        return {
            "schema_version": self.schema_version,
            "context": self.determination.context.value,
            "zero_rated": self.determination.zero_rated,
            "reason": self.determination.reason.value,
            "zero_rated_with_payment": self.zero_rated_with_payment,
            "may_charge_tax": self.may_charge_tax,
            "currency": self.currency,
            "amount_precision": self.amount_precision,
            "rounding_mode": self.rounding_mode.value,
            "lines": [_line_snapshot(line) for line in self.lines],
            "component_totals": [
                {"component": row.component.value, "tax_amount": str(row.tax_amount)}
                for row in self.component_totals
            ],
            "totals": {
                "base_value": str(self.totals.base_value),
                "charges": str(self.totals.charges),
                "taxable_value": str(self.totals.taxable_value),
                "tax_total": str(self.totals.tax_total),
                "gross": str(self.totals.gross),
            },
        }


def _opt(value: object) -> str | None:
    return None if value is None else str(value)


def _line_snapshot(line: LineResult) -> dict[str, object]:
    return {
        "key": line.key,
        "supply_kind": line.supply_kind.value,
        "treatment": line.treatment.value,
        "price_basis": line.price_basis.value,
        "base_value": str(line.base_value),
        "charges": [{"key": c.key, "amount": str(c.amount)} for c in line.charges],
        "taxable_value": str(line.taxable_value),
        "components": [
            {
                "component": c.component.value,
                "kind": c.kind.value,
                "rounding_mode": c.rounding_mode.value,
                "position": c.position,
                "percentage": _opt(c.percentage),
                "amount": _opt(c.amount),
                "basis_quantity": _opt(c.basis_quantity),
                "unit_id": _opt(c.unit_id),
                "tax_amount": str(c.tax_amount),
            }
            for c in line.components
        ],
        "tax_total": str(line.tax_total),
        "gross": str(line.gross),
    }


# --------------------------------------------------------------------------- arithmetic


def _round(value: Fraction, places: int, mode: str) -> Fraction:
    """Round a non-negative exact value once, to ``places`` decimals."""
    scale = 10**places
    quotient, remainder = divmod(value.numerator * scale, value.denominator)
    twice, mode = 2 * remainder, mode.upper()
    if remainder and (
        mode == "UP"
        or (mode == "HALF_UP" and twice >= value.denominator)
        or (
            mode == "HALF_EVEN"
            and (twice > value.denominator or (twice == value.denominator and quotient % 2))
        )
    ):
        quotient += 1
    return Fraction(quotient, scale)


def _decimal(value: Fraction, places: int, path: str) -> Decimal:
    """Exact Decimal at ``places`` decimals; ``value`` is already on that grid."""
    if value > Fraction(MONEY_MAX):
        raise _fail("computed amount exceeds DECIMAL(19,4)", path, "out of range")
    integer = value.numerator * 10**places // value.denominator
    digits = tuple(map(int, str(integer)))
    return Decimal((0, digits, -places))


def _amount(value: Decimal | int | str | None, places: int, path: str) -> Decimal:
    """Validated non-negative input, exactly representable at ``places`` decimals."""
    if value is None:
        raise _fail(f"{path} is required", path, "required")
    try:
        result = exact_decimal(value, decimal_places=places)
    except MoneyError as exc:
        raise _fail(f"{path}: {exc}", path, str(exc)) from None
    if result < 0:
        raise _fail(f"{path} must not be negative", path, "must be >= 0")
    return result


# --------------------------------------------------------------------------- validation


@dataclass(frozen=True, slots=True)
class _Rate:
    """A validated component: either ``percent`` or ``per_unit`` (amount / basis)."""

    source: TaxComponent
    percentage: Decimal | None = None
    amount: Decimal | None = None
    basis_quantity: Decimal | None = None

    @property
    def percent(self) -> Fraction | None:
        return None if self.percentage is None else Fraction(self.percentage)

    @property
    def per_unit(self) -> Fraction | None:
        if self.amount is None or self.basis_quantity is None:
            return None
        return Fraction(self.amount) / Fraction(self.basis_quantity)

    def tax(self, taxable: Fraction, quantity: Fraction, places: int) -> Fraction:
        percent, per_unit = self.percent, self.per_unit
        exact = taxable * percent / 100 if percent is not None else quantity * (per_unit or 0)
        return _round(exact, places, self.source.rounding_mode.value)


def _validate_components(
    line: TaxLine, index: int, request: TaxRequest, currency: str
) -> tuple[_Rate, ...]:
    path = f"lines[{index}].components"
    components = line.components
    if len(components) > MAX_COMPONENTS:
        raise _fail("too many tax components on a line", path, f"at most {MAX_COMPONENTS}")
    if len({c.position for c in components}) != len(components):
        raise _fail("component positions must be distinct", path, "duplicate position")
    nil_rated = line.treatment is Treatment.NIL_RATED
    if nil_rated and any(c.kind is not ComponentKind.PERCENT for c in components):
        raise _fail("nil-rated lines carry only 0% components", path, "fixed cess on nil-rated")
    rates: list[_Rate] = []
    for position, comp in enumerate(sorted(components, key=lambda c: c.position)):
        cpath = f"{path}[{position}]"
        if type(comp.position) is not int or not 0 <= comp.position < MAX_COMPONENTS:
            raise _fail("component position out of range", cpath, "0..15")
        if comp.kind is ComponentKind.PERCENT:
            if comp.percentage is None or any(
                v is not None
                for v in (comp.amount, comp.currency, comp.unit_id, comp.basis_quantity)
            ):
                raise _fail("percent component needs only a percentage", cpath, "shape")
            pct = _amount(comp.percentage, MONEY_SCALE, f"{cpath}.percentage")
            if comp.component is not ComponentCode.CESS and pct > 100:
                raise _fail("GST percentage cannot exceed 100", cpath, "0..100")
            rates.append(_Rate(comp, percentage=pct))
            continue
        if comp.component is not ComponentCode.CESS:
            raise _fail("only cess may be a fixed per-unit amount", cpath, "CESS only")
        if comp.percentage is not None or None in (
            comp.amount,
            comp.currency,
            comp.unit_id,
            comp.basis_quantity,
        ):
            raise _fail("fixed cess needs amount, currency, unit and basis", cpath, "shape")
        if comp.currency != currency:
            raise _fail("fixed cess currency differs from the document", cpath, "currency")
        amount = _amount(comp.amount, MONEY_SCALE, f"{cpath}.amount")
        basis = _amount(comp.basis_quantity, MONEY_SCALE, f"{cpath}.basis_quantity")
        if amount == 0 or basis == 0:
            raise _fail("fixed cess amount and basis must be positive", cpath, "must be > 0")
        if line.quantity is None or line.unit_id != comp.unit_id:
            raise _fail(
                "fixed per-unit cess needs the line quantity in the rate's unit",
                f"lines[{index}].quantity",
                "quantity in the cess unit required",
            )
        rates.append(_Rate(comp, amount=amount, basis_quantity=basis))

    charges_tax = any(r.percentage or r.amount for r in rates)
    if nil_rated:
        # Catalog publishes nil-rated rates as explicit 0% GST so the Tax Analysis
        # shows the rate; they are still checked against the supply context below.
        if charges_tax:
            raise _fail("nil-rated lines carry only 0% components", path, "non-zero rate")
        if not components:
            return ()
    elif line.treatment is not Treatment.TAXABLE:
        if components:
            raise _fail(
                f"{line.treatment.value} lines carry no tax components", path, "must be empty"
            )
        return ()
    if not request.may_charge_tax:
        if charges_tax:
            raise _fail(
                "the supplier's registration may not charge tax on this document",
                path,
                "regime may not charge tax",
            )
        if not components:
            return ()
    context = request.determination.context
    gst = [r for r in rates if r.source.component is not ComponentCode.CESS]
    if Counter(r.source.component for r in gst) != CONTEXT_COMPONENTS[context]:
        raise _fail(
            f"components do not match the {context.value} supply context",
            path,
            "component set mismatch",
        )
    if len(gst) == 2 and (
        gst[0].percentage != gst[1].percentage
        or gst[0].source.rounding_mode is not gst[1].source.rounding_mode
    ):
        raise _fail(
            "central and state/UT GST must share percentage and rounding",
            path,
            "CGST must equal SGST/UTGST",
        )
    return tuple(rates)


def _apportion(
    charges: Sequence[AssessableCharge],
    lines: Sequence[TaxLine],
    quantities: Sequence[Fraction | None],
    values: Sequence[Fraction],
    places: int,
    mode: str,
) -> list[list[ChargeShare]]:
    shares: list[list[ChargeShare]] = [[] for _ in lines]
    for c_index, charge in enumerate(charges):
        path = f"charges[{c_index}]"
        amount = Fraction(_amount(charge.amount, places, f"{path}.amount"))
        eligible = [
            i
            for i, line in enumerate(lines)
            if charge.applies_to is ChargeScope.BOTH
            or (charge.applies_to is ChargeScope.GOODS) == (line.supply_kind is SupplyKind.GOODS)
        ]
        if not eligible:
            raise _fail("no line is eligible for this assessable charge", path, "no eligible line")
        if any(lines[i].price_basis is PriceBasis.INCLUSIVE for i in eligible):
            raise _fail(
                "assessable charges cannot be apportioned onto tax-inclusive lines",
                path,
                "eligible line is INCLUSIVE",
            )
        weights: list[Fraction] = []
        for i in eligible:
            if charge.apportion_by is ApportionBy.VALUE:
                weights.append(values[i])
                continue
            quantity = quantities[i]
            if quantity is None:
                raise _fail(
                    "apportion by quantity needs a quantity on every eligible line",
                    f"lines[{i}].quantity",
                    "required",
                )
            weights.append(quantity)
        total = sum(weights, Fraction())
        if total == 0 and amount:
            raise _fail("eligible lines have zero total weight", path, "cannot apportion")
        # Cumulative rounding: share_k = R(cum_k) - R(cum_{k-1}). Shares are never
        # negative and the last eligible line absorbs the residual exactly.
        running = Fraction()
        allocated = Fraction()
        for position, (i, weight) in enumerate(zip(eligible, weights, strict=True)):
            running += weight
            if position == len(eligible) - 1:
                target = amount
            else:
                target = _round(amount * running / total, places, mode) if total else Fraction()
            share = target - allocated
            allocated = target
            shares[i].append(ChargeShare(charge.key, _decimal(share, places, path)))
    return shares


# --------------------------------------------------------------------------- compute


def _validate_request(request: TaxRequest) -> str:
    places = request.amount_precision
    if type(places) is not int or not 0 <= places <= MONEY_SCALE:
        raise _fail("amount precision must be 0..4", "amount_precision", "0..4")
    currency = request.currency
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isupper():
        raise _fail("currency must be an ISO 4217 code", "currency", "three upper-case letters")
    if (
        type(request.may_charge_tax) is not bool
        or type(request.zero_rated_with_payment) is not bool
    ):
        raise _fail("flags must be booleans", "may_charge_tax", "boolean required")
    if not isinstance(request.determination, SupplyDetermination):
        raise _fail("a supply determination is required", "determination", "required")
    if not 1 <= len(request.lines) <= MAX_LINES:
        raise _fail("a document needs 1..2000 lines", "lines", f"1..{MAX_LINES}")
    if len(request.charges) > MAX_CHARGES:
        raise _fail("too many assessable charges", "charges", f"at most {MAX_CHARGES}")
    for name, keys in (
        ("lines", [line.key for line in request.lines]),
        ("charges", [charge.key for charge in request.charges]),
    ):
        if any(not isinstance(k, str) or not k or len(k) > 64 for k in keys):
            raise _fail("keys must be 1..64 character strings", name, "invalid key")
        if len(set(keys)) != len(keys):
            raise _fail("keys must be unique", name, "duplicate key")
    return currency


def _line_amounts(
    line: TaxLine,
    rates: tuple[_Rate, ...],
    value: Fraction,
    charge_total: Fraction,
    quantity: Fraction,
    places: int,
    doc_mode: str,
    suppress: bool,
    path: str,
) -> tuple[Fraction, Fraction, list[Fraction]]:
    """``(base, taxable, component amounts)`` for one line."""

    def taxes(taxable: Fraction) -> list[Fraction]:
        if suppress:
            return [Fraction()] * len(rates)
        return [rate.tax(taxable, quantity, places) for rate in rates]

    if line.price_basis is PriceBasis.EXCLUSIVE:
        return value, value + charge_total, taxes(value + charge_total)
    # INCLUSIVE: value is the gross. Fixed cess does not depend on the taxable
    # value, so it comes off first; the percentages then divide what remains.
    fixed = Fraction()
    percent = Fraction()
    if not suppress:
        for rate in rates:
            if rate.percent is None:
                fixed += rate.tax(Fraction(), quantity, places)
            else:
                percent += rate.percent
    if fixed > value:
        raise _fail("fixed cess exceeds the tax-inclusive line value", path, "value too small")
    estimate = _round((value - fixed) / (1 + percent / 100), places, doc_mode)
    amounts = taxes(estimate)
    taxable = value - sum(amounts, Fraction())  # residual lands here: taxable + Σtax == gross
    if taxable < 0:
        raise _fail("tax-inclusive value cannot carry its tax", path, "value too small")
    return taxable, taxable, amounts


def compute(request: TaxRequest) -> TaxComputation:
    """Compute per-line, per-component GST for one document."""
    currency = _validate_request(request)
    places = request.amount_precision
    doc_mode = request.rounding_mode.value
    # Zero-rated under LUT/bond: rates are recorded, amounts are zero.
    suppress = request.determination.zero_rated and not request.zero_rated_with_payment

    values: list[Fraction] = []
    quantities: list[Fraction | None] = []
    rates: list[tuple[_Rate, ...]] = []
    for index, line in enumerate(request.lines):
        values.append(Fraction(_amount(line.value, places, f"lines[{index}].value")))
        quantities.append(
            None
            if line.quantity is None
            else Fraction(_amount(line.quantity, MONEY_SCALE, f"lines[{index}].quantity"))
        )
        rates.append(_validate_components(line, index, request, currency))

    shares = _apportion(request.charges, request.lines, quantities, values, places, doc_mode)

    results: list[LineResult] = []
    sums: dict[ComponentCode, Fraction] = {}
    totals = [Fraction()] * 5
    for index, line in enumerate(request.lines):
        path = f"lines[{index}]"
        charge_total = sum((Fraction(s.amount) for s in shares[index]), Fraction())
        base, taxable, amounts = _line_amounts(
            line,
            rates[index],
            values[index],
            charge_total,
            quantities[index] or Fraction(),
            places,
            doc_mode,
            suppress,
            path,
        )
        tax_total = sum(amounts, Fraction())
        gross = taxable + tax_total
        components = []
        for rate, amount in zip(rates[index], amounts, strict=True):
            sums[rate.source.component] = sums.get(rate.source.component, Fraction()) + amount
            components.append(
                ComponentResult(
                    component=rate.source.component,
                    kind=rate.source.kind,
                    rounding_mode=rate.source.rounding_mode,
                    position=rate.source.position,
                    percentage=rate.percentage,
                    amount=rate.amount,
                    basis_quantity=rate.basis_quantity,
                    unit_id=rate.source.unit_id,
                    tax_amount=_decimal(amount, places, path),
                )
            )
        for slot, amount in enumerate((base, charge_total, taxable, tax_total, gross)):
            totals[slot] += amount
        results.append(
            LineResult(
                key=line.key,
                supply_kind=line.supply_kind,
                treatment=line.treatment,
                price_basis=line.price_basis,
                base_value=_decimal(base, places, path),
                charges=tuple(shares[index]),
                taxable_value=_decimal(taxable, places, path),
                components=tuple(components),
                tax_total=_decimal(tax_total, places, path),
                gross=_decimal(gross, places, path),
            )
        )

    return TaxComputation(
        determination=request.determination,
        currency=currency,
        amount_precision=places,
        rounding_mode=request.rounding_mode,
        may_charge_tax=request.may_charge_tax,
        zero_rated_with_payment=request.zero_rated_with_payment,
        lines=tuple(results),
        component_totals=tuple(
            ComponentTotal(code, _decimal(sums[code], places, "component_totals"))
            for code in sorted(sums, key=_ORDER.__getitem__)
        ),
        totals=TaxTotals(*(_decimal(t, places, "totals") for t in totals)),
    )
