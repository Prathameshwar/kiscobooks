"""Accounting invariants over values; no HTTP or database dependency."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.jurisdiction import validate_gstin
from billing_platform.tax import may_charge_tax

from accounting.domain.master_metadata import validate_account_metadata, validate_duty
from accounting.domain.reference import tax_jurisdictions
from accounting.domain.withholding import (
    validate_certificate_terms,
    validate_profile_terms,
    validate_rate_terms,
)


@dataclass(frozen=True)
class GroupNode:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    head_id: uuid.UUID


def hierarchy(nodes: list[GroupNode]) -> list[tuple[uuid.UUID, uuid.UUID, int]]:
    by_id = {node.id: node for node in nodes}
    result = []
    for node in nodes:
        current = node
        seen: set[uuid.UUID] = set()
        while True:
            if current.id in seen or len(seen) >= 10:
                raise ConflictError("group hierarchy has a cycle or exceeds ten levels")
            if current.head_id != node.head_id:
                raise ConflictError("parent and child groups must have the same head")
            result.append((current.id, node.id, len(seen)))
            seen.add(current.id)
            if current.parent_id is None:
                break
            if current.parent_id not in by_id:
                raise ConflictError("parent group is unavailable")
            current = by_id[current.parent_id]
    return result


def overlapping(
    start: dt.date | None,
    end: dt.date | None,
    other_start: dt.date | None,
    other_end: dt.date | None,
) -> bool:
    return (start or dt.date.min) <= (other_end or dt.date.max) and (
        other_start or dt.date.min
    ) <= (end or dt.date.max)


def require_contained_interval(
    start: dt.date | None,
    end: dt.date | None,
    parent_start: dt.date | None,
    parent_end: dt.date | None,
) -> None:
    if (start or dt.date.min) < (parent_start or dt.date.min) or (
        end or dt.date.max
    ) > (parent_end or dt.date.max):
        raise ConflictError("dependent effective interval must fit its registration")


def guard_effective_edit(
    start: dt.date | None,
    end: dt.date | None,
    changed: set[str],
    new_end: dt.date | None,
    *,
    today: dt.date,
) -> None:
    if (start is None or start <= today) and changed:
        if (
            (end is not None and end < today)
            or changed - {"valid_to"}
            or (new_end is not None and new_end < today)
        ):
            raise ConflictError("effective history is immutable; create a new interval")


def validate_values(name: str, values: dict[str, Any]) -> None:
    if "valid_from" in values:
        start, end = values["valid_from"], values.get("valid_to")
        if (
            (start is None and name != "party_tax_registration")
            or (start is not None and start < dt.date(1000, 1, 1))
            or (end is not None and end < (start or dt.date(1000, 1, 1)))
        ):
            raise ValidationFailedError("effective dates are invalid")
    if name == "account":
        validate_account_metadata(values)
        party = values["kind"] == "PARTY"
        if party != (values.get("party_id") is not None and values.get("party_role") is not None):
            raise ValidationFailedError("party accounts require a party and role")
        if not party and (
            values.get("party_id") is not None or values.get("party_role") is not None
        ):
            raise ValidationFailedError("only party accounts may identify a party")
        if (values["currency_mode"] == "FIXED") != (values.get("currency") is not None):
            raise ValidationFailedError("only fixed-currency accounts require a currency")
        if values["kind"] in {"BANK", "CASH", "TAX"} and values["currency_mode"] == "MULTI":
            raise ValidationFailedError("cash, bank and tax accounts have a single currency")
    if name == "account_tax_profile":
        validate_duty(values)
    if name == "party_credit_policy":
        limited = values["limit_mode"] == "LIMITED"
        if limited != (values.get("limit_amount") is not None):
            raise ValidationFailedError("only a limited policy requires a credit limit amount")
    if name == "party_contact":
        if not any(values.get(key) for key in ("email", "phone", "mobile")):
            raise ValidationFailedError("provide an email address or telephone number")
        email = values.get("email")
        if email is not None and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValidationFailedError("invalid contact email")
    if name == "party_tax_registration":
        validate_party_registration(values)
    if (
        name == "party_identifier"
        and values["scheme"] == "PAN"
        and not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", values["value"])
    ):
        raise ValidationFailedError("invalid PAN format")
    if name == "withholding_rate":
        validate_rate_terms(values)
    if name == "party_withholding_profile":
        validate_profile_terms(values)
    if name == "withholding_certificate":
        validate_certificate_terms(values)
    if name == "party_bank_account":
        number = values["account_number"]
        if not re.fullmatch(r"[A-Za-z0-9 -]{4,64}", number):
            raise ValidationFailedError("invalid beneficiary account number")
    if name == "account_tax_default":
        validate_account_tax_default(values)


#: GST classification code shapes, as Catalog validates them: SAC is a six-digit 99 chapter,
#: HSN a four, six or eight digit code outside chapter 99.
TAX_CODE_PATTERNS = {
    "SAC": re.compile(r"99[0-9]{4}"),
    "HSN": re.compile(r"(?!99)[0-9]{4}(?:[0-9]{2}){0,2}"),
}
#: The supply kind each code system classifies.
CODE_SYSTEM_KINDS = {"HSN": "GOODS", "SAC": "SERVICE"}
#: Treatments that resolve a rate and so must name a Catalog rule; exempt and non-GST
#: defaults may name one for reporting.
RATED_TREATMENTS = frozenset({"TAXABLE", "NIL_RATED"})
#: Account head natures whose GENERAL accounts may carry a tax default.
TAX_DEFAULT_HEADS = frozenset({"INCOME", "EXPENSE", "ASSET"})


def validate_account_tax_default(values: dict[str, Any]) -> None:
    """Pure shape rules for an account's GST default (tax-accounting plan Phase 6)."""
    system, code = values.get("code_system"), values.get("code")
    pattern = TAX_CODE_PATTERNS.get(system or "")
    if pattern is None or code is None or not pattern.fullmatch(code):
        raise ValidationFailedError("classification code does not match its code system")
    if CODE_SYSTEM_KINDS[system or ""] != values.get("supply_kind"):
        raise ValidationFailedError("code system and supply kind are incompatible")
    if values.get("treatment") in RATED_TREATMENTS and values.get("rule_id") is None:
        raise ValidationFailedError("taxable and nil-rated defaults name a tax rule")
    purchase = values.get("direction") == "PURCHASE"
    if purchase != (values.get("itc_eligibility") is not None):
        raise ValidationFailedError("input tax credit eligibility applies to purchases only")
    if not purchase and values.get("rcm_applicable"):
        raise ValidationFailedError("reverse charge applies to purchases only")
    if (values.get("assessable_inclusion", "NONE") == "NONE") != (
        values.get("apportion_by") is None
    ):
        raise ValidationFailedError("only an assessable inclusion is apportioned")


#: Party GST registration types whose number is a PAN-based GSTIN.
GSTIN_TYPES = frozenset({"REGULAR", "COMPOSITION", "SEZ_UNIT", "SEZ_DEVELOPER", "CASUAL", "OTHER"})
#: GST-only party types: they describe an Indian GST status, not a foreign one.
GST_ONLY_TYPES = frozenset({"SEZ_UNIT", "SEZ_DEVELOPER", "UIN", "CASUAL", "NRTP"})


def validate_party_registration(values: dict[str, Any]) -> None:
    kind, scheme = values.get("registration_type"), values.get("scheme")
    number: str | None = values.get("registration_number")
    if kind == "UNREGISTERED" and number is not None:
        raise ValidationFailedError("an unregistered party has no registration number")
    if kind not in {"UNREGISTERED", "OVERSEAS"} and number is None:
        raise ValidationFailedError("this registration type requires a registration number")
    if kind == "OVERSEAS" and values.get("country_code") == "IN":
        raise ValidationFailedError("an overseas party registration is outside India")
    if kind in GST_ONLY_TYPES and scheme != "GST_IN":
        raise ValidationFailedError("this registration type exists only under GST")
    if scheme != "GST_IN":
        return
    if kind == "OVERSEAS":
        # An overseas party holds no GSTIN and no Indian state; the row records only that
        # supplies to it are exports.
        if number is not None or values.get("state_code") is not None:
            raise ValidationFailedError("an overseas GST party has no GSTIN or Indian state")
        return
    if values.get("country_code") != "IN":
        raise ValidationFailedError("invalid GST registration format")
    state = values.get("state_code")
    code = tax_jurisdictions().get(state) if state else None
    if code is None:
        # Place of supply is a state; an unregistered buyer's row exists to record it.
        raise ValidationFailedError("GST party registrations require an Indian state")
    if number is None:
        return
    if kind in GSTIN_TYPES:
        try:
            normalized = validate_gstin(number, state_tax_code=code)
        except ValidationFailedError:
            raise ValidationFailedError("invalid GST registration number") from None
        if normalized != number:
            raise ValidationFailedError("GST registration numbers are stored without separators")
    elif not re.fullmatch(r"[0-9]{2}[0-9A-Z]{13}", number) or number[:2] != code:
        # UIN and NRTP identifiers are not PAN-based; the shared helper documents no pattern
        # for them yet, so only the fifteen-character state-prefixed shape is checked.
        raise ValidationFailedError("invalid GST registration number")


def validate_schedule(lines: list[tuple[int, Decimal]]) -> None:
    if not lines or len(lines) > 24:
        raise ConflictError("payment terms require one to twenty-four instalments")
    if len({sequence for sequence, _ in lines}) != len(lines) or any(
        sequence < 1 for sequence, _ in lines
    ):
        raise ConflictError("instalment sequences must be unique positive numbers")
    if sum((amount for _, amount in lines), Decimal(0)) != Decimal(100):
        raise ConflictError("instalment percentages must total 100")


def allowed_head(kind: str, role: str | None, nature: str) -> bool:
    if kind == "CASH":
        return nature == "ASSET"
    if kind == "BANK":
        return nature in {"ASSET", "LIABILITY"}
    if kind == "PARTY" and role == "CUSTOMER":
        return nature == "ASSET"
    if kind == "PARTY" and role == "SUPPLIER":
        return nature == "LIABILITY"
    if kind in {"INVENTORY_CONTROL", "ASSET_CONTROL"}:
        return nature == "ASSET"
    if kind == "TAX":
        return nature in {"ASSET", "LIABILITY"}
    return True


def validate_tax_head(purpose: str, nature: str) -> None:
    expected = (
        "ASSET" if purpose in {"INPUT_RECOVERABLE", "INPUT_PENDING", "DEPOSIT"} else "LIABILITY"
    )
    if purpose != "ADJUSTMENT" and nature != expected:
        raise ValidationFailedError("tax purpose and account head are incompatible")


@dataclass(frozen=True)
class TaxMapping:
    """What a tax posting purpose requires of its account's tax profile."""

    nature: str
    scheme: str
    component: str
    profile_purpose: str
    duty_types: frozenset[str]
    #: The registration regime test the mapping's whole window must satisfy, if any.
    regime: str | None


def _gst(direction: str, component: str) -> TaxMapping:
    duty = frozenset({"GST", "CESS", "OTHER"} if component == "CESS" else {"GST", "OTHER"})
    nature, purpose, regime = {
        "OUTPUT": ("LIABILITY", "OUTPUT_PAYABLE", "CHARGE"),
        "INPUT": ("ASSET", "INPUT_RECOVERABLE", "RECOVER"),
        "PENDING": ("ASSET", "INPUT_PENDING", "RECOVER"),
        # Reverse-charge liability is owed whatever the recipient's regime.
        "RCM": ("LIABILITY", "RCM_PAYABLE", None),
    }[direction]
    return TaxMapping(nature, "GST_IN", component, purpose, duty, regime)


def _withheld(duty: str, purpose: str) -> TaxMapping:
    nature = "LIABILITY" if purpose == "OUTPUT_PAYABLE" else "ASSET"
    return TaxMapping(nature, "OTHER", "OTHER", purpose, frozenset({duty}), None)


#: Posting purpose -> required tax profile. Explicit, so CESS, reverse-charge and
#: withholding purposes are mappable without inferring meaning from a name suffix.
TAX_MAPPINGS: dict[str, TaxMapping] = {
    f"{direction}_{component}": _gst(direction, component)
    for direction in ("OUTPUT", "INPUT", "PENDING", "RCM")
    for component in ("CGST", "SGST", "UTGST", "IGST", "CESS")
} | {
    "TDS_PAYABLE": _withheld("TDS", "OUTPUT_PAYABLE"),
    "TCS_PAYABLE": _withheld("TCS", "OUTPUT_PAYABLE"),
    "TDS_RECEIVABLE": _withheld("TDS", "INPUT_RECOVERABLE"),
    "TCS_RECEIVABLE": _withheld("TCS", "INPUT_RECOVERABLE"),
}

#: Account head natures for the non-tax posting purposes. A bank receipt may land in an
#: overdraft account, which sits under LIABILITY exactly as `allowed_head` permits.
PURPOSE_HEADS: dict[str, frozenset[str]] = {
    **{
        purpose: frozenset({"INCOME"})
        for purpose in ("SALES_REVENUE", "SERVICE_REVENUE", "SALES_RETURN", "ROUNDING_GAIN")
    },
    **{
        purpose: frozenset({"EXPENSE"})
        for purpose in ("PURCHASE_EXPENSE", "COST_OF_GOODS", "ROUNDING_LOSS")
    },
    "CASH_RECEIPT": frozenset({"ASSET"}),
    "BANK_RECEIPT": frozenset({"ASSET", "LIABILITY"}),
    "INVENTORY_VALUE": frozenset({"ASSET"}),
} | {purpose: frozenset({rule.nature}) for purpose, rule in TAX_MAPPINGS.items()}

PURPOSE_KINDS: dict[str, str] = {
    "CASH_RECEIPT": "CASH",
    "BANK_RECEIPT": "BANK",
} | dict.fromkeys(TAX_MAPPINGS, "TAX")

#: GST regimes under which the company itself recovers input tax. Deliberately narrow:
#: composition and unregistered regimes may not, and the others are unsupported here.
INPUT_RECOVERING_REGIMES = frozenset({"regular"})


def regime_permits(requirement: str | None, tax_system: str, regime: str) -> bool:
    """Whether one registration row's regime satisfies a profile/mapping requirement."""
    if requirement == "RECOVER":
        return tax_system == "gst_in" and regime in INPUT_RECOVERING_REGIMES
    if requirement == "CHARGE":
        return may_charge_tax(tax_system, regime)
    return True
