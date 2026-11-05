import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError

from accounting.domain.reference import validate_reference
from accounting.domain.rules import (
    PURPOSE_HEADS,
    TAX_MAPPINGS,
    GroupNode,
    allowed_head,
    hierarchy,
    overlapping,
    regime_permits,
    validate_schedule,
    validate_values,
)


def test_hierarchy_and_boundaries() -> None:
    head, root, child = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert hierarchy([GroupNode(root, None, head), GroupNode(child, root, head)]) == [
        (root, root, 0),
        (child, child, 0),
        (root, child, 1),
    ]
    for nodes in (
        [GroupNode(root, root, head)],
        [GroupNode(root, child, head)],
        [GroupNode(root, None, head), GroupNode(child, root, uuid.uuid4())],
    ):
        with pytest.raises(ConflictError):
            hierarchy(nodes)
    ids = [uuid.uuid4() for _ in range(11)]
    with pytest.raises(ConflictError):
        hierarchy(
            [GroupNode(value, ids[i - 1] if i else None, head) for i, value in enumerate(ids)]
        )


def test_schedule_and_intervals() -> None:
    validate_schedule([(1, Decimal("30")), (2, Decimal("70"))])
    for lines in (
        [],
        [(1, Decimal(99))],
        [(0, Decimal(100))],
        [(1, Decimal(50)), (1, Decimal(50))],
        [(i, Decimal(4)) for i in range(25)],
    ):
        with pytest.raises(ConflictError):
            validate_schedule(lines)
    d = dt.date(2026, 1, 1)
    assert overlapping(d, None, d, None)
    assert not overlapping(d, d, dt.date(2026, 1, 2), None)


@pytest.mark.parametrize(
    "name,values",
    [
        ("party_credit_policy", {"limit_mode": "LIMITED", "limit_amount": None}),
        ("party_credit_policy", {"limit_mode": "UNLIMITED", "limit_amount": Decimal(1)}),
        ("party_contact", {}),
        ("party_contact", {"email": "bad"}),
        (
            "party_tax_registration",
            {"registration_type": "UNREGISTERED", "registration_number": "27ABCDE1234F1Z0"},
        ),
        (
            "party_tax_registration",
            {
                "registration_type": "REGULAR",
                "scheme": "GST_IN",
                "country_code": "US",
                "registration_number": "bad",
            },
        ),
        ("party_identifier", {"scheme": "PAN", "value": "bad"}),
        ("party_bank_account", {"account_number": "bad!"}),
        ("any", {"valid_from": dt.date(999, 1, 1)}),
        ("any", {"valid_from": dt.date(2026, 1, 2), "valid_to": dt.date(2026, 1, 1)}),
    ],
)
def test_invalid_values(name: str, values: dict[str, Any]) -> None:
    with pytest.raises(ValidationFailedError):
        validate_values(name, values)


def test_account_rules() -> None:
    base = {"kind": "GENERAL", "currency_mode": "BASE"}
    validate_values("account", base)
    for extra in (
        {"kind": "PARTY"},
        {"party_id": uuid.uuid4()},
        {"currency_mode": "FIXED"},
        {"kind": "BANK", "currency_mode": "MULTI"},
    ):
        with pytest.raises(ValidationFailedError):
            validate_values("account", base | extra)
    validate_values("party_contact", {"email": "a@example.test"})
    validate_values("party_identifier", {"scheme": "PAN", "value": "ABCDE1234F"})
    validate_values("party_bank_account", {"account_number": "123456789"})
    validate_values(
        "party_tax_registration",
        {
            "registration_type": "REGULAR",
            "scheme": "GST_IN",
            "country_code": "IN",
            "registration_number": "27ABCDE1234F1Z0",
            "state_code": "IN-MH",
        },
    )
    for kind, role, nature, expected in [
        ("CASH", None, "ASSET", True),
        ("CASH", None, "EXPENSE", False),
        ("BANK", None, "LIABILITY", True),
        ("PARTY", "CUSTOMER", "ASSET", True),
        ("PARTY", "SUPPLIER", "ASSET", False),
        ("INVENTORY_CONTROL", None, "ASSET", True),
        ("ASSET_CONTROL", None, "INCOME", False),
        ("TAX", None, "LIABILITY", True),
        ("GENERAL", None, "EXPENSE", True),
    ]:
        assert allowed_head(kind, role, nature) is expected


def test_reference_validation_rejects_unknown_and_mismatched_codes() -> None:
    validate_reference("IN", "IN-MH", ["INR", None])
    validate_reference(None, None, [None])
    with pytest.raises(ValidationFailedError):
        validate_reference("ZZ", None, [None])
    with pytest.raises(ValidationFailedError):
        validate_reference("IN", "ZZ-ZZ", [None])
    # A real state that belongs to another country must not pass under IN.
    with pytest.raises(ValidationFailedError):
        validate_reference("IN", "US-CA", [None])
    # A state without a country has nothing to check against.
    with pytest.raises(ValidationFailedError):
        validate_reference(None, "IN-MH", [None])
    with pytest.raises(ValidationFailedError):
        validate_reference("IN", "IN-MH", ["ZZZ"])
    with pytest.raises(ValidationFailedError):
        validate_reference("IN", "IN-MH", ["INR", "ZZZ"])


GST_PARTY = {"scheme": "GST_IN", "country_code": "IN", "state_code": "IN-MH"}


@pytest.mark.parametrize(
    "values",
    [
        GST_PARTY | {"registration_type": "REGULAR", "registration_number": "27ABCDE1234F1Z0"},
        GST_PARTY | {"registration_type": "SEZ_UNIT", "registration_number": "27ABCDE1234F1Z0"},
        GST_PARTY | {"registration_type": "CASUAL", "registration_number": "27ABCDE1234F1Z0"},
        GST_PARTY | {"registration_type": "UNREGISTERED", "registration_number": None},
        GST_PARTY | {"registration_type": "UIN", "registration_number": "2712345678901UN"},
        {
            "scheme": "GST_IN",
            "country_code": "US",
            "state_code": None,
            "registration_type": "OVERSEAS",
            "registration_number": None,
        },
        {
            "scheme": "VAT",
            "country_code": "GB",
            "registration_type": "OVERSEAS",
            "registration_number": "GB123",
        },
    ],
)
def test_party_registration_types(values: dict[str, Any]) -> None:
    validate_values("party_tax_registration", values)


@pytest.mark.parametrize(
    "values,message",
    [
        # Wrong mod-36 check character.
        (
            GST_PARTY | {"registration_type": "REGULAR", "registration_number": "27ABCDE1234F1Z5"},
            "invalid GST registration number",
        ),
        # Entity code 0 is never issued.
        (
            GST_PARTY | {"registration_type": "REGULAR", "registration_number": "27ABCDE1234F0Z1"},
            "invalid GST registration number",
        ),
        # The state prefix must match the state.
        (
            GST_PARTY
            | {
                "registration_type": "REGULAR",
                "registration_number": "29ABCDE1234F1ZW",
            },
            "invalid GST registration number",
        ),
        (
            GST_PARTY
            | {"registration_type": "REGULAR", "registration_number": "27ABCDE1234F1Z0"}
            | {"state_code": None},
            "require an Indian state",
        ),
        (
            GST_PARTY | {"registration_type": "UNREGISTERED", "state_code": None},
            "require an Indian state",
        ),
        (GST_PARTY | {"registration_type": "REGULAR"}, "requires a registration number"),
        (
            GST_PARTY | {"registration_type": "UNREGISTERED", "registration_number": "X"},
            "has no registration number",
        ),
        (
            GST_PARTY | {"registration_type": "OVERSEAS", "country_code": "IN"},
            "outside India",
        ),
        (
            {"scheme": "VAT", "country_code": "GB", "registration_type": "UIN"}
            | {"registration_number": "X"},
            "only under GST",
        ),
        (
            {"scheme": "GST_IN", "country_code": "US", "registration_type": "OVERSEAS"}
            | {"state_code": "IN-MH"},
            "no GSTIN or Indian state",
        ),
        (
            GST_PARTY | {"registration_type": "UIN", "registration_number": "2912345678901UN"},
            "invalid GST registration number",
        ),
        (
            GST_PARTY | {"registration_type": "REGULAR", "registration_number": "27abcde1234f1z0"},
            "without separators",
        ),
    ],
)
def test_party_registration_rejections(values: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationFailedError, match=message):
        validate_values("party_tax_registration", values)


def test_purpose_table_is_explicit() -> None:
    assert TAX_MAPPINGS["OUTPUT_CESS"].component == "CESS"
    assert TAX_MAPPINGS["OUTPUT_CESS"].profile_purpose == "OUTPUT_PAYABLE"
    assert TAX_MAPPINGS["INPUT_CESS"].nature == "ASSET"
    assert TAX_MAPPINGS["RCM_IGST"].profile_purpose == "RCM_PAYABLE"
    assert TAX_MAPPINGS["RCM_IGST"].regime is None
    assert TAX_MAPPINGS["TDS_PAYABLE"].duty_types == frozenset({"TDS"})
    assert TAX_MAPPINGS["TCS_RECEIVABLE"].nature == "ASSET"
    assert PURPOSE_HEADS["BANK_RECEIPT"] == frozenset({"ASSET", "LIABILITY"})
    assert regime_permits("CHARGE", "gst_in", "regular")
    assert not regime_permits("CHARGE", "gst_in", "composition")
    assert not regime_permits("RECOVER", "gst_in", "composition")
    assert regime_permits(None, "gst_in", "composition")
