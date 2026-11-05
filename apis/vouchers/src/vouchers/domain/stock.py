"""Native physical profiles; stock authority remains entirely with Accounting."""

from billing_platform.errors import ValidationFailedError
from voucher_execution.stock import STOCK_PROFILES, StockPolicy

from vouchers.schemas.configuration import Policy
from vouchers.schemas.documents import VoucherInput


def restrict_stock(parent: StockPolicy, child: StockPolicy) -> StockPolicy:
    modes = {parent.opening_gl_mode, child.opening_gl_mode} - {"EITHER"}
    if len(modes) > 1:
        raise ValidationFailedError("inherited stock opening modes conflict")
    return StockPolicy.model_validate(
        {
            "allow_zero_value_receipts": parent.allow_zero_value_receipts
            and child.allow_zero_value_receipts,
            "opening_gl_mode": next(iter(modes), "EITHER"),
        }
    )


def validate_stock(
    body: VoucherInput, policy: Policy, *, kind: str, profile: str, stage: str
) -> None:
    stock = body.stock
    if stock is None:
        if (
            stage != "DRAFT"
            and policy.stock is not None
            and (kind, profile) in STOCK_PROFILES.values()
        ):
            raise ValidationFailedError(
                "complete the native physical stock details before approval or posting"
            )
        return
    if stock.action == "PURCHASE_INVOICE":
        # B24: a Product or Mixed Purchase bill brings its goods in. Its type allows goods
        # supplies; it needs no separate stock rules, as Accounting values it from the bill.
        if (
            (kind, profile) != STOCK_PROFILES[stock.action]
            or policy.invoice is None
            or "GOODS" not in policy.invoice.allowed_supply_kinds
        ):
            raise ValidationFailedError("this Purchase type does not take goods")
        if stock.currency != body.currency or stock.stock_date != body.stock_date:
            raise ValidationFailedError(
                "stock currency and movement date must match the voucher header"
            )
        if body.mode not in {"ITEMS", "MIXED"} or body.posting_date != body.stock_date:
            raise ValidationFailedError(
                "a goods bill uses item lines and receives its goods on its posting date"
            )
        return
    if (kind, profile) != STOCK_PROFILES[stock.action] or policy.stock is None:
        raise ValidationFailedError("physical stock requires its configured native voucher profile")
    if stock.currency != body.currency or stock.stock_date != body.stock_date:
        raise ValidationFailedError(
            "stock currency and movement date must match the voucher header"
        )
    if (
        body.mode != "ITEMS"
        or body.posting_date is None
        or body.statutory_date is not None
        or body.fulfillment_terms
    ):
        raise ValidationFailedError(
            "physical stock uses base-unit item lines and explicit stock/posting dates"
        )
    if (
        policy.stock.opening_gl_mode != "EITHER"
        and stock.action == "OPENING"
        and stock.opening_mode != policy.stock.opening_gl_mode
    ):
        raise ValidationFailedError("stock opening GL mode is restricted by configuration")
    if not policy.stock.allow_zero_value_receipts and any(
        line.received_value == 0 for line in stock.lines
    ):
        raise ValidationFailedError("reviewed zero-value receipts are not enabled for this voucher")
    if len(body.narration) > 1000:
        raise ValidationFailedError("stock posting narration is limited to one thousand characters")
