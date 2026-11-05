"""Explicit audit events selected by Accounting's publisher and accepted by Audit."""

from accounting.financial_resources import FINANCIAL_RESOURCES
from accounting.resources import RESOURCES

SENSITIVE_READS = frozenset(
    {
        "party_bank_account",
        "account_bank_profile",
        "party_tax_registration",
        "party_drug_licence",
        "party_identifier",
        "account_tax_profile",
        "party_registration_address",
        "withholding_certificate",
    }
)

IMPORT_EVENTS = frozenset(
    f"accounting.import_job.{action}" for action in ("create", "update", "export", "cleanup")
)
IMPORT_EVENTS = IMPORT_EVENTS | {
    f"accounting.{name}.{action}"
    for name in (
        "financial_opening_revision",
        "financial_opening_entry",
        "financial_opening_chunk",
        "financial_opening_import",
    )
    for action in ("create", "update", "export")
}

_FIXED = {"account_head", "accounting_setup", "account_template_installation"}
_DERIVED = {"account_group_closure", "account_template_binding"}
AUDIT_EVENTS = frozenset(
    f"accounting.{spec.name}.{action}"
    for spec in RESOURCES
    if spec.name not in _DERIVED
    for action in (
        ("create",)
        if spec.name in _FIXED
        else ("create", "update", "activate", "deactivate")
        if spec.lifecycle == "status"
        else ("create", "update")
    )
) | frozenset(
    f"accounting.account_posting_mapping.draft_{action}"
    for action in ("create", "update", "publish")
)
AUDIT_EVENTS = (
    AUDIT_EVENTS
    | IMPORT_EVENTS
    | {
        "accounting.stock_account_policy.publish",
        "accounting.stock_account_policy.close",
        "accounting.stock_account_policy.correct",
        "accounting.stock_retirement.check",
        "accounting.stock_policy.inspect",
        "accounting.stock_projection.rebuild",
        "accounting.stock_posting.post",
        "accounting.stock_posting.reverse",
        *(
            f"accounting.journal.{action}"
            for action in ("create", "update", "prepare", "post", "void")
        ),
        "accounting.journal_line.create",
        "accounting.journal_line.update",
        "accounting.financial_setup.create",
        "accounting.financial_setup.update",
        "accounting.financial_setup.reconciled",
        "accounting.fiscal_year.create",
        "accounting.fiscal_year.update",
        "accounting.fiscal_period.create",
        "accounting.fiscal_period.update",
        "accounting.fiscal_period.transition",
        "accounting.accounting_setup.metadata_upgrade",
        "accounting.accounting_setup.update",
    }
)

AUDIT_EVENTS = AUDIT_EVENTS | {
    f"accounting.{name}.{action}"
    for name in (
        "opening_batch",
        "source_document",
        "open_item",
        "allocation",
        "credit_reservation",
        "credit_override",
        "charge_policy",
        "charge_assessment",
        "charge_tax_snapshot",
        "journal_tax",
    )
    for action in (
        "create",
        "update",
        "finalize",
        "post",
        "void",
        "reverse",
        "approve",
        "release",
        "consume",
        "waive",
        "reject",
        "close",
    )
}


AUDIT_EVENTS = (
    frozenset(AUDIT_EVENTS)
    | {f"accounting.{spec.name}.export" for spec in (*RESOURCES, *FINANCIAL_RESOURCES)}
    | {f"accounting.{name}.read" for name in SENSITIVE_READS}
)


def audit_event(entity: str, action: str) -> str:
    event = f"accounting.{entity}.{action}"
    if event not in AUDIT_EVENTS:
        raise ValueError("unregistered Accounting audit event")
    return event


AUDIT_EVENTS = AUDIT_EVENTS | {"accounting.voucher_execution.record"}
AUDIT_EVENTS = AUDIT_EVENTS | {"accounting.stock_count.start", "accounting.stock_count.observe"}
AUDIT_EVENTS = AUDIT_EVENTS | {
    "accounting.stock_opening_control.create",
    "accounting.stock_opening_control.finalize",
    "accounting.stock_opening_control.reopen",
    "accounting.stock_opening_control.replace",
    "accounting.stock_opening_control.adopt",
    "accounting.stock_opening_control.confirm_zero",
    "accounting.stock_opening_control.export",
}

AUDIT_EVENTS = AUDIT_EVENTS | {
    f"accounting.exchange_rate_quote.{action}" for action in ("create", "approve", "withdraw")
}
AUDIT_EVENTS = AUDIT_EVENTS | {"accounting.exchange_rate_usage.create"}

AUDIT_EVENTS = AUDIT_EVENTS | {"accounting.reporting.captured", "accounting.reporting.snapshotted"}
AUDIT_EVENTS = AUDIT_EVENTS | {
    "accounting.reporting.snapshot_requested",
    "accounting.reporting.snapshot_started",
    "accounting.reporting.snapshot_failed",
}

AUDIT_EVENTS = AUDIT_EVENTS | {
    *("accounting.voucher_money_intent." + action for action in ("prepare", "commit", "cancel")),
    "accounting.bank_instrument.create",
    "accounting.bank_instrument_event.create",
}

AUDIT_EVENTS = AUDIT_EVENTS | {"accounting.voucher_money_allocation.create"}
AUDIT_EVENTS = AUDIT_EVENTS | {"accounting.invoice_record.prepare"}
AUDIT_EVENTS = AUDIT_EVENTS | {"accounting.gst_return_record.create"}
AUDIT_EVENTS = AUDIT_EVENTS | {"accounting.gst_outward_record.create"}
AUDIT_EVENTS = AUDIT_EVENTS | {
    "accounting.invoice_credit_action.create",
    "accounting.invoice_credit_event.create",
}

AUDIT_EVENTS = AUDIT_EVENTS | {
    f"accounting.{resource}.{action}"
    for resource in ("stock_lot", "stock_unit")
    for action in ("prepare", "correct", "hold", "release", "retire", "reactivate")
}

AUDIT_EVENTS = AUDIT_EVENTS | {
    f"accounting.party_opening_balance.{action}" for action in ("create", "withdraw")
}
AUDIT_EVENTS = AUDIT_EVENTS | {
    f"accounting.master_opening_balance.{action}"
    for action in ("create", "withdraw", "post", "reverse")
}

BANK_AUDIT_ACTIONS = {
    "bank_opening_item": ("review",),
    "bank_reconciliation_policy": ("publish",),
    "bank_statement_mapping": ("publish",),
    "bank_statement_import": ("preview", "commit", "reject"),
    "bank_statement_entry": ("duplicate_decision",),
    "bank_match_event": ("match", "unmatch"),
    "bank_adjustment_proposal": ("prepare", "resolved", "rejected"),
    "bank_reconciliation_session": ("draft", "finalize", "amend"),
}
AUDIT_EVENTS = AUDIT_EVENTS | {
    f"accounting.{entity}.{action}"
    for entity, actions in BANK_AUDIT_ACTIONS.items()
    for action in actions
}
