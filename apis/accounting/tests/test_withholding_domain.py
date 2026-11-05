"""Withholding resolution rules with no database: precedence, thresholds and shape checks."""

import datetime as dt
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.money import RoundingMode

from accounting.domain.withholding import (
    CertificateTerms,
    ProfileTerms,
    RateTerms,
    WithholdingResult,
    resolve_withholding,
    taxable_base,
    validate_certificate_terms,
    validate_profile_terms,
    validate_rate_terms,
)

D = Decimal
ON = dt.date(2026, 6, 1)
START = dt.date(2026, 4, 1)


def rate(**changes: Any) -> RateTerms:
    base = RateTerms(
        id=uuid7(),
        deductee_type="COMPANY",
        rate_percent=D("2"),
        no_pan_rate_percent=D("20"),
        single_transaction_threshold=None,
        aggregate_annual_threshold=None,
        threshold_basis="TRANSACTION",
        valid_from=START,
        valid_to=None,
    )
    return replace(base, **changes)


def profile(**changes: Any) -> ProfileTerms:
    base = ProfileTerms(
        id=uuid7(),
        kind="TDS",
        deductible=True,
        deductee_type="COMPANY",
        pan_status="VERIFIED",
        valid_from=START,
        valid_to=None,
    )
    return replace(base, **changes)


def certificate(**changes: Any) -> CertificateTerms:
    base = CertificateTerms(
        id=uuid7(), rate_percent=D("0.5"), amount_limit=None, valid_from=START, valid_to=None
    )
    return replace(base, **changes)


def resolve(
    *,
    rates: list[RateTerms] | None = None,
    profiles: list[ProfileTerms] | None = None,
    certificates: list[CertificateTerms] | None = None,
    **kwargs: Any,
) -> WithholdingResult:
    arguments: dict[str, Any] = {
        "kind": "TDS",
        "posting_date": ON,
        "amount": D("100000"),
        "precision": 2,
        "rounding": RoundingMode.HALF_UP,
    } | kwargs
    return resolve_withholding(
        rates=[rate()] if rates is None else rates,
        profiles=[profile()] if profiles is None else profiles,
        certificates=certificates or [],
        **arguments,
    )


def test_normal_rate_applies_to_a_verified_pan_and_returns_decimals() -> None:
    result = resolve()
    assert result.applies and result.reason == "WITHHELD"
    assert result.withholding_amount == D("2000.00")
    assert type(result.withholding_amount) is Decimal
    assert type(result.base_amount) is Decimal
    assert [p.rate_source for p in result.portions] == ["NORMAL"]
    assert all(type(p.amount) is Decimal for p in result.portions)
    assert result.certificate_id is None


@pytest.mark.parametrize("status", ["NOT_AVAILABLE", "INOPERATIVE"])
def test_no_pan_rate_applies_when_pan_is_not_verified(status: str) -> None:
    result = resolve(profiles=[profile(pan_status=status)])
    assert result.withholding_amount == D("20000.00")
    assert result.portions[0].rate_source == "NO_PAN"


def test_certificate_wins_over_no_pan_and_normal() -> None:
    cert = certificate()
    result = resolve(profiles=[profile(pan_status="NOT_AVAILABLE")], certificates=[cert])
    assert result.certificate_id == cert.id
    assert [p.rate_source for p in result.portions] == ["CERTIFICATE"]
    assert result.withholding_amount == D("500.00")


def test_certificate_limit_splits_the_base_and_the_rest_uses_the_fallback() -> None:
    cert = certificate(amount_limit=D("50000"))
    result = resolve(certificates=[cert], certificate_consumed=D("20000"))
    assert [(p.base_amount, p.rate_source) for p in result.portions] == [
        (D("30000.0000"), "CERTIFICATE"),
        (D("70000.0000"), "NORMAL"),
    ]
    assert result.withholding_amount == D("1550.00")
    assert result.certificate_id == cert.id


def test_exhausted_certificate_is_not_reported_as_used() -> None:
    cert = certificate(amount_limit=D("50000"))
    result = resolve(certificates=[cert], certificate_consumed=D("50000"))
    assert result.certificate_id is None
    assert [p.rate_source for p in result.portions] == ["NORMAL"]


def test_certificate_outside_its_dates_is_ignored() -> None:
    expired = certificate(valid_to=dt.date(2026, 5, 31))
    assert resolve(certificates=[expired]).certificate_id is None


def test_two_effective_certificates_conflict() -> None:
    with pytest.raises(ConflictError):
        resolve(certificates=[certificate(), certificate()])


def test_not_deductible_profile_withholds_nothing() -> None:
    result = resolve(profiles=[profile(deductible=False)])
    assert (result.applies, result.reason, result.rate_id) == (False, "NOT_DEDUCTIBLE", None)
    assert result.withholding_amount == D(0)


def test_profile_of_the_other_kind_is_not_used() -> None:
    with pytest.raises(ConflictError, match="no effective withholding profile"):
        resolve(profiles=[profile(kind="TCS")])


def test_overlapping_profiles_or_rates_conflict() -> None:
    with pytest.raises(ConflictError):
        resolve(profiles=[profile(), profile()])
    with pytest.raises(ConflictError):
        resolve(rates=[rate(), rate()])


def test_rate_for_another_deductee_type_does_not_apply() -> None:
    with pytest.raises(ConflictError, match="no effective rate"):
        resolve(rates=[rate(deductee_type="INDIVIDUAL")])


def test_superseded_rate_resolves_by_posting_date() -> None:
    old = rate(valid_to=dt.date(2026, 5, 31))
    new = rate(valid_from=dt.date(2026, 6, 1), rate_percent=D("1"), no_pan_rate_percent=D("5"))
    assert resolve(rates=[old, new], posting_date=dt.date(2026, 5, 31)).rate_id == old.id
    assert resolve(rates=[old, new]).rate_id == new.id


def test_single_transaction_threshold_is_strictly_greater() -> None:
    terms = rate(single_transaction_threshold=D("30000"))
    below = resolve(rates=[terms], amount=D("30000"))
    assert (below.applies, below.reason, below.threshold_crossed) == (
        False,
        "BELOW_THRESHOLD",
        False,
    )
    assert resolve(rates=[terms], amount=D("30000.0001")).applies


def test_aggregate_basis_catches_up_on_the_unwithheld_year_to_date() -> None:
    terms = rate(
        single_transaction_threshold=D("30000"),
        aggregate_annual_threshold=D("100000"),
        threshold_basis="AGGREGATE",
    )
    result = resolve(rates=[terms], amount=D("20000"), ytd_amount=D("90000"))
    assert result.base_amount == D("110000.0000")
    partial = resolve(
        rates=[terms], amount=D("20000"), ytd_amount=D("90000"), ytd_withheld_base=D("40000")
    )
    assert partial.base_amount == D("70000.0000")


def test_aggregate_basis_single_crossing_only_withholds_the_transaction() -> None:
    terms = rate(
        single_transaction_threshold=D("30000"),
        aggregate_annual_threshold=D("100000"),
        threshold_basis="AGGREGATE",
    )
    assert resolve(rates=[terms], amount=D("40000")).base_amount == D("40000.0000")


def test_transaction_basis_with_aggregate_crossing_withholds_only_the_transaction() -> None:
    terms = rate(aggregate_annual_threshold=D("100000"))
    result = resolve(rates=[terms], amount=D("20000"), ytd_amount=D("90000"))
    assert result.base_amount == D("20000.0000")


def test_excess_basis_withholds_only_above_the_annual_threshold() -> None:
    terms = rate(aggregate_annual_threshold=D("5000000"), threshold_basis="EXCESS")
    crossing = resolve(rates=[terms], amount=D("1000000"), ytd_amount=D("4500000"))
    assert crossing.base_amount == D("500000.0000")
    after = resolve(rates=[terms], amount=D("1000000"), ytd_amount=D("6000000"))
    assert after.base_amount == D("1000000.0000")
    below = resolve(rates=[terms], amount=D("100"), ytd_amount=D("4000000"))
    assert below.reason == "BELOW_THRESHOLD"


def test_excess_basis_without_annual_threshold_is_rejected() -> None:
    with pytest.raises(ValidationFailedError):
        taxable_base(rate(threshold_basis="EXCESS"), D(1), D(0), D(0))


def test_total_uses_company_precision_and_rounding_mode() -> None:
    terms = rate(rate_percent=D("1.5"))
    up = resolve(rates=[terms], amount=D("333"), precision=0)
    down = resolve(rates=[terms], amount=D("333"), precision=0, rounding=RoundingMode.DOWN)
    assert (up.withholding_amount, down.withholding_amount) == (D("5"), D("4"))
    assert up.portions[0].amount == D("4.9950")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "VAT"},
        {"amount": 100},
        {"amount": D("-1")},
        {"ytd_amount": D("1"), "ytd_withheld_base": D("2")},
    ],
)
def test_invalid_inputs_are_rejected(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationFailedError):
        resolve(**kwargs)


RATE = {
    "rate_percent": D("1"),
    "no_pan_rate_percent": D("20"),
    "single_transaction_threshold": None,
    "aggregate_annual_threshold": None,
    "threshold_basis": "TRANSACTION",
}


@pytest.mark.parametrize(
    "changes",
    [
        {"rate_percent": D("101")},
        {"no_pan_rate_percent": D("-1")},
        {"rate_percent": D("10"), "no_pan_rate_percent": D("5")},
        {"single_transaction_threshold": D("0")},
        {"threshold_basis": "AGGREGATE"},
        {"threshold_basis": "EXCESS"},
        {
            "threshold_basis": "EXCESS",
            "aggregate_annual_threshold": D("10"),
            "single_transaction_threshold": D("1"),
        },
        {"single_transaction_threshold": D("20"), "aggregate_annual_threshold": D("10")},
    ],
)
def test_rate_shape_rules(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationFailedError):
        validate_rate_terms(RATE | changes)


def test_valid_rate_shapes_pass() -> None:
    validate_rate_terms(RATE)
    validate_rate_terms(
        RATE | {"threshold_basis": "EXCESS", "aggregate_annual_threshold": D("5000000")}
    )
    validate_rate_terms(
        RATE
        | {
            "threshold_basis": "AGGREGATE",
            "single_transaction_threshold": D("30000"),
            "aggregate_annual_threshold": D("100000"),
        }
    )


def test_profile_pan_pairing() -> None:
    identifier = uuid7()
    validate_profile_terms({"pan_status": "VERIFIED", "pan_identifier_id": identifier})
    validate_profile_terms({"pan_status": "NOT_AVAILABLE", "pan_identifier_id": None})
    validate_profile_terms({"pan_status": "INOPERATIVE", "pan_identifier_id": identifier})
    with pytest.raises(ValidationFailedError):
        validate_profile_terms({"pan_status": "VERIFIED", "pan_identifier_id": None})
    with pytest.raises(ValidationFailedError):
        validate_profile_terms({"pan_status": "NOT_AVAILABLE", "pan_identifier_id": identifier})


def test_certificate_shape_rules() -> None:
    validate_certificate_terms({"rate_percent": D("0"), "amount_limit": None, "currency": None})
    validate_certificate_terms({"rate_percent": D("1"), "amount_limit": D("10"), "currency": "INR"})
    for values in (
        {"rate_percent": D("101"), "amount_limit": None, "currency": None},
        {"rate_percent": D("1"), "amount_limit": D("0"), "currency": "INR"},
        {"rate_percent": D("1"), "amount_limit": D("10"), "currency": None},
        {"rate_percent": D("1"), "amount_limit": None, "currency": "INR"},
    ):
        with pytest.raises(ValidationFailedError):
            validate_certificate_terms(values)
