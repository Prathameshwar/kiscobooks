import datetime as dt

import pytest
from billing_platform.errors import ValidationFailedError

from accounting.domain.invoice_tax_dates import payment_date, service_tax_point


def day(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def test_service_tax_point_is_independent_of_gl_and_handles_late_invoicing():
    timely = service_tax_point(invoice=day("2026-04-05"), supplied=day("2026-03-31"))
    late = service_tax_point(invoice=day("2026-05-05"), supplied=day("2026-03-31"))
    assert timely.tax_point_date == day("2026-04-05") and timely.date_contract_version == 2
    assert late.tax_point_date == day("2026-03-31") and late.legal_basis == "CGST_13_2_B"
    prepaid = service_tax_point(
        invoice=day("2026-04-05"),
        supplied=day("2026-03-31"),
        payment_book=day("2026-03-20"),
        payment_bank=day("2026-03-22"),
    )
    assert prepaid.tax_point_date == day("2026-03-20")


def test_supplier_invoiced_rcm_uses_earlier_payment_or_day_after_sixty_days():
    base = {"invoice": day("2026-04-01"), "supplied": day("2026-04-01"), "reverse_charge": True}
    assert service_tax_point(**base).tax_point_date == day("2026-06-01")
    assert service_tax_point(**base, payment_bank=day("2026-05-30")).tax_point_date == day(
        "2026-05-30"
    )
    with pytest.raises(ValidationFailedError, match="self-invoices"):
        service_tax_point(**base, supplier_issued=False)


@pytest.mark.parametrize(
    "supply,invoice,paid,expected,basis",
    [
        ("2026-03-25", "2026-04-02", "2026-04-03", "2026-04-02", "CGST_14_A_I"),
        ("2026-03-25", "2026-03-28", "2026-04-03", "2026-03-28", "CGST_14_A_II"),
        ("2026-03-25", "2026-04-02", "2026-03-28", "2026-03-28", "CGST_14_A_III"),
        ("2026-04-02", "2026-03-28", "2026-04-03", "2026-04-03", "CGST_14_B_I"),
        ("2026-04-02", "2026-03-28", "2026-03-29", "2026-03-28", "CGST_14_B_II"),
        ("2026-04-02", "2026-04-03", "2026-03-29", "2026-04-03", "CGST_14_B_III"),
    ],
)
def test_six_statutory_rate_transition_cases(supply, invoice, paid, expected, basis):
    result = service_tax_point(
        invoice=day(invoice),
        supplied=day(supply),
        payment_book=day(paid),
        rate_change=day("2026-04-01"),
    )
    assert (result.tax_point_date, result.legal_basis) == (day(expected), basis)


def test_bank_credit_rule_and_unsupported_transition_are_explicit():
    assert payment_date(day("2026-03-30"), day("2026-04-06"), change=day("2026-04-01")) == day(
        "2026-04-06"
    )
    assert payment_date(day("2026-03-30"), day("2026-04-05"), change=day("2026-04-01")) == day(
        "2026-03-30"
    )
    with pytest.raises(ValidationFailedError, match="payment evidence"):
        service_tax_point(
            invoice=day("2026-04-03"), supplied=day("2026-03-30"), rate_change=day("2026-04-01")
        )
    with pytest.raises(ValidationFailedError, match="RCM with"):
        service_tax_point(
            invoice=day("2026-04-03"),
            supplied=day("2026-03-30"),
            rate_change=day("2026-04-01"),
            reverse_charge=True,
        )


def test_invalid_dates_and_overflow_fail_closed():
    with pytest.raises(ValidationFailedError, match="precede"):
        service_tax_point(invoice=day("2017-06-30"), supplied=day("2017-06-30"))
    with pytest.raises(ValidationFailedError, match="range"):
        service_tax_point(invoice=dt.date.max, supplied=dt.date.max, reverse_charge=True)


@pytest.mark.parametrize("change", ["2026-01-01", "2026-12-01"])
def test_rate_change_outside_all_supply_facts_keeps_ordinary_late_invoice_rule(change):
    result = service_tax_point(
        invoice=day("2026-05-05"),
        supplied=day("2026-03-01"),
        payment_book=day("2026-05-06"),
        rate_change=day(change),
    )
    assert result.tax_point_date == day("2026-03-01")
