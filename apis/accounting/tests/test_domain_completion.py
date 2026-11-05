"""Classification truth tables and boundary rules stay independent of HTTP and storage."""

from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError

from accounting.domain.master_metadata import (
    group_metadata,
    tally_nature,
    validate_account_metadata,
    validate_duty,
)
from accounting.domain.rules import allowed_head


def test_group_classification_truth_table_and_stock_exception() -> None:
    for nature in ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"):
        result = group_metadata({}, nature, None)
        assert result["is_primary"] is True and result["is_reserved"] is False
        assert result["is_revenue"] is (nature in {"INCOME", "EXPENSE"})
        assert result["is_deemed_positive"] is (nature in {"ASSET", "EXPENSE"})
        assert tally_nature(nature) == ("LIABILITY" if nature == "EQUITY" else nature)
        if nature not in {"INCOME", "EXPENSE"}:
            with pytest.raises(ValidationFailedError):
                group_metadata({"affects_gross_profit": True}, nature, None)
            with pytest.raises(ValidationFailedError):
                group_metadata({"allocation_method": "BY_QTY"}, nature, None)
    stock = group_metadata(
        {"affects_gross_profit": True},
        "ASSET",
        {"affects_gross_profit": False},
        system_key="group.STOCK",
    )
    assert stock["affects_gross_profit"] is True and stock["is_reserved"] is True
    assert group_metadata({}, "ASSET", stock)["affects_gross_profit"] is True
    for inherited in (False, True):
        with pytest.raises(ValidationFailedError):
            group_metadata(
                {"affects_gross_profit": not inherited},
                "EXPENSE",
                {"affects_gross_profit": inherited},
            )
    assert group_metadata({"allocation_method": "BY_VALUE"}, "EXPENSE", None)["is_revenue"]


def test_all_account_kind_head_combinations() -> None:
    natures = {"ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"}
    for kind, role, expected in [
        ("GENERAL", None, natures),
        ("CASH", None, {"ASSET"}),
        ("BANK", None, {"ASSET", "LIABILITY"}),
        ("TAX", None, {"ASSET", "LIABILITY"}),
        ("INVENTORY_CONTROL", None, {"ASSET"}),
        ("ASSET_CONTROL", None, {"ASSET"}),
        ("PARTY", "CUSTOMER", {"ASSET"}),
        ("PARTY", "SUPPLIER", {"LIABILITY"}),
        ("PARTY", "OTHER", natures),
    ]:
        for nature in natures:
            assert allowed_head(kind, role, nature) is (nature in expected), (kind, role, nature)


def test_rounding_and_duty_domain_boundaries() -> None:
    for method in ("NORMAL", "UP", "DOWN"):
        for mode in ("BASE", "FIXED"):
            validate_account_metadata(
                {
                    "rounding_method": method,
                    "rounding_limit": Decimal("0.0001"),
                    "currency_mode": mode,
                }
            )
    for limit in (None, Decimal("NaN"), Decimal("0"), Decimal("-1"), "1", 1.0):
        with pytest.raises(ValidationFailedError):
            validate_account_metadata(
                {"rounding_method": "NORMAL", "rounding_limit": limit, "currency_mode": "BASE"}
            )
    with pytest.raises(ValidationFailedError):
        validate_account_metadata(
            {"rounding_method": "UNKNOWN", "rounding_limit": Decimal(1), "currency_mode": "BASE"}
        )
    for duty in ("TDS", "TCS", "EXCISE", "CESS", "OTHER"):
        validate_duty({"duty_type": duty, "scheme": "OTHER", "component": "OTHER"})
    for duty in ("GST", "OTHER"):
        for component in ("CGST", "SGST", "UTGST", "IGST", "CESS"):
            validate_duty(
                {
                    "duty_type": duty,
                    "scheme": "GST_IN",
                    "component": component,
                    "company_registration_id": "registration",
                }
            )
    with pytest.raises(ValidationFailedError):
        validate_duty({"duty_type": "INVALID", "scheme": "OTHER", "component": "OTHER"})
