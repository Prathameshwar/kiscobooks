"""Invoice capture eligibility. Accounting alone calculates or admits monetary effects."""

from billing_platform.errors import ValidationFailedError
from voucher_execution.invoice import (
    InvoicePolicy,
    InvoiceQuantity,
    discount_policy_violation,
    sales_policy_violation,
)

from vouchers.domain.duplicate_bill import normalize_bill_reference
from vouchers.schemas.documents import VoucherInput

UNPOSTABLE_PURCHASE = (
    "Goods and mixed purchases cannot be accepted, submitted or posted yet: "
    "only account and service bills can be posted."
)


def goods_bill(body: VoucherInput, *, kind: str) -> bool:
    """A well-formed Product or Mixed Purchase bill that brings its goods into stock (B24).

    Every item line is a goods supply on the invoice and a stock line on the same identity,
    received and billed in the same quantity; account and service supplies may sit beside them.
    """
    invoice, stock = body.invoice, body.stock
    if (
        kind != "PURCHASE"
        or invoice is None
        or stock is None
        or stock.action != "PURCHASE_INVOICE"
        or body.mode not in {"ITEMS", "MIXED"}
        or body.financial is not None
    ):
        return False
    goods = {row.item_line_key for row in invoice.supplies if row.supply_kind == "GOODS"}
    lines = {line.line_key for line in body.lines}
    return bool(goods) and goods == lines == {line.line_id for line in stock.lines}


def carries_unpostable_purchase_scope(
    body: VoucherInput, *, kind: str, goods_allowed: bool = False
) -> bool:
    """A Purchase with goods, stock or common item lines, which Accounting cannot post yet.

    The same boundary as ``tasks.posting.post`` and Accounting's ``request_for``: an ACCOUNTS-mode
    document of account and service supplies, with no item lines, stock date or goods supply. The
    refusal is made at acceptance and submission, so such a bill is never approved and then refused
    at posting with a generic message. Other kinds are unchanged.

    A Purchase with item lines but no invoice section (a type configured without one) is the same
    goods scope: it can be drafted, never approved, issued or posted.
    """
    if goods_allowed and goods_bill(body, kind=kind):
        return False
    invoice = body.invoice
    return kind == "PURCHASE" and (
        body.mode != "ACCOUNTS"
        or bool(body.lines)
        or body.stock is not None
        or body.stock_date is not None
        or (
            invoice is not None
            and any(
                row.supply_kind == "GOODS" or row.item_line_key is not None
                for row in invoice.supplies
            )
        )
    )


def validate_invoice(
    body: VoucherInput, policy: InvoicePolicy, *, kind: str, profile: str, stage: str = "DRAFT"
) -> None:
    if stage != "DRAFT" and carries_unpostable_purchase_scope(body, kind=kind, goods_allowed=True):
        raise ValidationFailedError(UNPOSTABLE_PURCHASE)
    invoice = body.invoice
    if invoice is None:
        return
    if (kind in {"CREDIT_NOTE", "DEBIT_NOTE"}) != (invoice.source_invoice_id is not None):
        raise ValidationFailedError("financial notes require an original invoice source")
    if kind not in {"SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"} or profile != "STANDARD":
        raise ValidationFailedError("invoice entry is unavailable for this kind/profile")
    if stage != "DRAFT" and any(row.free_purpose != "NONE" for row in invoice.supplies):
        raise ValidationFailedError("free and scheme invoice execution is not available")
    if stage != "DRAFT" and kind == "PURCHASE":
        # The duplicate-bill guard and the GST input-credit fact must name the same bill.
        number = normalize_bill_reference(invoice.bill_reference)
        if not number:
            raise ValidationFailedError("enter the supplier's bill number")
        if any(
            context is not None
            and context.supplier_invoice_number is not None
            and normalize_bill_reference(context.supplier_invoice_number) != number
            for context in (invoice.tax, *(row.tax for row in invoice.supplies))
        ):
            raise ValidationFailedError(
                "the GST supplier invoice number must match the supplier's bill number"
            )
    if stage != "DRAFT" and invoice.accepted_calculation_hash is None:
        raise ValidationFailedError("invoice calculation must be accepted before submission")
    if kind == "SALES" and (violation := sales_policy_violation(invoice, policy)):
        raise ValidationFailedError(violation)
    if violation := discount_policy_violation(invoice, policy):
        raise ValidationFailedError(violation)
    if len(invoice.components) > policy.max_components:
        raise ValidationFailedError("invoice exceeds configured component limit")
    items = {row.line_key: row for row in body.lines}
    if set(items) != {
        row.item_line_key for row in invoice.supplies if row.item_line_key is not None
    }:
        raise ValidationFailedError("invoice must identify every common item line exactly once")
    for row in invoice.supplies:
        quantities: dict[str, InvoiceQuantity] = {q.basis: q for q in row.quantities}
        if (
            row.supply_kind not in policy.allowed_supply_kinds
            or row.price_basis not in policy.allowed_price_bases
        ):
            raise ValidationFailedError("supply kind or price basis is not configured")
        if row.item_line_key is not None:
            item = items[row.item_line_key].item
            for basis, quantity in (
                ("ACTUAL", item.actual_quantity),
                ("BILLED", item.billed_quantity),
            ):
                captured = quantities.get(basis)
                if (
                    captured is None
                    or captured.quantity != quantity
                    or captured.unit_id != item.unit_id
                ):
                    raise ValidationFailedError(
                        "invoice quantities must match common item evidence"
                    )
        if "ACTUAL" in quantities and "BILLED" in quantities:
            if quantities["ACTUAL"].unit_id != quantities["BILLED"].unit_id or (
                quantities["ACTUAL"].quantity != quantities["BILLED"].quantity
                and row.free_purpose == "NONE"
            ):
                raise ValidationFailedError("actual and billed quantities are inconsistent")
        if row.free_purpose in {"MANUAL_PAID_BUNDLE", "SCHEME_PAID_BUNDLE"}:
            actual = quantities.get("ACTUAL")
            billed = quantities.get("BILLED")
            if (
                actual is None
                or billed is None
                or billed.quantity <= 0
                or actual.quantity <= billed.quantity
            ):
                raise ValidationFailedError(
                    "paid bundle requires billed units and a positive reward quantity"
                )
        if row.free_purpose == "SCHEME_PAID_BUNDLE":
            if kind != "SALES" or not policy.same_item_deals_allowed:
                raise ValidationFailedError("sales deal is not configured")
        elif row.free_purpose != "NONE" and not policy.manual_free_allowed:
            raise ValidationFailedError("manual free quantities are not configured")
    if (
        any(row.free_purpose == "SCHEME_PAID_BUNDLE" for row in invoice.supplies)
        and any(row.purpose == "DISCOUNT" for row in invoice.components)
        and not policy.deal_manual_stacking_allowed
    ):
        raise ValidationFailedError("deal/manual stacking is not configured")
    total = 0
    graph = {row.component_key: set(row.dependencies) for row in invoice.components}
    for component in invoice.components:
        if (component.tax_targets or component.tax_allocation_basis is not None) and (
            not policy.independent_tax_allocation_allowed
        ):
            raise ValidationFailedError("independent tax allocation is not configured")
        if (
            component.scope not in policy.allowed_scopes
            or component.input_kind not in policy.allowed_component_inputs
            or component.amount_basis not in policy.allowed_price_bases
        ):
            raise ValidationFailedError("component recipe is not configured")
        if component.purpose == "DISCOUNT" and not policy.manual_discounts_allowed:
            raise ValidationFailedError("manual discounts are not configured")
        if component.effect == "ADD" and not policy.charges_allowed:
            raise ValidationFailedError("invoice charges are not configured")
        total += (
            len(component.targets) * int(component.commercial_treatment == "COUNTERPARTY")
            + len(component.tax_targets or component.targets)
            * int(component.tax_treatment == "ASSESSABLE")
            + len(component.cost_targets)
        )
    if total > policy.max_allocations:
        raise ValidationFailedError("invoice exceeds configured allocation limit")
    while graph:
        ready = {key for key, dependencies in graph.items() if not dependencies & graph.keys()}
        if not ready:
            raise ValidationFailedError("invoice component dependencies contain a cycle")
        graph = {key: dependencies for key, dependencies in graph.items() if key not in ready}
    for line_key in {row.tender.line_key for row in invoice.tenders}:
        entries = [row for row in invoice.tenders if row.tender.line_key == line_key]
        if len({(row.account_id, row.account_version) for row in entries}) != 1:
            raise ValidationFailedError("split invoice tenders must name one account version")
    if any(row.tender.currency != body.currency for row in invoice.tenders):
        raise ValidationFailedError("invoice tenders must use the invoice currency")
