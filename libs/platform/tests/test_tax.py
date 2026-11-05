"""The tax-system and regime catalogues.

Small, and worth its own file: every service stores a ``tax_system`` string on a
replica, so a value one service accepts and another rejects is a document that
cannot be reproduced (docs/company.md §2.1).

The regime catalogue carries exactly two flags, and both change what a posting
*computes* — which is the test for belonging here at all. Anything that only
changes what a return looks like belongs to whichever service files it, so the
tests below check the two flags and deliberately check nothing else.
"""

from __future__ import annotations

import pytest

from billing_platform import tax as module
from billing_platform.errors import ValidationFailedError
from billing_platform.tax import (
    REGIMES,
    TAX_SYSTEMS,
    Regime,
    assert_known_tax_system,
    get_regime,
    may_charge_tax,
    regimes_for,
)


def test_the_documented_systems_are_the_ones_the_code_knows() -> None:
    assert set(TAX_SYSTEMS) == {
        "gst_in",
        "vat_gb",
        "vat_eu",
        "vat_ae",
        "vat_sa",
        "gst_au",
        "gst_ca",
        "sales_tax_us",
        "none",
    }


def test_every_system_has_a_label() -> None:
    """The label is what a client renders. A blank one shows an empty dropdown row."""
    assert all(label.strip() for label in TAX_SYSTEMS.values())


def test_not_registered_is_a_value_not_a_null() -> None:
    """ "No indirect tax registration" is a posture held deliberately. A NULL would
    be indistinguishable from "nobody has filled this in yet"."""
    assert "none" in TAX_SYSTEMS


def test_a_known_system_is_accepted() -> None:
    assert_known_tax_system("gst_in")


def test_an_unknown_system_is_rejected() -> None:
    with pytest.raises(ValidationFailedError):
        assert_known_tax_system("gst_zz")


def test_the_rejection_names_the_field() -> None:
    """422 bodies carry field-level detail so a form can point at the input."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_known_tax_system("")

    assert raised.value.extra["fields"] == {"tax_system": "not in the platform catalogue"}


# --- the regime catalogue -----------------------------------------------------


def test_every_regime_catalogue_belongs_to_a_known_tax_system() -> None:
    assert set(REGIMES) <= set(TAX_SYSTEMS)


def test_the_indian_regimes_are_the_documented_ones() -> None:
    """docs/company.md §2.2. These keys are stored on `company_tax_registration` and
    appear in filed output, so they are immutable once shipped."""
    assert set(regimes_for("gst_in")) == {
        "regular",
        "composition",
        "unregistered",
        "sez_unit",
        "sez_developer",
        "ecommerce_operator",
        "isd",
        "casual_taxable_person",
        "tds_deductor",
    }


def test_a_composition_dealer_may_not_charge_tax() -> None:
    """The rule the whole catalogue exists for: a composition dealer pays a flat rate
    on turnover and must not show GST on an invoice."""
    assert may_charge_tax("gst_in", "composition") is False


def test_a_regular_dealer_may_charge_tax() -> None:
    assert may_charge_tax("gst_in", "regular") is True


def test_cash_accounting_defers_tax_to_the_payment() -> None:
    """The second of the two flags, and the only other thing here that changes a
    computed amount rather than a return's appearance."""
    assert get_regime("vat_gb", "cash_accounting").tax_due_on_payment is True
    assert get_regime("vat_gb", "standard").tax_due_on_payment is False


def test_each_vat_system_owns_its_own_regime_objects() -> None:
    """``_vat_regimes()`` is a function rather than one shared dict, so a later
    amendment to one country's regimes cannot silently appear in the other three."""
    assert regimes_for("vat_gb") == regimes_for("vat_ae")
    assert REGIMES["vat_gb"]["standard"] is not REGIMES["vat_ae"]["standard"]


def test_the_returned_catalogue_is_a_copy() -> None:
    """A caller listing regimes for a form must not be able to edit the catalogue that
    validated the last posting."""
    catalogue = regimes_for("gst_in")
    catalogue.pop("regular")

    assert "regular" in regimes_for("gst_in")


def test_a_known_system_with_no_catalogue_accepts_no_registration() -> None:
    """`gst_au`, `gst_ca` and `none` are deliberately absent rather than guessed:
    regime keys are immutable once shipped, so inventing them is worse than refusing.
    For `none` it is also true by construction — "not registered" is the *absence* of
    a registration row."""
    for system in ("gst_au", "gst_ca", "none"):
        with pytest.raises(ValidationFailedError) as raised:
            regimes_for(system)

        assert raised.value.extra["fields"] == {
            "tax_system": "no regime catalogue defined for this system"
        }


def test_an_unknown_tax_system_has_no_regimes() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        regimes_for("gst_zz")

    assert raised.value.extra["fields"] == {"tax_system": "not in the platform catalogue"}


def test_an_unknown_regime_is_rejected_and_the_message_lists_the_real_ones() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        get_regime("gst_in", "flat_rate")

    assert raised.value.extra["fields"] == {"regime": "not a gst_in regime"}
    assert "composition" in str(raised.value)


def test_a_regime_of_another_system_is_not_borrowed() -> None:
    """`flat_rate` is a real VAT regime and not a GST one. Accepting it because it
    exists somewhere would let a posting compute tax under rules no Indian authority
    applies."""
    assert "flat_rate" in regimes_for("vat_gb")
    with pytest.raises(ValidationFailedError):
        get_regime("gst_in", "flat_rate")


def test_every_regime_has_a_label() -> None:
    for regimes in REGIMES.values():
        assert all(regime.label.strip() for regime in regimes.values())


def test_a_regime_cannot_be_mutated_at_runtime() -> None:
    """A catalogue validated once at import and mutable afterwards is a catalogue
    validated never."""
    with pytest.raises(AttributeError):
        get_regime("gst_in", "composition").may_charge_tax = True  # type: ignore[misc]


# --- the import-time validator ------------------------------------------------


def test_a_catalogue_under_an_unknown_system_would_fail_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(module.REGIMES, "vat_zz", {"standard": Regime("Standard")})

    with pytest.raises(ValueError, match="unknown tax system"):
        module._validate_catalogues()


def test_an_empty_catalogue_would_fail_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty dict is not "no regimes" — it is a system whose every registration
    fails at the boundary with a message about the catalogue rather than the value."""
    monkeypatch.setitem(module.REGIMES, "gst_au", {})

    with pytest.raises(ValueError, match="empty regime catalogue"):
        module._validate_catalogues()


def test_a_regime_key_that_is_not_snake_case_would_fail_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The key is stored in a row, so it would be compared against a literal that does
    not match it."""
    monkeypatch.setitem(module.REGIMES, "gst_au", {"Standard": Regime("Standard")})

    with pytest.raises(ValueError, match="snake_case"):
        module._validate_catalogues()


def test_a_regime_with_no_label_would_fail_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(module.REGIMES, "gst_au", {"standard": Regime("")})

    with pytest.raises(ValueError, match="has no label"):
        module._validate_catalogues()


def test_the_shipped_catalogues_pass_their_own_validator() -> None:
    module._validate_catalogues()


# --- registration classes -----------------------------------------------------


def test_every_regime_declares_a_known_registration_class() -> None:
    from billing_platform.tax import REGISTRATION_CLASSES

    for regimes in REGIMES.values():
        for regime in regimes.values():
            assert regime.registration_class in REGISTRATION_CLASSES


def test_the_indian_registration_classes() -> None:
    from billing_platform.tax import registration_class

    assert registration_class("gst_in", "regular") == "supplier"
    assert registration_class("gst_in", "composition") == "supplier"
    assert registration_class("gst_in", "isd") == "isd"
    assert registration_class("gst_in", "tds_deductor") == "tds_deductor"
    assert registration_class("gst_in", "ecommerce_operator") == "tcs_collector"
    assert registration_class("vat_gb", "standard") == "supplier"


def test_an_unknown_pairing_falls_back_to_supplier() -> None:
    """The fallback is the most restrictive grouping, never a free pass to coexist."""
    from billing_platform.tax import registration_class

    assert registration_class("none", "anything") == "supplier"
    assert registration_class("gst_in", "not_a_regime") == "supplier"


def test_an_unknown_registration_class_would_fail_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from billing_platform import tax as module

    monkeypatch.setitem(
        module.REGIMES, "gst_in", {"regular": Regime("Normal", registration_class="wholesale")}
    )
    with pytest.raises(ValueError, match="registration class"):
        module._validate_catalogues()
