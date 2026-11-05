"""Presets offer only recipes allowed by the effective native invoice policy."""

from decimal import Decimal

from voucher_execution.invoice import InvoicePolicy

from vouchers.schemas.purchase_calculation import PurchaseCalculationPreset


def preset_violation(preset: PurchaseCalculationPreset, policy: InvoicePolicy) -> str | None:
    if len(preset.steps) > policy.max_components:
        return "preset exceeds the configured component limit"
    discounts = 0
    # Accounting caps the total discount, so the preset's discounts are summed: a sum of
    # percentages bounds the compounded percentage, and fixed amounts add exactly.
    percent = Decimal(0)
    fixed = Decimal(0)
    for step in preset.steps:
        if (
            step.scope not in policy.allowed_scopes
            or step.input_kind not in policy.allowed_component_inputs
            or step.amount_basis not in policy.allowed_price_bases
        ):
            return "preset calculation basis or scope is not configured"
        if step.purpose == "DISCOUNT":
            discounts += 1
            if step.input_kind == "PERCENT":
                percent += step.value
            else:
                fixed += step.value
            if not policy.manual_discounts_allowed:
                return "enable Purchase discounts before configuring discount steps"
            if (
                step.input_kind not in policy.discount_input_kinds
                or step.amount_basis not in policy.discount_amount_bases
                or percent > policy.max_discount_pct
                or (policy.max_discount_amount is not None and fixed > policy.max_discount_amount)
            ):
                return "preset discount exceeds the configured choices or limit"
            if not policy.discount_compounding_allowed and step.basis_recipe != "ORIGINAL":
                return "discount compounding is not configured"
        elif not policy.charges_allowed:
            return "enable Purchase charges before configuring charge steps"
    if discounts > policy.max_discount_components:
        return "preset exceeds the configured discount component limit"
    return None
