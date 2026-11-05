"""Every printed page identifies its voucher, and the page templates are injection-safe."""

import copy

import pytest
from test_purchase_print import snapshot

from vouchers.domain.purchase_print import page_templates

INJECTION_NAME = '"><img src=//evil onerror=x></style><script>alert(1)</script>'


def footer_of(value) -> str:
    header, footer = page_templates(value)
    assert header.strip() and "<script" not in header.lower()
    return footer


def test_footer_identifies_the_voucher_supplier_bill_and_date_on_every_page():
    value = snapshot()
    value["document"]["issue_number"] = "PUR/26-27/00042"
    footer = footer_of(value)
    for fact in (
        "PUR/26-27/00042",
        "Example Supplier",
        "BILL-123",
        "31/10/2026",  # the company display format, not an ISO date
        "DRAFT",
        "Purchase voucher",
    ):
        assert fact in footer, fact
    assert "Not allocated" not in footer
    assert 'class="pageNumber"' in footer and 'class="totalPages"' in footer


def test_an_unallocated_number_uses_the_wording_of_the_first_page():
    footer = footer_of(snapshot())
    assert "Not allocated" in footer and "Example Supplier" in footer


def test_restricted_supplier_and_missing_bill_reference_use_the_first_page_wording():
    value = snapshot()
    del value["labels"]
    value["document"]["invoice"]["bill_reference"] = None
    footer = footer_of(value)
    assert "Supplier details restricted" in footer and "—" in footer


@pytest.mark.parametrize("field", ["supplier", "bill_reference", "issue_number", "status"])
def test_page_templates_escape_every_injected_value(field):
    value = snapshot()
    if field == "supplier":
        value["labels"]["supplier"] = INJECTION_NAME
    elif field == "bill_reference":
        value["document"]["invoice"]["bill_reference"] = INJECTION_NAME
    else:
        value["document"][field] = INJECTION_NAME
    header, footer = page_templates(value)
    for template in (header, footer):
        lowered = template.lower()
        assert "<img" not in lowered and "<script" not in lowered and "</style>" not in lowered
        assert "onerror=x>" not in template or "&gt;" in template
    assert "&quot;&gt;&lt;img src=//evil onerror=x&gt;&lt;/style&gt;&lt;script&gt;" in footer


def test_the_supplier_name_cannot_break_out_of_the_footer_markup():
    value = snapshot()
    value["labels"]["supplier"] = INJECTION_NAME
    footer = footer_of(value)
    # The only tags in the template are our own fixed structural ones.
    import re

    tags = set(re.findall(r"<\s*([a-zA-Z0-9]+)", footer))
    assert tags <= {"div", "span"}, tags
    assert "style=" in footer and footer.count("<div") == footer.count("</div>")


def test_the_footer_stays_compact_and_does_not_mutate_the_snapshot():
    value = snapshot()
    original = copy.deepcopy(value)
    footer = footer_of(value)
    assert footer.count("<div") <= 3  # wrapper plus at most two lines
    assert value == original
    assert len(footer) < 2_000
