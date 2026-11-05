"""Pure scan and generation rules shared by Catalog barcode commands and reads."""

import uuid

import pytest
from billing_platform.errors import ValidationFailedError

from catalog.domain.barcodes import generate_internal_value, gtin_aliases, parse_scan


def test_internal_code_is_stable_printable_and_not_a_gtin() -> None:
    code = generate_internal_value(uuid.UUID("018f02de-6fbb-7e44-a3a3-c6b4fb3d55c5"))
    assert code.startswith("I") and len(code) == 27 and code.isalnum()
    assert code == generate_internal_value(uuid.UUID("018f02de-6fbb-7e44-a3a3-c6b4fb3d55c5"))


def test_gtin_aliases_include_zero_padded_equivalent() -> None:
    aliases = gtin_aliases("036000291452")
    assert "036000291452" in aliases
    assert "0036000291452" in aliases
    assert "00036000291452" in aliases
    with pytest.raises(ValidationFailedError):
        gtin_aliases("036000291453")


def test_gs1_scan_extracts_bounded_hints_and_rejects_ambiguity() -> None:
    parsed = parse_scan("]C101000360002914521725123110LOT7\x1d21SER123")
    assert parsed.code == "00036000291452"
    assert parsed.lot == "LOT7"
    assert parsed.expiry_yymmdd == "251231"
    assert parsed.serial == "SER123"
    assert parsed.gs1
    for value in (
        "]C1010003600029145210A\x1d10B",
        "]C1010003600029145222UNKNOWN",
        "]C1010003600029145210",
        "]C1010003600029145217990231",
        "]C1010003600029145210LOT\x1d",
        "]d20100036000291452",
    ):
        with pytest.raises(ValidationFailedError):
            parse_scan(value)


def test_plain_scan_keeps_code_without_inventing_tracking() -> None:
    parsed = parse_scan("SHELF-001")
    assert (parsed.code, parsed.lot, parsed.expiry_yymmdd, parsed.serial, parsed.gs1) == (
        "SHELF-001",
        None,
        None,
        None,
        False,
    )
    assert parse_scan("]C0SHELF-001").code == "SHELF-001"
