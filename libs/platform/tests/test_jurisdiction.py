"""Jurisdiction profiles — the shape of a country's paperwork, as code.

Two things are being defended here, and they are not the same thing.

The **catalogue** is defended by the import-time validator: a profile with a
duplicate ``kind``, an unknown tax system, or a restricted identifier that prints
on an invoice must fail the boot rather than the request that first reads it. Those
tests build a deliberately broken profile and call the validator directly, because
the real catalogue is valid by construction and there is no other way to see the
failure.

The **AADHAAR rule** is defended by ``prepare_statutory_value``, which is the single
place a full personal identity number is discarded (CLAUDE.md §5.10). Its tests are
the most load-bearing in this file: every other layer — the model, the domain gate,
the API — is downstream of this function returning ``value=None``.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from billing_platform import jurisdiction as module
from billing_platform.errors import ValidationFailedError
from billing_platform.features import FEATURES
from billing_platform.jurisdiction import (
    JURISDICTION_PROFILES,
    REGISTRATION_SCOPES,
    JurisdictionProfile,
    LicenceSpec,
    StatutoryIdSpec,
    TaxSystemSpec,
    assert_tax_registration_number,
    assert_tax_system_offered,
    gate_kinds,
    licence_spec,
    normalize_statutory_value,
    offered_tax_systems,
    prepare_statutory_value,
    profile,
    required_statutory_kinds,
    statutory_id_spec,
    supported_countries,
    tax_system_spec,
)
from billing_platform.reference import countries
from billing_platform.tax import TAX_SYSTEMS

# --- the catalogue as shipped --------------------------------------------------


def test_only_the_two_documented_jurisdictions_are_shipped() -> None:
    """A third profile is a research task with a reviewer, not a guess: a wrong
    pattern rejects a valid identifier and a missing licence kind would fail a
    posting gate open."""
    assert supported_countries() == ("GB", "IN")


def test_every_profile_names_only_known_tax_systems() -> None:
    """A system absent from ``TAX_SYSTEMS`` offers a registration no service can
    compute a tax from."""
    for entry in JURISDICTION_PROFILES.values():
        for spec in entry.tax_systems:
            assert spec.tax_system in TAX_SYSTEMS


def test_every_profile_key_is_a_real_iso_country() -> None:
    """Asserted here rather than at import: validating profile keys against
    ``reference.countries()`` would pull the ORM layer and a JSON load into a
    catalogue module's import, and the import validator checks only the shape."""
    known = {row["code"] for row in countries()}

    assert set(JURISDICTION_PROFILES) <= known


def test_india_registers_per_state_and_the_uk_per_country() -> None:
    """This is what ``company_tax_registration.jurisdiction_code`` holds, and the
    reason that column carries no foreign key."""
    assert profile("IN").tax_registration_is_per == "state"
    assert profile("GB").tax_registration_is_per == "country"
    assert {entry.tax_registration_is_per for entry in JURISDICTION_PROFILES.values()} <= (
        REGISTRATION_SCOPES
    )


def test_an_unsupported_country_is_refused_rather_than_given_an_empty_profile() -> None:
    """An empty profile would require no identifiers, offer no tax system, and fail
    every licence gate closed — a company that can be created and can never post."""
    with pytest.raises(ValidationFailedError) as raised:
        profile("FR")

    assert raised.value.extra["fields"] == {"country_code": "not a supported jurisdiction"}


def test_the_refusal_lists_what_is_supported() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        profile("FR")

    assert "GB, IN" in str(raised.value)


# --- statutory identifier specs -----------------------------------------------


def test_pan_is_required_in_india_and_prints_on_an_invoice() -> None:
    spec = statutory_id_spec("IN", "pan")

    assert spec.required is True
    assert spec.prints_on_invoice is True
    assert spec.restricted is False


def test_aadhaar_is_restricted_and_therefore_neither_required_nor_printed() -> None:
    """The two combinations the import validator forbids, asserted on the real spec:
    a required restricted identifier is the platform demanding a personal identity
    number, and a printed one is a full AADHAAR on a document."""
    spec = statutory_id_spec("IN", "aadhaar")

    assert spec.restricted is True
    assert spec.required is False
    assert spec.prints_on_invoice is False


def test_the_required_kinds_are_the_ones_a_company_cannot_be_completed_without() -> None:
    assert required_statutory_kinds("IN") == ("pan",)
    assert required_statutory_kinds("GB") == ("company_number",)


def test_an_unknown_identifier_kind_is_refused_and_the_message_lists_the_real_ones() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        statutory_id_spec("IN", "ssn")

    assert raised.value.extra["fields"] == {"kind": "not a statutory identifier in IN"}
    assert "pan" in str(raised.value)


def test_an_indian_kind_is_not_a_uk_kind() -> None:
    """Kinds are per profile, not global: `pan` on a UK company is an identifier no
    UK authority issues."""
    with pytest.raises(ValidationFailedError):
        statutory_id_spec("GB", "pan")


def test_the_cin_pattern_admits_only_the_two_real_class_letters() -> None:
    """docs/company.md §3 writes the first character class as ``[LUu]``, which is a
    typo — a CIN never starts lowercase. The pattern is asserted directly because
    normalization uppercases first, so a lowercase submission is still accepted and
    stored uppercased; the typo would only ever have widened what the regex admits.
    """
    pattern = statutory_id_spec("IN", "cin").pattern
    assert pattern is not None
    assert re.fullmatch(pattern, "u67190MH2019PTC123456") is None
    assert re.fullmatch(pattern, "L67190MH2019PTC123456") is not None
    assert prepare_statutory_value("IN", "cin", "u67190MH2019PTC123456").value == (
        "U67190MH2019PTC123456"
    )


def test_a_kind_with_no_pattern_accepts_any_non_trivial_value() -> None:
    """Udyam has no single stable format. A pattern covering only the common shape
    would reject valid registrations at the boundary — worse than not checking."""
    assert statutory_id_spec("IN", "udyam").pattern is None
    assert prepare_statutory_value("IN", "udyam", "UDYAM-MH-19-0001234").value == (
        "UDYAMMH190001234"
    )


# --- licence specs and gates --------------------------------------------------


def test_drug_licence_forms_have_distinct_retail_and_wholesale_labels() -> None:
    """Registration accepts both retail forms and preserves shipped wholesale keys."""
    expected = {
        "drug_licence_20": "retail",
        "drug_licence_21": "retail",
        "drug_licence_20b": "wholesale",
        "drug_licence_21b": "wholesale",
    }
    assert set(gate_kinds("IN", "scheduled_drug")) == set(expected)
    for kind, sale_type in expected.items():
        assert sale_type in licence_spec("IN", kind).label
    assert gate_kinds("IN", "scheduled_drug", operation="RETAIL") == (
        "drug_licence_20",
        "drug_licence_21",
    )
    assert gate_kinds("IN", "scheduled_drug", operation="WHOLESALE") == (
        "drug_licence_20b",
        "drug_licence_21b",
    )


def test_drug_licence_form_also_depends_on_drug_class() -> None:
    assert gate_kinds(
        "IN", "scheduled_drug", operation="RETAIL", drug_class="OTHER_THAN_C_C1_X"
    ) == ("drug_licence_20",)
    assert gate_kinds(
        "IN", "scheduled_drug", operation="RETAIL", drug_class="C_C1_EXCLUDING_X"
    ) == ("drug_licence_21",)
    assert gate_kinds(
        "IN", "scheduled_drug", operation="WHOLESALE", drug_class="SCHEDULE_X"
    ) == ()


def test_a_gate_no_licence_declares_resolves_to_nothing() -> None:
    """Empty means *no licence here permits it*, which callers must read as a
    refusal — see ``statutory.assert_company_can_issue``."""
    assert gate_kinds("IN", "firearm") == ()
    assert gate_kinds("GB", "scheduled_drug") == ()


def test_every_gating_licence_expires() -> None:
    """A gate satisfied by a licence with no expiry would be permanent: the row would
    keep permitting the sale after the certificate lapsed."""
    for entry in JURISDICTION_PROFILES.values():
        for spec in entry.licences:
            if spec.gates is not None:
                assert spec.has_expiry, f"{spec.kind} gates {spec.gates} but never expires"


def test_the_uk_profile_declares_no_licences_at_all() -> None:
    """Absence is a real answer, and it is why ``licence_spec``'s message has to cope
    with an empty catalogue."""
    assert profile("GB").licences == ()

    with pytest.raises(ValidationFailedError) as raised:
        licence_spec("GB", "fssai")

    assert "none" in str(raised.value)


def test_an_unknown_licence_kind_is_refused() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        licence_spec("IN", "liquor_licence")

    assert raised.value.extra["fields"] == {"kind": "not a licence kind in IN"}


# --- tax systems offered ------------------------------------------------------


def test_a_jurisdiction_offers_only_its_own_tax_systems() -> None:
    assert offered_tax_systems("IN") == ("gst_in",)
    assert offered_tax_systems("GB") == ("vat_gb",)


def test_a_foreign_tax_system_is_not_a_preference_to_be_honoured() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_tax_system_offered("IN", "vat_gb")

    assert raised.value.extra["fields"] == {"tax_system": "not offered in IN"}


def test_a_valid_gstin_is_accepted_and_returned_normalized() -> None:
    """The return value exists so a caller cannot validate one string and store
    another."""
    assert assert_tax_registration_number("IN", "gst_in", "27aaapa1234a1zt") == "27AAAPA1234A1ZT"


def test_a_gstin_with_the_wrong_check_position_is_rejected() -> None:
    """The literal ``Z`` in position 14 is part of the format, so a transposed
    character is caught rather than stored."""
    with pytest.raises(ValidationFailedError) as raised:
        assert_tax_registration_number("IN", "gst_in", "27AAAPA1234A1X5")

    assert raised.value.extra["fields"] == {"number": "does not match the gst_in format"}


def test_a_gstin_state_prefix_must_be_two_digits() -> None:
    with pytest.raises(ValidationFailedError):
        assert_tax_registration_number("IN", "gst_in", "MHAAAPA1234A1Z5")


def test_a_uk_vat_number_is_accepted_without_a_pattern() -> None:
    """A UK VAT number has several legitimate shapes — standard, branch, government
    department, health authority — so the profile declares no pattern rather than one
    that rejects three of them."""
    assert tax_system_spec("GB", "vat_gb").number_pattern is None
    assert assert_tax_registration_number("GB", "vat_gb", "GB 123 4567 89") == "GB123456789"


def test_an_empty_registration_number_is_rejected_even_with_no_pattern() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        assert_tax_registration_number("GB", "vat_gb", "   ")

    assert raised.value.extra["fields"] == {"number": "empty"}


# --- normalization ------------------------------------------------------------


def test_spaces_and_hyphens_are_not_part_of_an_identifier() -> None:
    """They are how a human writes a twelve-digit number."""
    assert normalize_statutory_value(" 1234-5678 9012 ") == "123456789012"


def test_normalization_uppercases() -> None:
    """A lowercase PAN stored beside its uppercase twin would defeat
    ``uq_company_statutory_id_company_id_kind_value_last4``."""
    assert normalize_statutory_value("aaapa1234a") == "AAAPA1234A"


# --- the AADHAAR rule, which is the reason this module exists -----------------


def test_a_restricted_identifier_keeps_only_its_last_four_digits() -> None:
    """CLAUDE.md §5.10. ``value`` is ``None`` and that is not a degraded case — it is
    the whole design."""
    stored = prepare_statutory_value("IN", "aadhaar", "1234 5678 9012")

    assert stored.value is None
    assert stored.value_last4 == "9012"


def test_the_full_restricted_value_is_absent_from_everything_returned() -> None:
    """Asserted over the whole object rather than one field, so a later field added
    to ``StoredStatutoryValue`` cannot quietly carry the number."""
    full = "123456789012"
    stored = prepare_statutory_value("IN", "aadhaar", full)

    assert full not in repr(stored)


def test_a_restricted_identifier_is_still_validated_before_it_is_discarded() -> None:
    """The pattern is checked *first*. Verifying the wrong number is worse than not
    verifying, and after the discard there is nothing left to check."""
    with pytest.raises(ValidationFailedError):
        prepare_statutory_value("IN", "aadhaar", "1234")


def test_a_rejected_restricted_value_is_not_echoed_in_the_error() -> None:
    """The rejected value in a 422 body would put a full AADHAAR into an error
    response and, from there, into whatever logs the client's failures."""
    full = "12345678901234"

    with pytest.raises(ValidationFailedError) as raised:
        prepare_statutory_value("IN", "aadhaar", full)

    assert full not in str(raised.value)
    assert full not in str(raised.value.extra)


def test_a_business_identifier_is_stored_in_full() -> None:
    """PAN, TAN, CIN, EIN and GSTIN are business identifiers, print on invoices, and
    are kept whole (CLAUDE.md §5.10)."""
    stored = prepare_statutory_value("IN", "pan", "aaapa1234a")

    assert stored.value == "AAAPA1234A"
    assert stored.value_last4 == "234A"


def test_last4_is_populated_for_an_unrestricted_kind_too() -> None:
    """Not an oversight. It is the last column of the unique key, and MariaDB treats
    NULLs inside a unique key as distinct (docs/identity-db-plan.md §2) — left NULL
    for unrestricted kinds, a company could store the same PAN twice."""
    for kind, value in (("pan", "AAAPA1234A"), ("tan", "MUMA12345B"), ("udyam", "UDYAM123456")):
        assert len(prepare_statutory_value("IN", kind, value).value_last4) == 4


def test_an_identifier_too_short_to_have_four_characters_is_refused() -> None:
    """``value_last4`` is ``CHAR``-width four and NOT NULL; a three-character value
    could not populate it, and a padded one would compare wrongly."""
    with pytest.raises(ValidationFailedError) as raised:
        prepare_statutory_value("IN", "udyam", "AB-C")

    assert raised.value.extra["fields"] == {"value": "fewer than four characters"}


def test_a_pattern_is_matched_in_full_and_not_merely_at_the_start() -> None:
    """``re.fullmatch``, not ``re.match``: a PAN with trailing junk is not a PAN."""
    with pytest.raises(ValidationFailedError):
        prepare_statutory_value("IN", "pan", "AAAPA1234AXXXX")


# --- the import-time validator ------------------------------------------------
#
# The shipped catalogue is valid, so each of these installs a deliberately broken
# profile and calls the validator directly. Without them the validator's branches
# are unreachable and a real profile mistake would reach production unchecked.

_MINIMAL = JurisdictionProfile(
    country_code="ZZ",
    tax_systems=(TaxSystemSpec("gst_in"),),
    tax_registration_is_per="country",
)


def _install(monkeypatch: pytest.MonkeyPatch, entry: JurisdictionProfile, key: str = "ZZ") -> None:
    monkeypatch.setitem(module.JURISDICTION_PROFILES, key, entry)


def test_a_profile_whose_key_disagrees_with_its_country_code_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two are read independently — the key selects the profile, the field is what
    error messages quote — so a mismatch is a profile that lies about itself."""
    _install(monkeypatch, _MINIMAL, key="YY")

    with pytest.raises(ValueError, match="declares country_code"):
        module._validate_profiles()


def test_a_profile_key_that_is_not_iso_shaped_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="IND",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
        ),
        key="IND",
    )

    with pytest.raises(ValueError, match="alpha-2"):
        module._validate_profiles()


def test_a_profile_offering_no_tax_system_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(country_code="ZZ", tax_systems=(), tax_registration_is_per="country"),
    )

    with pytest.raises(ValueError, match="offers no tax system"):
        module._validate_profiles()


def test_an_unknown_tax_system_fails_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("vat_zz"),),
            tax_registration_is_per="country",
        ),
    )

    with pytest.raises(ValueError, match="unknown tax system"):
        module._validate_profiles()


def test_the_same_tax_system_offered_twice_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``tax_systems_by_key`` would silently keep the second spec, so which pattern
    validates a number would depend on tuple order."""
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"), TaxSystemSpec("gst_in", number_pattern=r"^X$")),
            tax_registration_is_per="country",
        ),
    )

    with pytest.raises(ValueError, match="more than once"):
        module._validate_profiles()


def test_an_uncompilable_registration_pattern_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Otherwise it raises from inside the request that first validates a number."""
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in", number_pattern=r"^[A-"),),
            tax_registration_is_per="country",
        ),
    )

    with pytest.raises(re.error):
        module._validate_profiles()


def test_an_unknown_registration_scope_fails_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="city",
        ),
    )

    with pytest.raises(ValueError, match="scopes registration by"):
        module._validate_profiles()


def test_a_duplicated_identifier_kind_fails_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """One spec would shadow the other, so whether a value is restricted would depend
    on tuple order — and the losing spec could be the restricted one."""
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            statutory_ids=(
                StatutoryIdSpec(kind="pan", label="PAN"),
                StatutoryIdSpec(kind="pan", label="PAN again", restricted=True),
            ),
        ),
    )

    with pytest.raises(ValueError, match="statutory identifier"):
        module._validate_profiles()


def test_a_kind_that_is_not_snake_case_fails_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kinds are stored in rows and immutable once shipped, so the casing is part of
    the data and cannot be tidied later."""
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            statutory_ids=(StatutoryIdSpec(kind="PAN", label="PAN"),),
        ),
    )

    with pytest.raises(ValueError, match="snake_case"):
        module._validate_profiles()


def test_an_identifier_with_no_label_fails_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """The label is what a client renders; a blank one shows an empty form row."""
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            statutory_ids=(StatutoryIdSpec(kind="pan", label=""),),
        ),
    )

    with pytest.raises(ValueError, match="has no label"):
        module._validate_profiles()


def test_a_restricted_identifier_that_prints_on_an_invoice_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one outcome this module exists to prevent: a full AADHAAR on a document —
    which the platform could not even produce, since it holds only four digits."""
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            statutory_ids=(
                StatutoryIdSpec(
                    kind="aadhaar", label="Aadhaar", restricted=True, prints_on_invoice=True
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="cannot print on an invoice"):
        module._validate_profiles()


def test_a_required_restricted_identifier_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The platform has no basis to demand a personal identity number to create a
    company."""
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            statutory_ids=(
                StatutoryIdSpec(kind="aadhaar", label="Aadhaar", restricted=True, required=True),
            ),
        ),
    )

    with pytest.raises(ValueError, match="cannot be required"):
        module._validate_profiles()


def test_an_uncompilable_identifier_pattern_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            statutory_ids=(StatutoryIdSpec(kind="pan", label="PAN", pattern=r"^(unclosed"),),
        ),
    )

    with pytest.raises(re.error):
        module._validate_profiles()


def test_a_duplicated_licence_kind_fails_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            licences=(
                LicenceSpec(kind="fssai", label="FSSAI"),
                LicenceSpec(kind="fssai", label="FSSAI again"),
            ),
        ),
    )

    with pytest.raises(ValueError, match="licence"):
        module._validate_profiles()


def test_a_licence_with_no_label_fails_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            licences=(LicenceSpec(kind="fssai", label=""),),
        ),
    )

    with pytest.raises(ValueError, match="has no label"):
        module._validate_profiles()


def test_an_empty_gate_fails_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """``gates=""`` is not "gates nothing" — it is a gate no item can ever declare,
    while ``gate_kinds`` would still return the licence for it."""
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            licences=(LicenceSpec(kind="fssai", label="FSSAI", gates=""),),
        ),
    )

    with pytest.raises(ValueError, match="empty gate"):
        module._validate_profiles()


@pytest.mark.parametrize(
    ("limit", "match"),
    [
        (Decimal("NaN"), "non-finite"),
        (Decimal("0"), "non-positive"),
        (Decimal("-1.0000"), "non-positive"),
        (Decimal("1000000000000000.0000"), "exceeds DECIMAL"),
        (Decimal("200000.00001"), "more than 4 decimals"),
    ],
)
def test_an_unstorable_cash_receipt_limit_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch, limit: Decimal, match: str
) -> None:
    """A ceiling wider than ``DECIMAL(19,4)`` truncates on insert without erroring,
    which would silently *raise* a statutory limit the tenant tried to lower."""
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            cash_receipt_limit=limit,
        ),
    )

    with pytest.raises(ValueError, match=match):
        module._validate_profiles()


def test_the_shipped_catalogue_passes_its_own_validator() -> None:
    """Called at import already; asserted here so the suite fails on the validator
    rather than on collection, which reports the reason far more clearly."""
    module._validate_profiles()


def test_indias_cash_ceiling_is_the_statutory_one() -> None:
    """§269ST. A real statutory rule, so a real column on `company` — never a custom
    field (CLAUDE.md invariant 14)."""
    assert profile("IN").cash_receipt_limit == Decimal("200000.0000")


def test_a_jurisdiction_may_have_no_cash_ceiling() -> None:
    """``None`` is "no statutory limit here", which is a different answer from "not
    filled in" and is why the domain rule treats it as the largest possible raise."""
    assert profile("GB").cash_receipt_limit is None


# --- the specs are frozen -----------------------------------------------------


def test_a_profile_cannot_be_mutated_at_runtime() -> None:
    """A catalogue validated once at import and mutable afterwards is a catalogue
    validated never."""
    with pytest.raises(AttributeError):
        profile("IN").tax_registration_is_per = "country"  # type: ignore[misc]


def test_a_spec_cannot_be_mutated_at_runtime() -> None:
    with pytest.raises(AttributeError):
        statutory_id_spec("IN", "aadhaar").restricted = False  # type: ignore[misc]


def test_a_class_shape_with_no_base_pattern_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A class shape is accepted *in addition to* the base pattern; with no base the
    number is unchecked and the class shape would be dead text."""
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(
                TaxSystemSpec("gst_in", class_number_patterns=(("tds_deductor", r"^\d+$"),)),
            ),
            tax_registration_is_per="country",
        ),
    )

    with pytest.raises(ValueError, match="no base pattern"):
        module._validate_profiles()


def test_a_class_shape_for_an_unknown_registration_class_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(
                TaxSystemSpec(
                    "gst_in",
                    number_pattern=r"^\d+$",
                    class_number_patterns=(("wholesaler", r"^\d+$"),),
                ),
            ),
            tax_registration_is_per="country",
        ),
    )

    with pytest.raises(ValueError, match="unknown registration class"):
        module._validate_profiles()


def test_a_gstin_is_checksummed_and_state_prefixed_in_the_profile() -> None:
    spec = tax_system_spec("IN", "gst_in")
    assert spec.mod36_check and spec.state_prefixed
    assert spec.number_patterns_for("supplier") == (spec.number_pattern,)
    assert len(spec.number_patterns_for("tds_deductor")) == 2
    assert tax_system_spec("GB", "vat_gb").number_patterns_for("tds_deductor") == ()


# --- default_features ---------------------------------------------------------
#
# The capabilities a setup form offers pre-selected (docs/company-features.md §3).
# A default lives in the profile rather than in a client because three clients
# would hold three lists; what is defended here is that the list is honourable —
# every key exists, is offerable where it is suggested, and carries what it needs.


def test_every_default_feature_is_a_real_capability() -> None:
    for entry in JURISDICTION_PROFILES.values():
        for key in entry.default_features:
            assert key in FEATURES


def test_every_default_feature_is_offerable_in_its_own_jurisdiction() -> None:
    """A tax-gated default outside the jurisdiction's systems would be selected and
    then filtered out of the form, and refused by the enable call behind it."""
    for entry in JURISDICTION_PROFILES.values():
        offered = {spec.tax_system for spec in entry.tax_systems}
        for key in entry.default_features:
            gated = FEATURES[key].tax_systems
            assert not gated or offered & set(gated)


def test_defaults_carry_their_own_dependencies_in_order() -> None:
    """Stated rather than closed at read time: a form that enables them in order must
    never ask for a dependent before the feature it needs."""
    for entry in JURISDICTION_PROFILES.values():
        seen: set[str] = set()
        for key in entry.default_features:
            assert set(FEATURES[key].requires) <= seen
            seen.add(key)


def test_both_jurisdictions_default_to_the_ordinary_trading_capabilities() -> None:
    """Stock and credit limits are the common case for a company that bills goods;
    India adds the e-way bill, which any consignment over the threshold needs
    whatever the turnover. ``e_invoicing`` is deliberately **not** a default: it
    starts at a turnover threshold and needs IRP credentials this platform does not
    have at creation time."""
    assert JURISDICTION_PROFILES["IN"].default_features == (
        "inventory",
        "credit_limits",
        "e_waybill",
    )
    assert JURISDICTION_PROFILES["GB"].default_features == ("inventory", "credit_limits")
    assert "e_invoicing" not in JURISDICTION_PROFILES["IN"].default_features


def test_an_unknown_default_feature_fails_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            default_features=("teleportation",),
        ),
    )

    with pytest.raises(ValueError, match="unknown feature"):
        module._validate_profiles()


def test_a_default_feature_gated_to_another_tax_system_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("vat_gb"),),
            tax_registration_is_per="country",
            default_features=("e_invoicing",),
        ),
    )

    with pytest.raises(ValueError, match="only offerable under"):
        module._validate_profiles()


def test_a_default_feature_missing_its_dependency_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            default_features=("batch_tracking",),
        ),
    )

    with pytest.raises(ValueError, match="without its dependencies"):
        module._validate_profiles()


def test_a_default_feature_listed_before_its_dependency_fails_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both keys are present, so membership alone would accept this. The list is served in
    the order it is written, for a caller that enables them in turn."""
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            default_features=("e_waybill", "inventory"),
        ),
    )

    with pytest.raises(ValueError, match="before it"):
        module._validate_profiles()


def test_the_same_default_feature_twice_fails_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        JurisdictionProfile(
            country_code="ZZ",
            tax_systems=(TaxSystemSpec("gst_in"),),
            tax_registration_is_per="country",
            default_features=("inventory", "inventory"),
        ),
    )

    with pytest.raises(ValueError, match="default feature"):
        module._validate_profiles()
