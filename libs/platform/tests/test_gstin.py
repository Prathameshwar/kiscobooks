"""GSTIN validation — shape, mod-36 check character, and state prefix.

The check character is computed here by an **independent reference implementation**
(``_reference_check``) rather than trusted from memorised examples: a test that
only replays numbers copied from somewhere proves the module agrees with the copy,
not with the algorithm. The two implementations are written differently on purpose
(``int(c, 36)`` and ``divmod`` here, a lookup string in the module) so a shared bug
is unlikely.

One published GSTIN is used as a cross-check of the reference implementation itself.
"""

from __future__ import annotations

import pytest

from billing_platform.errors import ValidationFailedError
from billing_platform.jurisdiction import (
    assert_tax_registration_number,
    gstin_check_character,
    validate_gstin,
)


def _reference_check(first14: str) -> str:
    total = 0
    for index, char in enumerate(first14):
        quotient, remainder = divmod(int(char, 36) * (2 if index % 2 else 1), 36)
        total += quotient + remainder
    check = (36 - total % 36) % 36
    return "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[check]


def _gstin(first14: str) -> str:
    return first14 + _reference_check(first14)


#: Maharashtra (27), PAN AAAPA1234A, entity 1, literal Z.
MH = _gstin("27AAAPA1234A1Z")
#: A TDS-deductor GSTIN: Delhi (07), TAN DELA12345B, entity 1, literal D.
TDS_DL = _gstin("07DELA12345B1D")
#: An e-commerce operator's TCS GSTIN: Karnataka (29), PAN AAACF1234K, entity 1, literal C.
TCS_KA = _gstin("29AAACF1234K1C")


def test_the_reference_implementation_agrees_with_a_published_gstin() -> None:
    """Guards the guard: if the reference were wrong, every test below would be too."""
    assert _reference_check("27AAPFU0939F1Z") == "V"


def test_the_module_check_character_matches_the_reference() -> None:
    for first14 in (
        "27AAAPA1234A1Z",
        "29BBBPB5678B1Z",
        "07DELA12345B1D",
        "29AAACF1234K1C",
        "33ZZZZZ9999Z9Z",
    ):
        assert gstin_check_character(first14) == _reference_check(first14)


def test_a_valid_gstin_is_accepted_normalized() -> None:
    assert validate_gstin(MH.lower(), state_tax_code="27") == MH
    assert validate_gstin(f" {MH[:5]}-{MH[5:]} ", state_tax_code="27") == MH


def test_every_one_of_the_first_fourteen_characters_is_checked() -> None:
    """Mutate each position to another valid character: the check must catch it."""
    for position in range(14):
        original = MH[position]
        replacement = "8" if original.isdigit() and original != "8" else "9"
        if original.isalpha():
            replacement = "B" if original != "B" else "C"
        mutated = MH[:position] + replacement + MH[position + 1 :]
        if position < 2:
            # A different state prefix would be caught by the prefix rule; isolate the
            # checksum by not asking for one.
            state = None
        else:
            state = "27"
        with pytest.raises(ValidationFailedError):
            validate_gstin(mutated, state_tax_code=state)


def test_a_wrong_check_character_is_rejected() -> None:
    wrong = MH[:14] + ("0" if MH[14] != "0" else "1")

    with pytest.raises(ValidationFailedError) as raised:
        validate_gstin(wrong, state_tax_code="27")

    assert raised.value.extra["fields"] == {"number": "check character does not match"}


def test_a_state_prefix_that_differs_from_the_jurisdiction_is_rejected() -> None:
    """A Karnataka GSTIN on a Maharashtra registration decides intra- versus
    inter-state on every invoice wrongly."""
    karnataka = _gstin("29AAAPA1234A1Z")

    with pytest.raises(ValidationFailedError) as raised:
        validate_gstin(karnataka, state_tax_code="27")

    assert raised.value.extra["fields"] == {
        "number": "state prefix 29 does not match the jurisdiction's GST state code 27"
    }


def test_no_state_code_skips_only_the_prefix_rule() -> None:
    karnataka = _gstin("29AAAPA1234A1Z")
    assert validate_gstin(karnataka, state_tax_code=None) == karnataka

    with pytest.raises(ValidationFailedError):
        validate_gstin(karnataka[:14] + ("0" if karnataka[14] != "0" else "1"), state_tax_code=None)


def test_entity_code_zero_is_rejected() -> None:
    """The 13th character counts registrations under one PAN from 1; ``0`` is never
    issued, even when the check character is right for it."""
    with pytest.raises(ValidationFailedError) as raised:
        validate_gstin(_gstin("27AAAPA1234A0Z"), state_tax_code="27")

    assert raised.value.extra["fields"] == {"number": "does not match the gst_in format"}


def test_a_gstin_without_the_literal_z_is_rejected_for_a_supplier() -> None:
    with pytest.raises(ValidationFailedError):
        validate_gstin(_gstin("27AAAPA1234A1X"), state_tax_code="27")


def test_a_tan_based_gstin_is_accepted_for_a_tds_deductor() -> None:
    assert validate_gstin(TDS_DL, state_tax_code="07", registration_class="tds_deductor") == (
        TDS_DL
    )


def test_a_tan_based_gstin_is_refused_for_any_other_class() -> None:
    """Only a TDS deductor is registered against a TAN."""
    for registration_class in ("supplier", "isd"):
        with pytest.raises(ValidationFailedError) as raised:
            validate_gstin(TDS_DL, state_tax_code="07", registration_class=registration_class)

        assert raised.value.extra["fields"] == {"number": "does not match the gst_in format"}


def test_a_tds_deductor_may_still_hold_a_pan_based_gstin() -> None:
    """Accepting the TAN shape widens the deductor's options; it does not narrow them."""
    assert validate_gstin(MH, state_tax_code="27", registration_class="tds_deductor") == MH


def test_a_tcs_gstin_is_accepted_for_a_tcs_collector() -> None:
    assert validate_gstin(TCS_KA, state_tax_code="29", registration_class="tcs_collector") == (
        TCS_KA
    )


def test_a_tcs_gstin_is_refused_for_any_other_class() -> None:
    """The literal ``C`` marks a TCS registration; no other class is issued one."""
    for registration_class in ("supplier", "isd", "tds_deductor"):
        with pytest.raises(ValidationFailedError) as raised:
            validate_gstin(TCS_KA, state_tax_code="29", registration_class=registration_class)

        assert raised.value.extra["fields"] == {"number": "does not match the gst_in format"}


def test_a_tan_based_gstin_is_refused_for_a_tcs_collector() -> None:
    with pytest.raises(ValidationFailedError):
        validate_gstin(TDS_DL, state_tax_code="07", registration_class="tcs_collector")


def test_a_tcs_gstin_is_checksummed_and_state_prefixed() -> None:
    wrong = TCS_KA[:14] + ("0" if TCS_KA[14] != "0" else "1")
    with pytest.raises(ValidationFailedError) as raised:
        validate_gstin(wrong, state_tax_code="29", registration_class="tcs_collector")
    assert raised.value.extra["fields"] == {"number": "check character does not match"}

    with pytest.raises(ValidationFailedError) as raised:
        validate_gstin(TCS_KA, state_tax_code="27", registration_class="tcs_collector")
    assert "state prefix 29" in raised.value.extra["fields"]["number"]


def test_a_tcs_gstin_with_entity_code_zero_is_refused() -> None:
    with pytest.raises(ValidationFailedError):
        validate_gstin(
            _gstin("29AAACF1234K0C"), state_tax_code="29", registration_class="tcs_collector"
        )


def test_a_tan_based_gstin_is_checksummed_too() -> None:
    wrong = TDS_DL[:14] + ("0" if TDS_DL[14] != "0" else "1")

    with pytest.raises(ValidationFailedError) as raised:
        validate_gstin(wrong, state_tax_code="07", registration_class="tds_deductor")

    assert raised.value.extra["fields"] == {"number": "check character does not match"}


def test_an_unknown_registration_class_is_rejected() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        validate_gstin(MH, state_tax_code="27", registration_class="wholesaler")

    assert raised.value.extra["fields"] == {"registration_class": "not a known registration class"}


def test_the_profile_path_applies_the_checksum() -> None:
    """Regression: the profile pattern alone accepted any final character, so
    ``27AAAPA1234A1Z5`` — whose check character is ``T`` — was stored."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_tax_registration_number("IN", "gst_in", "27AAAPA1234A1Z5")

    assert raised.value.extra["fields"] == {"number": "check character does not match"}


def test_the_profile_path_applies_the_state_prefix() -> None:
    with pytest.raises(ValidationFailedError):
        assert_tax_registration_number("IN", "gst_in", MH, state_tax_code="29")


def test_the_check_character_helper_refuses_a_wrong_length() -> None:
    with pytest.raises(ValueError):
        gstin_check_character("27AAAPA1234A1")
    with pytest.raises(ValueError):
        gstin_check_character("27AAAPA1234A1z")
