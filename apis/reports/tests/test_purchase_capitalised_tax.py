"""Goods with non-claimable GST reconcile through their inventory principal."""

import pytest
from billing_platform.errors import ConflictError
from test_invoice_reports import purchase_dataset

from reports.domain.invoice_reconciliation import reconcile_invoices


def goods_live():
    facts, ids, journal, _, tax_line, _ = purchase_dataset()
    live = {
        (row.entity, str(row.source_id)): dict(row.data)
        for row in facts
        if not (row.entity == "journal_line" and row.source_id == tax_line)
        and not (row.entity == "invoice_posting_line" and row.data["tax_component_id"])
    }
    supply = live["invoice_supply_fact", ids["supply"]]
    supply.update(supply_kind="GOODS", credit_state="INELIGIBLE")
    for (entity, _), row in live.items():
        if (
            entity == "journal_line"
            and row["journal_id"] == str(journal.source_id)
            and row["side"] == "DEBIT"
        ):
            row.update(amount="220", base_amount="220")
        if entity == "invoice_posting_line" and row["tracking"] == "NONE":
            row["line_key"] = supply["line_key"]
    return live, ids, journal


def test_nonclaimable_goods_tax_is_capitalised_in_principal():
    live, _, _ = goods_live()
    reconcile_invoices(live)


def test_capitalisation_does_not_allow_missing_pending_tax_links():
    live, ids, _ = goods_live()
    live["invoice_supply_fact", ids["supply"]]["credit_state"] = "PENDING_EVIDENCE"
    with pytest.raises(ConflictError, match="tax GL purposes"):
        reconcile_invoices(live)


def test_capitalisation_requires_the_supply_principal_identity():
    live, _, _ = goods_live()
    link = next(
        row
        for (entity, _), row in live.items()
        if entity == "invoice_posting_line" and row["tracking"] == "NONE"
    )
    link["line_key"] = "another-supply"
    with pytest.raises(ConflictError, match="goods inventory principal"):
        reconcile_invoices(live)


@pytest.mark.parametrize(
    "field,value", [("amount", "200"), ("side", "CREDIT"), ("account_id", "wrong-account")]
)
def test_capitalised_tax_requires_the_exact_goods_principal(field, value):
    live, _, journal = goods_live()
    line = next(
        row
        for (entity, _), row in live.items()
        if entity == "journal_line"
        and row["journal_id"] == str(journal.source_id)
        and row["side"] == "DEBIT"
    )
    line[field] = value
    with pytest.raises(ConflictError, match="goods inventory principal"):
        reconcile_invoices(live)
