"""Canonical bounded invoice arithmetic. Masters and statutory rules resolve before entry.

Fractions retain exact intermediate values; rounding is explicit at money boundaries.
These immutable inputs are resolved facts, never authorization for a caller's tax choices.
"""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import NoReturn

from billing_platform.errors import ValidationFailedError

ZERO = Decimal("0.0000")


def refuse(message: str) -> NoReturn:
    raise ValidationFailedError(message)


def exact(value: Decimal, *, scale: int = 4) -> Fraction:
    if not isinstance(value, Decimal) or not value.is_finite():
        refuse("invoice amounts must be finite exact decimals")
    result = Fraction(value)
    maximum = Fraction(10 ** (19 - scale)) - Fraction(1, 10**scale)
    if abs(result) > maximum or (result * 10**scale).denominator != 1:
        refuse("invoice amount exceeds its storage precision")
    return result


def money(value: Fraction, precision: int, mode: str = "HALF_UP") -> Decimal:
    if precision not in range(5) or mode not in {"HALF_UP", "HALF_EVEN", "UP", "DOWN"}:
        refuse("unsupported invoice rounding policy")
    sign = -1 if value < 0 else 1
    units = abs(value) * 10**precision
    whole, remainder = divmod(units.numerator, units.denominator)
    if (
        (mode == "UP" and remainder)
        or (mode == "HALF_UP" and remainder * 2 >= units.denominator)
        or (
            mode == "HALF_EVEN"
            and (
                remainder * 2 > units.denominator
                or (remainder * 2 == units.denominator and whole % 2)
            )
        )
    ):
        whole += 1
    result = Decimal((int(sign < 0), tuple(map(int, str(whole * 10 ** (4 - precision)))), -4))
    exact(result)
    return result


def apportion(
    total: Decimal, weights: tuple[tuple[str, Fraction], ...], precision: int
) -> dict[str, Decimal]:
    """Stable largest remainder, keyed by source identity rather than display position."""
    amount = exact(total)
    if (
        precision not in range(5)
        or not weights
        or len({key for key, _ in weights}) != len(weights)
        or any(value < 0 for _, value in weights)
        or (amount * 10**precision).denominator != 1
    ):
        refuse("invalid component allocation")
    denominator = sum((value for _, value in weights), Fraction())
    if denominator <= 0:
        refuse("component allocation has no eligible basis")
    units = abs(amount) * 10**precision
    shares = {key: units * weight / denominator for key, weight in weights}
    whole = {key: value.numerator // value.denominator for key, value in shares.items()}
    residual = int(units) - sum(whole.values())
    ordered = sorted(shares, key=lambda key: (-(shares[key] - whole[key]), key))
    for key in ordered[:residual]:
        whole[key] += 1
    sign = -1 if amount < 0 else 1
    return {
        key: money(Fraction(sign * count, 10**precision), precision) for key, count in whole.items()
    }


@dataclass(frozen=True)
class Quantity:
    name: str
    value: Decimal
    unit: str


@dataclass(frozen=True)
class Tax:
    key: str
    code: str
    rate: Decimal
    basis: str = "VALUE"
    quantity_basis: str | None = None
    unit: str | None = None
    denominator: Decimal = Decimal(1)
    supplier_charged: bool = True
    rounding_mode: str | None = None


@dataclass(frozen=True)
class Supply:
    key: str
    amount: Decimal
    inclusive: bool = False
    quantities: tuple[Quantity, ...] = ()
    taxes: tuple[Tax, ...] = ()


@dataclass(frozen=True)
class Component:
    key: str
    targets: tuple[str, ...]
    value: Decimal
    effect: str = "DEDUCT"
    kind: str = "PERCENT"
    dependencies: tuple[str, ...] = ()
    basis: str = "NET_EXCL_TAX"
    allocation: str = "VALUE"
    quantity_basis: str | None = None
    unit: str | None = None
    denominator: Decimal = Decimal(1)
    commercial: bool = True
    taxable: bool = True
    cost_targets: tuple[str, ...] = ()
    cost_allocation: str = "VALUE"
    tax_targets: tuple[str, ...] = ()
    tax_allocation: str | None = None


@dataclass(frozen=True)
class Allocation:
    component_key: str
    line_key: str
    purpose: str
    amount: Decimal


@dataclass(frozen=True)
class ComponentResult:
    key: str
    basis_amount: Decimal
    basis_quantity: Decimal | None
    input_amount: Decimal
    amount: Decimal


@dataclass(frozen=True)
class TaxResult:
    key: str
    code: str
    basis: Decimal
    amount: Decimal
    supplier_charged: bool


@dataclass(frozen=True)
class SupplyResult:
    key: str
    entered: Decimal
    commercial: Decimal
    taxable: Decimal
    taxes: tuple[TaxResult, ...]
    price_rounding: Decimal
    payable: Decimal


@dataclass(frozen=True)
class Calculation:
    version: int
    lines: tuple[SupplyResult, ...]
    components: tuple[ComponentResult, ...]
    allocations: tuple[Allocation, ...]
    commercial_total: Decimal
    tax_total: Decimal
    charged_tax_total: Decimal
    rounding: Decimal
    payable: Decimal


def quantity(line: Supply, name: str | None, unit: str | None) -> Fraction:
    matches = [row for row in line.quantities if row.name == name and row.unit == unit]
    if name is None or unit is None or len(matches) != 1:
        refuse("quantity basis and compatible unit evidence are required")
    result = exact(matches[0].value)
    if result < 0:
        refuse("invoice quantity cannot be negative")
    return result


def tax_recipe(line: Supply, *, charged_only: bool = False) -> tuple[Fraction, Fraction]:
    percent, fixed = Fraction(), Fraction()
    if len(line.taxes) > 8 or len({row.key for row in line.taxes}) != len(line.taxes):
        refuse("invalid or excessive tax components")
    for row in line.taxes:
        rate = exact(row.rate, scale=8)
        denominator = exact(row.denominator)
        if rate < 0 or denominator <= 0:
            refuse("invalid tax rate or unit denominator")
        if row.rounding_mode not in {None, "HALF_UP", "HALF_EVEN", "UP", "DOWN"}:
            refuse("unsupported tax component rounding policy")
        if row.basis == "VALUE":
            if row.quantity_basis is not None or row.unit is not None or denominator != 1:
                refuse("value tax cannot carry a quantity recipe")
            tax_percent, tax_fixed = rate / 100, Fraction()
        elif row.basis == "QUANTITY":
            tax_percent, tax_fixed = (
                Fraction(),
                rate * quantity(line, row.quantity_basis, row.unit) / denominator,
            )
        else:
            refuse("unsupported statutory tax recipe")
        if not charged_only or row.supplier_charged:
            percent += tax_percent
            fixed += tax_fixed
    return percent, fixed


def ordered_components(components: tuple[Component, ...], lines: set[str]) -> tuple[Component, ...]:
    if len(components) > 200 or len({row.key for row in components}) != len(components):
        refuse("invalid or excessive commercial components")
    pending = {row.key: row for row in components}
    allocation_count = 0
    for row in components:
        if (
            not row.key
            or row.key in lines
            or not 1 <= len(row.targets) <= 200
            or len(set(row.targets)) != len(row.targets)
            or not set(row.targets) <= lines
            or len(row.dependencies) > 32
            or len(set(row.dependencies)) != len(row.dependencies)
            or not set(row.dependencies) <= pending.keys()
            or row.key in row.dependencies
            or len(set(row.cost_targets)) != len(row.cost_targets)
            or not set(row.cost_targets) <= lines
            or len(set(row.tax_targets)) != len(row.tax_targets)
            or not set(row.tax_targets) <= lines
        ):
            refuse("component references are invalid or outside the revision")
        allocation_count += (
            len(row.targets) * int(row.commercial)
            + len(row.tax_targets or row.targets) * int(row.taxable)
            + len(row.cost_targets)
        )
        if (row.tax_targets or row.tax_allocation is not None) and (
            not row.taxable or row.basis == "GROSS_INCL_TAX"
        ):
            refuse("separate tax allocation requires an assessable net adjustment")
        if allocation_count > 4000:
            refuse("invoice exceeds the component allocation limit")
    result: list[Component] = []
    completed: set[str] = set()
    while pending:
        ready = sorted(key for key, row in pending.items() if set(row.dependencies) <= completed)
        if not ready:
            refuse("component dependencies contain a cycle")
        for key in ready:
            result.append(pending.pop(key))
            completed.add(key)
    return tuple(result)


def calculate(
    supplies: tuple[Supply, ...],
    components: tuple[Component, ...] = (),
    *,
    precision: int = 2,
    rounding_mode: str = "HALF_UP",
    invoice_increment: Decimal | None = None,
) -> Calculation:
    """Resolve named components once and retain independent commercial/tax/cost views."""
    money(Fraction(), precision, rounding_mode)
    if not 1 <= len(supplies) <= 200 or len({row.key for row in supplies}) != len(supplies):
        refuse("invoice requires one to 200 distinct supply lines")
    by_key = {row.key: row for row in supplies}
    bases: dict[str, Decimal] = {}
    price_bridge: dict[str, Fraction] = {}
    for supply in supplies:
        if not supply.key or len({q.name for q in supply.quantities}) != len(supply.quantities):
            refuse("supply and quantity identities must be distinct")
        if supply.inclusive and supply.taxes and not any(
            tax.supplier_charged for tax in supply.taxes
        ):
            refuse("tax-inclusive price requires a supplier-charged tax component")
        for q in supply.quantities:
            quantity(supply, q.name, q.unit)
        amount = exact(supply.amount)
        percent, fixed = tax_recipe(supply, charged_only=True)
        net = (amount - fixed) / (1 + percent) if supply.inclusive else amount
        if net < 0:
            refuse("tax-inclusive amount is below its fixed tax")
        bases[supply.key] = money(net, precision, rounding_mode)
        if supply.inclusive:
            price_bridge[supply.key] = amount - (
                Fraction(bases[supply.key]) * (1 + percent) + fixed
            )
    commercial = {key: Fraction(value) for key, value in bases.items()}
    taxable = dict(commercial)
    component_shares: dict[str, dict[str, Decimal]] = {}
    allocations: list[Allocation] = []
    results: list[ComponentResult] = []
    for row in ordered_components(components, set(by_key)):
        rate = exact(row.value, scale=8 if row.kind == "PERCENT" else 4)
        if rate < 0 or row.effect not in {"ADD", "DEDUCT"}:
            refuse("component amounts must be positive with a declared direction")
        if row.basis not in {"NET_EXCL_TAX", "GROSS_INCL_TAX"}:
            refuse("unsupported component amount basis")
        if not row.commercial and not row.taxable and not row.cost_targets:
            refuse("component has no declared effect")
        values = {
            key: Fraction(bases[key])
            + sum(
                (Fraction(component_shares[dep].get(key, ZERO)) for dep in row.dependencies),
                Fraction(),
            )
            for key in row.targets
        }
        if any(value < 0 for value in values.values()):
            refuse("component dependency produces a negative basis")
        if row.basis == "GROSS_INCL_TAX":
            gross_values = {}
            for key, base_value in values.items():
                percent, fixed = tax_recipe(by_key[key], charged_only=True)
                gross_values[key] = base_value * (1 + percent) + fixed + price_bridge.get(
                    key, Fraction()
                )
            values = gross_values
        basis_value = sum(values.values(), Fraction())
        quantity_value: Fraction | None = None
        if row.kind == "FIXED":
            amount = rate
        elif row.kind == "PERCENT":
            if row.effect == "DEDUCT" and rate > 100:
                refuse("discount percentage exceeds its eligible basis")
            amount = basis_value * rate / 100
        elif row.kind == "PER_QUANTITY":
            if row.allocation != "QUANTITY":
                refuse("per-quantity components require quantity allocation")
            denominator = exact(row.denominator)
            if denominator <= 0:
                refuse("quantity denominator must be positive")
            quantity_value = sum(
                (quantity(by_key[key], row.quantity_basis, row.unit) for key in row.targets),
                Fraction(),
            )
            amount = rate * quantity_value / denominator
        else:
            refuse("unsupported component input kind")
        if row.kind != "PER_QUANTITY" and exact(row.denominator) != 1:
            refuse("non-quantity component cannot carry a unit denominator")
        sign = -1 if row.effect == "DEDUCT" else 1
        input_amount = money(sign * amount, precision, rounding_mode)
        weights = allocation_weights(row.allocation, row, by_key, values, row.targets)
        shares = apportion(input_amount, weights, precision)
        if row.basis == "GROSS_INCL_TAX":
            if not row.commercial or not row.taxable:
                refuse("gross component requires commercial and tax-base treatment")
            # Extract each target's own rate; never average mixed-rate components.
            gross_shares = shares
            shares = {
                key: money(
                    Fraction(value) / (1 + tax_recipe(by_key[key], charged_only=True)[0]),
                    precision,
                    rounding_mode,
                )
                for key, value in shares.items()
            }
            for key, value in shares.items():
                if key not in price_bridge:
                    # Preserve the existing rounded exclusive consideration before
                    # introducing a gross-valued adjustment.
                    initial_tax = sum(
                        (
                            Fraction(
                                money(
                                    Fraction(bases[key]) * Fraction(t.rate) / 100
                                    if t.basis == "VALUE"
                                    else quantity(by_key[key], t.quantity_basis, t.unit)
                                    * Fraction(t.rate)
                                    / Fraction(t.denominator),
                                    precision,
                                    t.rounding_mode or rounding_mode,
                                )
                            )
                            for t in by_key[key].taxes
                            if t.supplier_charged
                        ),
                        Fraction(),
                    )
                    percent, fixed = tax_recipe(by_key[key], charged_only=True)
                    price_bridge[key] = initial_tax - Fraction(bases[key]) * percent - fixed
                percent, _ = tax_recipe(by_key[key], charged_only=True)
                price_bridge[key] += Fraction(gross_shares[key]) - Fraction(value) * (1 + percent)
        component_shares[row.key] = shares
        amount_net = money(
            sum((Fraction(value) for value in shares.values()), Fraction()), precision
        )
        results.append(
            ComponentResult(
                row.key,
                money(basis_value, precision, rounding_mode),
                money(quantity_value, 4) if quantity_value is not None else None,
                input_amount,
                amount_net,
            )
        )
        tax_shares = shares
        if row.tax_targets or row.tax_allocation is not None:
            tax_targets = row.tax_targets or row.targets
            tax_values = {
                key: Fraction(bases[key])
                + sum(
                    (Fraction(component_shares[dep].get(key, ZERO)) for dep in row.dependencies),
                    Fraction(),
                )
                for key in tax_targets
            }
            tax_shares = apportion(
                amount_net,
                allocation_weights(
                    row.tax_allocation or row.allocation, row, by_key, tax_values, tax_targets
                ),
                precision,
            )
        for purpose, enabled, totals, distribution in (
            ("COMMERCIAL", row.commercial, commercial, shares),
            ("TAX_BASE", row.taxable, taxable, tax_shares),
        ):
            if enabled:
                for key, share in distribution.items():
                    totals[key] += Fraction(share)
                    if totals[key] < 0:
                        refuse("discount exceeds an eligible line balance")
                    allocations.append(Allocation(row.key, key, purpose, share))
        if row.cost_targets:
            cost_values = {key: Fraction(bases[key]) for key in row.cost_targets}
            cost_weights = allocation_weights(
                row.cost_allocation, row, by_key, cost_values, row.cost_targets
            )
            allocations.extend(
                Allocation(row.key, key, "STOCK_COST", share)
                for key, share in apportion(amount_net, cost_weights, precision).items()
            )
    output: list[SupplyResult] = []
    for line in sorted(supplies, key=lambda row: row.key):
        taxes: list[TaxResult] = []
        for tax in line.taxes:
            base = (
                taxable[line.key]
                if tax.basis == "VALUE"
                else quantity(line, tax.quantity_basis, tax.unit)
            )
            amount = (
                base
                * Fraction(tax.rate)
                / (100 if tax.basis == "VALUE" else Fraction(tax.denominator))
            )
            taxes.append(
                TaxResult(
                    tax.key,
                    tax.code,
                    money(base, precision if tax.basis == "VALUE" else 4),
                    money(amount, precision, tax.rounding_mode or rounding_mode),
                    tax.supplier_charged,
                )
            )
        charged = sum((Fraction(row.amount) for row in taxes if row.supplier_charged), Fraction())
        line_total = commercial[line.key] + charged
        price_rounding = Fraction()
        if line.key in price_bridge:
            percent, fixed = tax_recipe(line, charged_only=True)
            exact_total = commercial[line.key] + taxable[line.key] * percent + fixed
            target = Fraction(money(exact_total + price_bridge[line.key], precision, rounding_mode))
            price_rounding = target - line_total
            line_total = target
        if line_total < 0:
            refuse("discount exceeds the gross consideration")
        output.append(
            SupplyResult(
                line.key,
                bases[line.key],
                money(commercial[line.key], precision),
                money(taxable[line.key], precision),
                tuple(taxes),
                money(price_rounding, precision),
                money(line_total, precision),
            )
        )
    net_total = sum((Fraction(row.commercial) for row in output), Fraction())
    tax_total = sum((Fraction(tax.amount) for row in output for tax in row.taxes), Fraction())
    charged_total = sum(
        (Fraction(tax.amount) for row in output for tax in row.taxes if tax.supplier_charged),
        Fraction(),
    )
    gross = sum((Fraction(row.payable) for row in output), Fraction())
    rounded = gross
    if invoice_increment is not None:
        increment = exact(invoice_increment)
        if increment <= 0 or (increment * 10**precision).denominator != 1:
            refuse("invoice increment must be positive and representable")
        rounded = Fraction(money(gross / increment, 0, rounding_mode)) * increment
    return Calculation(
        1,
        tuple(output),
        tuple(results),
        tuple(allocations),
        money(net_total, precision),
        money(tax_total, precision),
        money(charged_total, precision),
        money(rounded - net_total - charged_total, precision),
        money(rounded, precision),
    )


def allocation_weights(
    method: str,
    component: Component,
    lines: dict[str, Supply],
    values: dict[str, Fraction],
    targets: tuple[str, ...],
) -> tuple[tuple[str, Fraction], ...]:
    if method == "VALUE":
        return tuple((key, values[key]) for key in targets)
    if method == "QUANTITY":
        return tuple(
            (key, quantity(lines[key], component.quantity_basis, component.unit)) for key in targets
        )
    refuse("unsupported allocation basis")
