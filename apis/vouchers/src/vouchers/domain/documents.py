"""Stage-aware validation and calendar resolution without financial side effects."""

import calendar
import datetime as dt
from decimal import Decimal

from billing_platform.errors import ConflictError, ValidationFailedError
from voucher_execution.invoice import InvoicePolicy
from voucher_execution.money import MoneyPolicy

from vouchers.domain.financial import validate_money
from vouchers.domain.invoice import validate_invoice
from vouchers.domain.registry import resolve_kind
from vouchers.domain.stock import validate_stock
from vouchers.schemas.configuration import Policy
from vouchers.schemas.documents import VoucherInput


def fiscal_start(day: dt.date, month: int, start_day: int) -> dt.date:
    def start(year: int) -> dt.date:
        return dt.date(year, month, min(start_day, calendar.monthrange(year, month)[1]))

    candidate = start(day.year)
    return candidate if day >= candidate else start(day.year - 1)


def validate_content(
    content: VoucherInput, policy: Policy, *, kind: str, profile: str, stage: str, today: dt.date
) -> None:
    spec = resolve_kind(kind, profile)
    validate_stock(content, policy, kind=kind, profile=profile, stage=stage)
    counter_policy = policy.counter
    counter_allowed = kind in {"SALES_ORDER", "SALES", "CREDIT_NOTE", "RECEIPT", "PAYMENT"}
    if content.counter is not None and (
        counter_policy is None or counter_policy.mode == "OFF" or not counter_allowed
    ):
        raise ValidationFailedError("counter is not enabled for this voucher")
    if (
        stage != "DRAFT"
        and counter_allowed
        and counter_policy is not None
        and counter_policy.mode == "REQUIRED"
        and content.counter is None
    ):
        raise ValidationFailedError("counter is required")
    if (
        content.counter is not None
        and counter_policy is not None
        and counter_policy.session_required
        and content.counter.session_id is None
    ):
        raise ValidationFailedError("counter session is required")
    attribution = policy.commercial_attribution
    allowed_roles = {
        "SELLER": {"SALES_ORDER", "DELIVERY_NOTE", "SALES", "CREDIT_NOTE"},
        "BROKER": {
            "SALES_ORDER",
            "DELIVERY_NOTE",
            "SALES",
            "PURCHASE_ORDER",
            "PURCHASE",
            "CREDIT_NOTE",
            "DEBIT_NOTE",
        },
        "COLLECTOR": {"RECEIPT", "SALES"},
        "RETURN_HANDLER": {"CREDIT_NOTE", "DEBIT_NOTE"},
        "PAYMENT_HANDLER": {"PAYMENT"},
    }
    role_settings = {
        "SELLER": "seller",
        "BROKER": "broker",
        "COLLECTOR": "collector",
        "RETURN_HANDLER": "return_handler",
        "PAYMENT_HANDLER": "payment_handler",
    }
    if attribution is None and content.assignments:
        raise ValidationFailedError("commercial attribution is disabled")
    for role, field in role_settings.items():
        selected = [assignment for assignment in content.assignments if assignment.role == role]
        mode = getattr(attribution, field) if attribution is not None else "OFF"
        if selected and (mode == "OFF" or kind not in allowed_roles[role]):
            raise ValidationFailedError("commercial assignment is not allowed for this voucher")
        if stage != "DRAFT" and mode == "REQUIRED" and kind in allowed_roles[role] and not selected:
            raise ValidationFailedError("required commercial assignment is missing")
        if attribution is not None and len(selected) > attribution.max_participants:
            raise ValidationFailedError("commercial participant limit exceeded")
        groups: dict[object, Decimal] = {}
        for assignment in selected:
            if assignment.share <= 0 or assignment.share > 100:
                raise ValidationFailedError("commercial assignment share is invalid")
            if assignment.line_key is not None and (
                attribution is None
                or not attribution.allow_line_assignments
                or assignment.line_key not in {line.line_key for line in content.lines}
            ):
                raise ValidationFailedError("commercial assignment line is unavailable")
            groups[assignment.line_key] = (
                groups.get(assignment.line_key, Decimal(0)) + assignment.share
            )
        if None in groups and len(groups) > 1:
            raise ValidationFailedError("document and line assignments cannot overlap")
        if any(total != 100 for total in groups.values()):
            raise ValidationFailedError("commercial assignment shares must total 100")
    nonposting_order = kind in {"SALES_ORDER", "PURCHASE_ORDER"} or (
        kind == "STOCK_JOURNAL" and profile == "REQUISITION"
    )
    if nonposting_order:
        expected_purposes = (
            {"PROCURE", "INTERNAL_ISSUE"}
            if kind == "STOCK_JOURNAL"
            else {"QUOTE"}
            if profile == "QUOTATION"
            else {"SALE"}
            if kind == "SALES_ORDER"
            else {"PURCHASE"}
        )
        terms = content.fulfillment_terms
        order = policy.order
        if order is not None and terms is not None:
            if terms.purpose not in order.allowed_purposes:
                raise ValidationFailedError("fulfillment purpose is not allowed by configuration")
            if (
                terms.valid_until is not None
                and order.max_validity_days is not None
                and (terms.valid_until - content.document_date).days > order.max_validity_days
            ):
                raise ValidationFailedError("quotation validity exceeds configured limit")
            if (
                terms.required_by is not None
                and order.max_required_by_days is not None
                and (terms.required_by - content.document_date).days > order.max_required_by_days
            ):
                raise ValidationFailedError("required-by date exceeds configured limit")
            if stage != "DRAFT" and (
                (order.delivery_terms_required and not terms.delivery_terms.strip())
                or (order.payment_terms_required and not terms.payment_terms.strip())
            ):
                raise ValidationFailedError("configured fulfillment terms are missing")
        if (
            content.mode != "ITEMS"
            or content.financial is not None
            or content.invoice is not None
            or content.posting_date is not None
            or content.stock_date is not None
            or content.statutory_date is not None
            or (terms is not None and terms.purpose not in expected_purposes)
            or any(
                line.item.actual_quantity != 0 or line.item.billed_quantity != 0
                for line in content.lines
            )
        ):
            raise ValidationFailedError("non-posting fulfillment content is invalid")
        if terms is not None and (
            (terms.valid_until is not None and terms.valid_until < content.document_date)
            or (terms.required_by is not None and terms.required_by < content.document_date)
        ):
            raise ValidationFailedError("fulfillment dates precede the document date")
        if stage != "DRAFT" and (
            terms is None
            or not content.lines
            or any(
                line.item.planned_quantity is None or line.item.planned_quantity <= 0
                for line in content.lines
            )
            or (profile == "QUOTATION" and terms.valid_until is None)
            or (kind == "STOCK_JOURNAL" and terms.required_by is None)
        ):
            raise ValidationFailedError("accepted fulfillment content is incomplete")
        if stage != "DRAFT" and kind in {"SALES_ORDER", "PURCHASE_ORDER"}:
            required_role = "CUSTOMER" if kind == "SALES_ORDER" else "SUPPLIER"
            if not any(party.role == required_role for party in content.parties):
                raise ValidationFailedError("order party role is required")
        if (
            stage != "DRAFT"
            and profile == "QUOTATION"
            and terms is not None
            and terms.valid_until is not None
            and today > terms.valid_until
        ):
            raise ValidationFailedError("quotation validity expired")
    elif content.fulfillment_terms is not None or any(
        line.item.planned_quantity is not None for line in content.lines
    ):
        raise ValidationFailedError("fulfillment terms require a non-posting order profile")
    validate_invoice(
        content, policy.invoice or InvoicePolicy(), kind=kind, profile=profile, stage=stage
    )
    workflow = policy.sales_workflow if kind == "SALES" and profile == "STANDARD" else None
    if workflow is not None and content.invoice is not None:
        if workflow.max_due_days is not None and not (
            0 <= (content.invoice.due_date - content.document_date).days <= workflow.max_due_days
        ):
            raise ValidationFailedError("Sales invoice due date exceeds configured terms")
        if (
            stage != "DRAFT"
            and workflow.customer_order_reference_required
            and not any(
                reference.purpose == "CUSTOMER_ORDER" and reference.reference.strip()
                for reference in content.references
            )
        ):
            raise ValidationFailedError("Sales customer order reference is required")
    if (
        stage != "DRAFT"
        and kind in {"JOURNAL", "CONTRA", "PAYMENT", "RECEIPT"}
        and policy.financial is not None
        and content.financial is None
    ):
        raise ValidationFailedError("complete the native financial details before submission")
    if content.financial is not None:
        money = policy.money
        if money is not None and (
            content.financial.purpose not in money.allowed_purposes
            or len(content.financial.tenders) > money.max_tenders
            or any(
                tender.mode not in money.allowed_tender_modes
                for tender in content.financial.tenders
            )
        ):
            raise ValidationFailedError("money entry exceeds configured purpose or tender scope")
        if len(content.narration) > 1000:
            raise ValidationFailedError("financial narration is limited to 1000 characters")
        if content.mode != "ACCOUNTS" or content.stock_date or content.statutory_date:
            raise ValidationFailedError(
                "ordinary money profiles use account-only entries without tax or stock dates"
            )
        validate_money(
            content.financial,
            policy.financial or MoneyPolicy(),
            kind=kind,
            profile=profile,
            posting_date=content.posting_date,
        )
    if content.mode not in policy.allowed_modes:
        raise ValidationFailedError("entry mode is not allowed")
    present = {
        key
        for key, values in (
            ("ITEMS", content.lines),
            ("PARTIES", content.parties),
            ("REFERENCES", content.references),
            ("ATTACHMENTS", content.attachments),
            (
                "ACCOUNTS",
                content.financial.accounts
                if content.financial
                else content.invoice.supplies
                if content.invoice
                else (),
            ),
            ("CHARGES", content.invoice.components if content.invoice else ()),
            ("TAX", content.invoice.tax if content.invoice else None),
            (
                "TENDERS",
                content.financial.tenders
                if content.financial
                else content.invoice.tenders
                if content.invoice
                else (),
            ),
            (
                "BILL_ALLOCATIONS",
                content.financial.allocations
                if content.financial
                else content.invoice.allocations
                if content.invoice
                else (),
            ),
        )
        if values
    }
    if not present <= spec.sections or present & policy.forbidden_sections:
        raise ValidationFailedError("voucher contains a forbidden section")
    if content.lines and content.mode == "ACCOUNTS":
        raise ValidationFailedError("account-only mode cannot contain item lines")
    if len(content.lines) > policy.max_lines or len(content.parties) > policy.max_parties:
        raise ValidationFailedError("voucher exceeds configured cardinality")
    if content.invoice and len(content.invoice.supplies) > policy.max_lines:
        raise ValidationFailedError("invoice exceeds configured supply limit")
    if any(p.role not in policy.allowed_party_roles for p in content.parties):
        raise ValidationFailedError("party role is not allowed")
    if not -policy.backdate_days <= (content.document_date - today).days <= policy.future_days:
        raise ValidationFailedError("document date is outside configured entry window")
    for values, allowed in (
        (content.custom_fields, policy.header_field_keys),
        *((line.item.custom_fields, policy.item_field_keys) for line in content.lines),
    ):
        if allowed is not None and not values.keys() <= allowed:
            raise ValidationFailedError("custom field is not bound to this voucher type")
    if stage != "DRAFT":
        missing_sections = policy.required_sections - present
        if missing_sections:
            labels = {
                "ITEMS": "Items", "PARTIES": "Parties", "REFERENCES": "References",
                "ATTACHMENTS": "Attachments", "ACCOUNTS": "Accounts", "CHARGES": "Charges",
                "TAX": "Tax", "TENDERS": "Tenders", "BILL_ALLOCATIONS": "Bill allocations",
            }
            missing = ", ".join(labels[key] for key in sorted(missing_sections))
            raise ValidationFailedError(f"Required voucher sections are missing: {missing}.")
        if policy.narration_required and not content.narration.strip():
            raise ValidationFailedError("narration is required")
        if policy.line_description_required and any(
            not line.description.strip() for line in content.lines
        ):
            raise ValidationFailedError("line descriptions are required")
        if policy.supplier_reference_required and not any(
            r.purpose == "SUPPLIER_INVOICE" and r.reference.strip() for r in content.references
        ):
            raise ValidationFailedError("supplier reference is required")
        for values, required in (
            (content.custom_fields, policy.required_header_fields),
            *((line.item.custom_fields, policy.required_item_fields) for line in content.lines),
        ):
            if any(values.get(key) in (None, "", []) for key in required):
                raise ValidationFailedError("required custom field is missing")


def transition(
    status: str, action: str, *, approval_required: bool, nonposting_order: bool = False
) -> str:
    """The status an action leads to, or a conflict.

    Approval is a configuration choice. Where the effective policy does not require it, ``submit``
    is the only step before an approved voucher: there is nobody to wait for, and a company with a
    single user must be able to post. Where it is required, ``submit`` waits for a second actor.
    """
    targets = {
        "submit": ({"DRAFT", "REJECTED"}, "SUBMITTED" if approval_required else "APPROVED"),
        "approve": ({"SUBMITTED"}, "APPROVED"),
        "reject": ({"SUBMITTED"}, "REJECTED"),
        "issue": ({"APPROVED"} if approval_required else {"DRAFT", "APPROVED"}, "ISSUED"),
        "cancel": ({"DRAFT", "SUBMITTED", "REJECTED", "APPROVED"}, "CANCELLED"),
    }
    if nonposting_order:
        targets.update(
            {
                "accept": ({"ISSUED"}, "ACCEPTED"),
                "decline": ({"ISSUED"}, "DECLINED"),
                "expire": ({"ISSUED"}, "EXPIRED"),
                "cancel": (
                    {"DRAFT", "SUBMITTED", "REJECTED", "APPROVED", "ISSUED"},
                    "CANCELLED",
                ),
            }
        )
    rule = targets.get(action)
    if rule is None or status not in rule[0]:
        raise ConflictError("voucher action is not allowed in its current state")
    return rule[1]
