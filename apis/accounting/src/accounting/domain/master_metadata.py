"""Native master classifications and defaults, independent of persistence."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from billing_platform.errors import ValidationFailedError

METADATA_VERSION = 1
GROUP_DERIVED = frozenset({"is_primary", "is_reserved", "is_revenue", "is_deemed_positive"})
GROUP_CLASSIFICATION = GROUP_DERIVED | {
    "head_id",
    "parent_id",
    "affects_gross_profit",
    "sub_ledger_behaviour",
    "nett_balances",
    "used_for_calculation",
    "allocation_method",
}
PRESENTATION = frozenset({"name", "description", "sort_order"})


def tally_nature(nature: str) -> str:
    return "LIABILITY" if nature == "EQUITY" else nature


def group_metadata(
    values: Mapping[str, Any],
    nature: str,
    parent: Mapping[str, Any] | None,
    *,
    system_key: str | None = None,
) -> dict[str, Any]:
    supplied = values.get("affects_gross_profit")
    inherited = (
        parent["affects_gross_profit"]
        if parent is not None and system_key != "group.STOCK"
        else None
    )
    if inherited is not None and supplied is not None and supplied != inherited:
        raise ValidationFailedError("gross-profit classification must match the parent group")
    gross = inherited if inherited is not None else bool(supplied)
    stock = system_key == "group.STOCK" or (
        parent is not None and nature == "ASSET" and parent["affects_gross_profit"]
    )
    if gross and nature not in {"INCOME", "EXPENSE"} and not stock:
        raise ValidationFailedError("gross-profit classification is not applicable to this group")
    if values.get("allocation_method", "NOT_APPLICABLE") != "NOT_APPLICABLE" and nature not in {
        "INCOME",
        "EXPENSE",
    }:
        raise ValidationFailedError("allocation requires an income or expense group")
    return {
        "is_primary": parent is None,
        "is_reserved": system_key is not None,
        "is_revenue": nature in {"INCOME", "EXPENSE"},
        "is_deemed_positive": nature in {"ASSET", "EXPENSE"},
        "affects_gross_profit": gross,
    }


def template_group_defaults(code: str, order: int) -> dict[str, Any]:
    return {
        "affects_gross_profit": code
        in {"DIRECT_INCOME", "DIRECT_EXPENSES", "PURCHASES", "SALES", "STOCK"},
        "sub_ledger_behaviour": code in {"DEBTORS", "CREDITORS"},
        "nett_balances": False,
        "used_for_calculation": code in {"TAX_PAYABLE", "TAX_RECOVERABLE"},
        "allocation_method": "NOT_APPLICABLE",
        "sort_order": order * 10,
    }


def validate_account_metadata(values: Mapping[str, Any]) -> None:
    method = values.get("rounding_method", "NONE")
    limit = values.get("rounding_limit")
    if method == "NONE":
        if limit is not None:
            raise ValidationFailedError("disabled rounding cannot carry a limit")
    elif (
        method not in {"NORMAL", "UP", "DOWN"}
        or not isinstance(limit, Decimal)
        or not limit.is_finite()
        or limit <= 0
        or values["currency_mode"] == "MULTI"
    ):
        raise ValidationFailedError("rounding requires a positive limit and a single currency")


def validate_duty(values: Mapping[str, Any]) -> None:
    duty, scheme, component = (
        values.get("duty_type", "OTHER"),
        values["scheme"],
        values["component"],
    )
    components = {
        "GST_IN": {"CGST", "SGST", "UTGST", "IGST", "CESS"},
        "VAT": {"VAT"},
        "OTHER": {"OTHER"},
    }
    if component not in components.get(scheme, set()):
        raise ValidationFailedError("tax component differs from its scheme")
    compatible = (
        duty == "OTHER"
        or (duty == "GST" and scheme == "GST_IN")
        or (duty == "VAT" and scheme == "VAT")
        or (duty == "CESS" and (scheme, component) in {("GST_IN", "CESS"), ("OTHER", "OTHER")})
        or (duty in {"TDS", "TCS", "EXCISE"} and scheme == "OTHER")
    )
    if not compatible:
        raise ValidationFailedError("duty classification differs from its tax scheme")
    if scheme in {"GST_IN", "VAT"} and values.get("company_registration_id") is None:
        raise ValidationFailedError("GST and VAT profiles require a company registration")
