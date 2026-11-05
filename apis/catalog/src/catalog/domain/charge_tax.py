"""Version-two charge-tax statements Catalog signs for Accounting (pure; no database).

Contract: ``apis/accounting/contracts/catalog-tax-computation-v2.schema.json``. Amounts come
from ``billing_platform.tax_calc`` only — this module selects inputs and shapes the statement,
it never does tax arithmetic of its own. Money stays ``Decimal`` end to end and travels as an
exact string at the company's amount precision.

The statement names the company registration the supply is made under: the supplier-class
GST registration of the supplier's state that is valid on ``posting_date`` (never the
company's current registration). Accounting re-checks the same facts against its signed
Identity context and refuses any disagreement.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.money import RoundingMode
from billing_platform.service_auth import ServiceKey, sign_service_body
from billing_platform.statutory import covers
from billing_platform.tax import may_charge_tax, registration_class
from billing_platform.tax_calc import (
    BuyerType,
    SupplyDetermination,
    SupplyKind,
    TaxComponent,
    TaxLine,
    TaxRequest,
    Treatment,
    compute,
    place_of_supply,
)

VERSION: Final = 2
#: Accounting's ingest operation; the signature binds this, the issuer and the audience.
OPERATION: Final = "catalog.accounting_tax.assessed"
TAX_SYSTEM: Final = "gst_in"
#: Deterministic provider ids: the same inputs always name the same statement, so a retried
#: delivery dedupes in Accounting instead of conflicting with the first one.
PROVIDER_NAMESPACE: Final = uuid.UUID("0192f4a0-6c1e-7d3a-9b52-5f0c3e8a1d47")
MAX_COMPONENTS: Final = 5


@dataclass(frozen=True, slots=True)
class Registration:
    id: uuid.UUID
    regime: str
    registration_class: str | None
    jurisdiction_code: str
    valid_from: dt.date
    valid_to: dt.date | None


def parse_registration(value: Mapping[str, Any]) -> Registration | None:
    """Identity's registration transport row; ``None`` for another tax system."""
    if value.get("tax_system") != TAX_SYSTEM:
        return None
    try:
        start = dt.date.fromisoformat(str(value["valid_from"]))
        end = (
            None if value.get("valid_to") is None else dt.date.fromisoformat(str(value["valid_to"]))
        )
        regime = str(value["regime"])
        return Registration(
            id=uuid.UUID(str(value["id"])),
            regime=regime,
            registration_class=(
                None if "registration_class" not in value else str(value["registration_class"])
            ),
            jurisdiction_code=str(value["jurisdiction_code"]).strip().upper(),
            valid_from=start,
            valid_to=end,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationFailedError("company registration context is malformed") from exc


def jurisdiction(country_code: str, state_code: str) -> str:
    """Identity's ``IN-MH`` form of a company's ``MH`` state code."""
    state = state_code.strip().upper()
    return state if "-" in state else f"{country_code.strip().upper()}-{state}"


def supplier_registration(
    registrations: Iterable[Mapping[str, Any]],
    *,
    country_code: str,
    state_code: str,
    posting_date: dt.date,
) -> Registration | None:
    """The single supplier-class GST registration of the supplier state on ``posting_date``.

    An ISD or TDS-deductor GSTIN may coexist in the state and never charges; a row whose sent
    class disagrees with the class its regime implies fails closed (it is not a match). More
    than one match is ambiguous and refused rather than guessed.
    """
    target = jurisdiction(country_code, state_code)
    matches = []
    for value in registrations:
        entry = parse_registration(value)
        if entry is None or entry.jurisdiction_code != target:
            continue
        implied = registration_class(TAX_SYSTEM, entry.regime)
        sent = implied if entry.registration_class is None else entry.registration_class
        if implied != "supplier" or sent != implied:
            continue
        if covers(entry.valid_from, entry.valid_to, posting_date):
            matches.append(entry)
    if len(matches) > 1:
        raise ConflictError("more than one supplier GST registration is valid on that date")
    return matches[0] if matches else None


@dataclass(frozen=True, slots=True)
class ChargeTaxInput:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    assessment_id: uuid.UUID
    input_hash: str
    posting_date: dt.date
    currency: str
    net_amount: Decimal
    supply_kind: SupplyKind
    treatment: Treatment
    place_of_supply_state: str | None
    buyer_type: BuyerType
    quantity: Decimal | None = None
    unit_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class CompanyFacts:
    country_code: str
    state_code: str
    base_currency: str
    amount_precision: int
    rounding_mode: RoundingMode


def amount_string(value: Decimal, places: int) -> str:
    """An exact positive ``DECIMAL(19,4)`` string; ``str`` round-trips through Accounting."""
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValidationFailedError("charge-tax amounts are positive Decimals")
    exact = value.quantize(Decimal(1).scaleb(-places))
    if exact != value or places > 4 or len(exact.as_tuple().digits) > 19:
        raise ValidationFailedError("charge-tax amount is not exact at company precision")
    return str(exact)


def provider_id(values: Mapping[str, Any]) -> uuid.UUID:
    return uuid.uuid5(PROVIDER_NAMESPACE, canonical_json(dict(values)).decode())


def bare_state(value: str) -> str:
    """``MH`` from either ``MH`` or Identity's ``IN-MH``, so both sides compare alike."""
    text = value.strip().upper()
    return text.split("-", 1)[1] if "-" in text else text


def determine(
    request: ChargeTaxInput, company: CompanyFacts, *, utgst_states: frozenset[str]
) -> SupplyDetermination:
    destination = request.place_of_supply_state
    return place_of_supply(
        bare_state(company.state_code),
        None if destination is None else bare_state(destination),
        request.buyer_type,
        utgst_states=frozenset(bare_state(code) for code in utgst_states),
    )


def statement(
    request: ChargeTaxInput,
    company: CompanyFacts,
    determination: SupplyDetermination,
    components: Sequence[TaxComponent],
    registrations: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """The version-two computation for one assessed charge, ready to sign."""
    if request.currency != company.base_currency:
        # Rates in foreign-currency documents are a separate decision; fail closed for now.
        raise ValidationFailedError("charge-tax evidence is computed in the company currency")
    registration = supplier_registration(
        registrations,
        country_code=company.country_code,
        state_code=company.state_code,
        posting_date=request.posting_date,
    )
    rated = any(entry.percentage or entry.amount for entry in components)
    if registration is None and rated:
        # Fail closed: a missing registration context must never silently untax a supply.
        raise ValidationFailedError(
            "no supplier GST registration of the company is valid on the posting date"
        )
    charging = registration is not None and may_charge_tax(TAX_SYSTEM, registration.regime)
    if not charging:
        # A regime that may not charge tax (composition) issues a bill of supply: the rate is
        # not applied at all, rather than computed and refused.
        components = ()
    result = compute(
        TaxRequest(
            lines=(
                TaxLine(
                    key="charge",
                    supply_kind=request.supply_kind,
                    value=request.net_amount,
                    treatment=request.treatment,
                    components=tuple(components),
                    quantity=request.quantity,
                    unit_id=request.unit_id,
                ),
            ),
            determination=determination,
            currency=request.currency,
            amount_precision=company.amount_precision,
            may_charge_tax=charging,
            rounding_mode=company.rounding_mode,
        )
    )
    places = company.amount_precision
    taxed = [entry for entry in result.component_totals if entry.tax_amount > 0]
    if len(taxed) > MAX_COMPONENTS:
        raise ValidationFailedError("charge-tax statement carries too many components")
    net = result.totals.taxable_value
    gross = result.totals.gross
    if net != request.net_amount or gross != net + sum(
        (entry.tax_amount for entry in taxed), Decimal(0)
    ):
        raise ValidationFailedError("charge-tax computation does not balance")
    body: dict[str, Any] = {
        "version": VERSION,
        "tenant_id": str(request.tenant_id),
        "company_id": str(request.company_id),
        "assessment_id": str(request.assessment_id),
        "company_registration_id": None if registration is None else str(registration.id),
        "input_hash": request.input_hash,
        "posting_date": request.posting_date.isoformat(),
        "currency": request.currency,
        "net_amount": amount_string(net, places),
        "gross_amount": amount_string(gross, places),
        "components": [
            {"code": entry.component.value, "amount": amount_string(entry.tax_amount, places)}
            for entry in taxed
        ],
    }
    return {"provider_id": str(provider_id(body)), **body}


def sign(key: ServiceKey, key_id: str, computation: Mapping[str, Any], timestamp: int) -> str:
    return sign_service_body(
        key,
        key_id=key_id,
        operation=OPERATION,
        timestamp=timestamp,
        body=canonical_json(dict(computation)),
    )


__all__ = [
    "OPERATION",
    "PROVIDER_NAMESPACE",
    "VERSION",
    "ChargeTaxInput",
    "CompanyFacts",
    "Registration",
    "amount_string",
    "bare_state",
    "determine",
    "jurisdiction",
    "parse_registration",
    "provider_id",
    "sign",
    "statement",
    "supplier_registration",
]
