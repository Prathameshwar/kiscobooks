"""Invoice facts expose read models and field policies without generic CRUD."""

from accounting.models import invoice as m
from accounting.models.invoice_credit import InvoiceCreditAction, InvoiceCreditEvent
from accounting.resources import Resource
from accounting.schemas import invoice as s
from accounting.schemas.invoice_credit import (
    CreditActionRequest,
    InvoiceCreditActionDetail,
    InvoiceCreditEventDetail,
)
from accounting.schemas.masters import Input

INVOICE_RESOURCES = (
    Resource(
        "invoice_record",
        "invoice-records",
        "command",
        m.InvoiceRecord,
        Input,
        Input,
        s.InvoiceRecordDetail,
        {"party_account_id": "account", "source_invoice_id": "invoice_record"},
        frozenset(),
    ),
    Resource(
        "invoice_supply_fact",
        "invoice-supply-facts",
        "command",
        m.InvoiceSupplyFact,
        Input,
        Input,
        s.InvoiceSupplyFactDetail,
        {"invoice_id": "invoice_record", "account_id": "account"},
        frozenset(),
    ),
    Resource(
        "invoice_component_fact",
        "invoice-component-facts",
        "command",
        m.InvoiceComponentFact,
        Input,
        Input,
        s.InvoiceComponentFactDetail,
        {"invoice_id": "invoice_record", "account_id": "account"},
        frozenset(),
    ),
    Resource(
        "invoice_allocation_fact",
        "invoice-allocation-facts",
        "command",
        m.InvoiceAllocationFact,
        Input,
        Input,
        s.InvoiceAllocationFactDetail,
        {
            "invoice_id": "invoice_record",
            "supply_id": "invoice_supply_fact",
            "component_id": "invoice_component_fact",
        },
        frozenset(),
    ),
    Resource(
        "invoice_tax_component",
        "invoice-tax-components",
        "command",
        m.InvoiceTaxComponent,
        Input,
        Input,
        s.InvoiceTaxComponentDetail,
        {"invoice_id": "invoice_record", "supply_id": "invoice_supply_fact"},
        frozenset(),
    ),
    Resource(
        "invoice_posting_line",
        "invoice-posting-lines",
        "command",
        m.InvoicePostingLine,
        Input,
        Input,
        s.InvoicePostingLineDetail,
        {"invoice_id": "invoice_record", "journal_line_id": "journal_line"},
        frozenset(),
    ),
    Resource(
        "invoice_credit_action",
        "invoice-credit-actions",
        "command",
        InvoiceCreditAction,
        CreditActionRequest,
        Input,
        InvoiceCreditActionDetail,
        {
            "invoice_id": "invoice_record",
            "component_id": "invoice_tax_component",
            "journal_id": "journal",
            "offset_account_id": "account",
            "cash_deposit_line_id": "journal_line",
        },
        frozenset(),
    ),
    Resource(
        "invoice_credit_event",
        "invoice-credit-events",
        "command",
        InvoiceCreditEvent,
        Input,
        Input,
        InvoiceCreditEventDetail,
        {"invoice_id": "invoice_record", "action_id": "invoice_credit_action"},
        frozenset(),
    ),
)
