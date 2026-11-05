"""Applicability is decided from registration windows and enabled features."""

import datetime as dt

import pytest
from billing_platform.errors import ValidationFailedError

from accounting.seeds.default_accounts import applicable_accounts
from tests.test_high_priority_defaults import registration

DAY = dt.date(2026, 11, 3)
BEGIN = dt.date(2026, 4, 1)


def selected(registrations=(), features=frozenset(), states=frozenset()):
    return applicable_accounts(tuple(registrations), features, BEGIN, DAY, states)


@pytest.mark.parametrize(
    "system,regime",
    [
        ("gst_in", "unregistered"),
        ("gst_in", "composition"),
        ("gst_in", "isd"),
        ("gst_in", "tds_deductor"),
        ("vat_gb", "not_registered"),
        ("vat_gb", "exempt"),
        ("none", "none"),
    ],
)
def test_inapplicable_tax_profiles_are_not_created(system, regime):
    assert selected([registration(system, regime)]) == []


def test_union_territory_uses_the_same_configured_component_as_invoice_calculation():
    packs = selected([registration(jurisdiction_code="IN-CH")], states=frozenset({"CH"}))
    assert {p["component"] for p in packs[0].profiles.values()} == {"CGST", "UTGST", "IGST", "CESS"}
    assert all(len(code) <= 40 for code, *_ in packs[0].accounts)


def test_full_gst_pack_identifiers_fit_native_database_columns():
    from accounting.models.masters import Account, AccountTemplateInstallation

    packs = selected(
        [registration(jurisdiction_code="IN-CH")],
        features=frozenset({"reverse_charge", "inventory", "tds", "tcs"}),
        states=frozenset({"CH"}),
    )
    key_length = AccountTemplateInstallation.__table__.c.template_key.type.length
    code_length = Account.__table__.c.code.type.length
    for pack in packs:
        assert len(pack.key) <= key_length
        assert all(len(code) <= code_length for code, *_ in pack.accounts)


def test_expired_and_future_registration_windows():
    assert selected([registration(valid_to="2026-10-31")]) == []
    packs = selected([registration(valid_from="2027-01-01", valid_to="2027-12-31")])
    assert packs[0].valid_from == dt.date(2027, 1, 1)
    assert packs[0].valid_to == dt.date(2027, 12, 31)


@pytest.mark.parametrize("regime", ["flat_rate", "margin_scheme"])
def test_restricted_vat_regime_never_gets_automatic_input_recovery(regime):
    packs = selected([registration("vat_gb", regime)])
    assert {p["purpose"] for p in packs[0].profiles.values()} == {"OUTPUT_PAYABLE"}
    assert packs[0].mappings == {}  # VAT calculation is not an enabled posting workflow.


def test_reverse_charge_and_withholding_follow_features():
    packs = selected(
        [registration(regime="composition")], features=frozenset({"reverse_charge", "tds", "tcs"})
    )
    profiles = [p for pack in packs for p in pack.profiles.values()]
    assert len(profiles) == 8
    gst = [p for p in profiles if p["scheme"] == "GST_IN"]
    assert {p["purpose"] for p in gst} == {"RCM_PAYABLE"}
    assert {p["duty_type"] for p in profiles} == {"GST", "TDS", "TCS"}


def test_invalid_registration_window_is_not_silently_ignored():
    with pytest.raises(ValidationFailedError):
        selected([registration(valid_from="invalid")])


@pytest.mark.parametrize("regime", ["sez_unit", "sez_developer", "casual_taxable_person"])
def test_other_supplier_gst_regimes_follow_the_existing_charge_and_recovery_rules(regime):
    pack = selected([registration(regime=regime)])[0]
    assert {p["purpose"] for p in pack.profiles.values()} == {"OUTPUT_PAYABLE"}
