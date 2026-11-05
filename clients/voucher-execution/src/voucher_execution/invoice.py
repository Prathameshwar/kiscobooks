"""Versioned invoice capture and policy; calculation belongs to Accounting alone."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Self

from billing_platform.exact import exact_decimal, exact_rate
from pydantic import (
    BeforeValidator,
    Field,
    PlainSerializer,
    SerializerFunctionWrapHandler,
    StrictBool,
    WithJsonSchema,
    field_serializer,
    model_serializer,
    model_validator,
)

from voucher_execution.contracts import Contract, DelegatedAuthority
from voucher_execution.money import Amount, BillAllocation, Mode, Rate, Tender
from voucher_execution.stock import StockInput

Value = Annotated[
    Decimal,
    BeforeValidator(exact_decimal),
    Field(ge=0, max_digits=19, decimal_places=4, allow_inf_nan=False),
    WithJsonSchema({"type": "string"}, mode="validation"),
    PlainSerializer(
        lambda value: format(value, ".4f"), return_type=str, when_used="json"
    ),
]
Scope = Literal["LINE", "SELECTED_LINES", "INVOICE"]


def component_number(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal | int | str):
        raise ValueError("component values require exact decimal strings")
    if isinstance(value, str) and len(value) > 128:
        raise ValueError("component value exceeds the input bound")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("invalid component decimal") from error
    if not result.is_finite():
        raise ValueError("component value must be finite")
    return (
        exact_rate(result)
        if result.copy_abs() < Decimal("100000000000")
        else exact_decimal(result)
    )


ComponentValue = Annotated[
    Decimal,
    BeforeValidator(component_number),
    Field(ge=0, max_digits=23, decimal_places=8, allow_inf_nan=False),
    WithJsonSchema({"type": "string"}, mode="validation"),
    PlainSerializer(
        lambda value: format(value, "f"), return_type=str, when_used="json"
    ),
]
InputKind = Literal["FIXED", "PERCENT", "PER_QUANTITY"]
QuantityBasis = Literal["ACTUAL", "BILLED", "ACCEPTED", "RETURNED", "MEASURED"]
ChargePurpose = Literal["FREIGHT", "PACKING", "INSURANCE", "HANDLING", "OTHER_CHARGE"]
SalesTaxProfile = Literal[
    "INDIA_DOMESTIC_SERVICE", "INDIA_DOMESTIC_SERVICE_RCM", "UNTAXED_ACCOUNT"
]
SALES_CONFIGURATION_FIELDS = frozenset(
    {
        "sales_party_account_ids",
        "sales_supply_account_ids",
        "sales_tax_profiles",
        "sales_discount_scopes",
        "sales_charge_scopes",
        "sales_charge_purposes",
        "sales_tender_modes",
        "sales_credit_allowed",
        "sales_split_tenders_allowed",
        "sales_advance_adjustments_allowed",
        "sales_invoice_rounding_allowed",
    }
)
DISCOUNT_CONFIGURATION_FIELDS = frozenset(
    {
        "discount_input_kinds",
        "discount_amount_bases",
        "max_discount_pct",
        "max_discount_amount",
        "max_discount_components",
        "discount_compounding_allowed",
    }
)


class InvoicePolicy(Contract):
    sales_supply_natures: frozenset[Literal["INCOME", "ASSET"]] = frozenset({"INCOME"})
    purchase_supply_natures: frozenset[Literal["EXPENSE", "ASSET"]] = frozenset(
        {"EXPENSE", "ASSET"}
    )
    allowed_scopes: frozenset[Scope] = frozenset({"LINE", "SELECTED_LINES", "INVOICE"})
    allowed_component_inputs: frozenset[InputKind] = frozenset(
        {"FIXED", "PERCENT", "PER_QUANTITY"}
    )
    allowed_price_bases: frozenset[Literal["NET_EXCL_TAX", "GROSS_INCL_TAX"]] = (
        frozenset({"NET_EXCL_TAX", "GROSS_INCL_TAX"})
    )
    allowed_supply_kinds: frozenset[Literal["GOODS", "SERVICE", "ACCOUNT"]] = frozenset(
        {"GOODS", "SERVICE", "ACCOUNT"}
    )
    manual_discounts_allowed: StrictBool = False
    discount_input_kinds: frozenset[InputKind] = frozenset(
        {"FIXED", "PERCENT", "PER_QUANTITY"}
    )
    discount_amount_bases: frozenset[Literal["NET_EXCL_TAX", "GROSS_INCL_TAX"]] = (
        frozenset({"NET_EXCL_TAX", "GROSS_INCL_TAX"})
    )
    max_discount_pct: Value = Field(default=Decimal(100), ge=0, le=100)
    max_discount_amount: Value | None = Field(default=None, ge=0)
    max_discount_components: int = Field(default=200, strict=True, ge=0, le=200)
    discount_compounding_allowed: StrictBool = True
    charges_allowed: StrictBool = False
    manual_free_allowed: StrictBool = False
    same_item_deals_allowed: StrictBool = False
    deal_manual_stacking_allowed: StrictBool = False
    independent_tax_allocation_allowed: StrictBool = False
    supplier_difference_limit: Value = Decimal(0)
    max_components: int = Field(default=200, strict=True, ge=0, le=200)
    max_allocations: int = Field(default=4000, strict=True, ge=0, le=4000)
    sales_party_account_ids: frozenset[uuid.UUID] | None = Field(
        default=None, max_length=128
    )
    sales_supply_account_ids: frozenset[uuid.UUID] | None = Field(
        default=None, max_length=128
    )
    sales_tax_profiles: frozenset[SalesTaxProfile] = frozenset(
        {"INDIA_DOMESTIC_SERVICE", "INDIA_DOMESTIC_SERVICE_RCM", "UNTAXED_ACCOUNT"}
    )
    sales_discount_scopes: frozenset[Scope] = frozenset(
        {"LINE", "SELECTED_LINES", "INVOICE"}
    )
    sales_charge_scopes: frozenset[Scope] = frozenset(
        {"LINE", "SELECTED_LINES", "INVOICE"}
    )
    sales_charge_purposes: frozenset[ChargePurpose] = frozenset(
        {"FREIGHT", "PACKING", "INSURANCE", "HANDLING", "OTHER_CHARGE"}
    )
    sales_tender_modes: frozenset[Mode] = frozenset(
        {"CASH", "CHEQUE", "NEFT", "RTGS", "IMPS", "UPI", "CARD", "BANK_TRANSFER"}
    )
    sales_credit_allowed: StrictBool = True
    sales_split_tenders_allowed: StrictBool = True
    sales_advance_adjustments_allowed: StrictBool = True
    sales_invoice_rounding_allowed: StrictBool = True

    @model_serializer(mode="wrap")
    def stable_invoice_policy(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        result: dict[str, object] = handler(self)
        # Existing accepted invoice hashes were calculated without these optional fields.
        # Omitting defaults preserves their canonical wire representation.
        for key in SALES_CONFIGURATION_FIELDS | DISCOUNT_CONFIGURATION_FIELDS:
            if getattr(self, key) == type(self).model_fields[key].default:
                result.pop(key, None)
        return result

    @field_serializer("*", when_used="json")
    def deterministic(self, value: object) -> object:
        if isinstance(value, Decimal):
            return format(value, ".4f")
        return sorted(value) if isinstance(value, frozenset) else value


def restrict_invoice(parent: InvoicePolicy, child: InvoicePolicy) -> InvoicePolicy:
    values = child.model_dump()
    for key in InvoicePolicy.model_fields:
        left, right = getattr(parent, key), getattr(child, key)
        if key in {
            "sales_party_account_ids",
            "sales_supply_account_ids",
            "max_discount_amount",
        }:
            if key == "max_discount_amount":
                values[key] = (
                    min(left, right)
                    if left is not None and right is not None
                    else left
                    if left is not None
                    else right
                )
                continue
            values[key] = (
                left & right
                if left is not None and right is not None
                else left
                if left is not None
                else right
            )
            continue
        values[key] = (
            left & right
            if isinstance(left, frozenset)
            else left and right
            if isinstance(left, bool)
            else min(left, right)
        )
    return InvoicePolicy.model_validate(values)


def sales_policy_violation(invoice: InvoiceInput, policy: InvoicePolicy) -> str | None:
    """Validate Sales-only choices on both the capture and calculation owner paths."""
    if (
        policy.sales_party_account_ids is not None
        and invoice.party_account_id not in policy.sales_party_account_ids
    ):
        return "sales party account is not configured"
    if policy.sales_supply_account_ids is not None and any(
        line.account_id not in policy.sales_supply_account_ids
        for line in invoice.supplies
    ):
        return "sales supply account is not configured"
    if invoice.tax.profile not in policy.sales_tax_profiles or any(
        line.tax is not None and line.tax.profile not in policy.sales_tax_profiles
        for line in invoice.supplies
    ):
        return "sales tax profile is not configured"
    if (
        not policy.sales_credit_allowed
        and not invoice.tenders
        and not invoice.allocations
    ):
        return "credit sales are not configured"
    if not policy.sales_split_tenders_allowed and len(invoice.tenders) > 1:
        return "split sales tenders are not configured"
    if not policy.sales_advance_adjustments_allowed and invoice.allocations:
        return "sales advance adjustments are not configured"
    if (
        not policy.sales_invoice_rounding_allowed
        and invoice.rounding_increment is not None
    ):
        return "sales rounding is not configured"
    if any(row.tender.mode not in policy.sales_tender_modes for row in invoice.tenders):
        return "sales tender mode is not configured"
    for component in invoice.components:
        if component.purpose == "DISCOUNT":
            if component.scope not in policy.sales_discount_scopes:
                return "sales discount scope is not configured"
        elif (
            component.purpose not in policy.sales_charge_purposes
            or component.scope not in policy.sales_charge_scopes
        ):
            return "sales charge purpose or scope is not configured"
    return None


def discount_policy_violation(
    invoice: InvoiceInput, policy: InvoicePolicy
) -> str | None:
    """Check discount recipes before calculation on both owner and producer paths."""
    discounts = tuple(row for row in invoice.components if row.purpose == "DISCOUNT")
    if len(discounts) > policy.max_discount_components:
        return "invoice exceeds configured discount component limit"
    discount_keys = {row.component_key for row in discounts}
    dependencies = {row.component_key: row.dependencies for row in invoice.components}
    for row in discounts:
        if row.input_kind not in policy.discount_input_kinds:
            return "discount input kind is not configured"
        if row.amount_basis not in policy.discount_amount_bases:
            return "discount amount basis is not configured"
        if not policy.discount_compounding_allowed:
            pending = list(row.dependencies)
            visited: set[uuid.UUID] = set()
            while pending:
                identity = pending.pop()
                if identity in visited:
                    continue
                if identity in discount_keys:
                    return "discount compounding is not configured"
                visited.add(identity)
                pending.extend(dependencies.get(identity, ()))
    return None


class InvoiceQuantity(Contract):
    basis: QuantityBasis
    quantity: Value
    unit_id: uuid.UUID


class InvoiceTaxContext(Contract):
    date_contract_version: Literal[2] = 2
    # INDIA_DOMESTIC_GOODS: forward-charge GST on goods, resolved from each item's
    # published HSN classification and rule (B24); the tax point is the invoice date.
    profile: Literal[
        "INDIA_DOMESTIC_SERVICE",
        "INDIA_DOMESTIC_SERVICE_RCM",
        "INDIA_DOMESTIC_GOODS",
        "UNTAXED_ACCOUNT",
    ]
    company_registration_id: uuid.UUID | None = None
    party_registration_id: uuid.UUID | None = None
    place_of_supply: str | None = Field(default=None, pattern=r"^IN-[A-Z0-9]{1,3}$")
    service_completion_date: dt.date | None = None
    payment_date: dt.date | None = None
    supplier_invoice_number: str | None = Field(
        default=None, min_length=1, max_length=120
    )
    supplier_invoice_date: dt.date | None = None
    withholding_section_id: uuid.UUID | None = None


class InvoiceSupply(Contract):
    line_key: uuid.UUID
    account_id: uuid.UUID
    account_version: int = Field(strict=True, ge=1)
    supply_kind: Literal["ACCOUNT", "SERVICE", "GOODS"]
    description: str = Field(min_length=1, max_length=1000)
    amount: Value
    price_basis: Literal["NET_EXCL_TAX", "GROSS_INCL_TAX"] = "NET_EXCL_TAX"
    # ITEM identity/actual and billed quantities stay on the common item detail.
    item_line_key: uuid.UUID | None = None
    quantities: tuple[InvoiceQuantity, ...] = Field(default=(), max_length=5)
    unit_price: Value | None = None
    price_denominator: Amount = Decimal(1)
    free_purpose: Literal[
        "NONE", "MANUAL_PAID_BUNDLE", "SCHEME_PAID_BUNDLE", "GIFT", "SAMPLE"
    ] = "NONE"
    free_reason: str | None = Field(default=None, min_length=1, max_length=500)
    promotion_revision_id: uuid.UUID | None = None
    promotion_version: int | None = Field(default=None, strict=True, ge=1)
    # Omission inherits the header; an explicit block is a complete line context.
    tax: InvoiceTaxContext | None = None
    # A purchased goods line whose GST cannot be claimed says so, with its reason; the
    # tax is then part of the goods' landed cost. Omitted means claimable where the
    # company's registration recovers input credit. Omitted from the wire when unset.
    input_credit: Literal["ELIGIBLE", "INELIGIBLE"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    input_credit_reason: str | None = Field(
        default=None, min_length=3, max_length=500, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.input_credit is not None and self.supply_kind != "GOODS":
            raise ValueError("an input-credit choice belongs to purchased goods")
        if (self.input_credit == "INELIGIBLE") != (self.input_credit_reason is not None):
            raise ValueError("non-claimable GST requires its reason, and only it")
        if len({row.basis for row in self.quantities}) != len(self.quantities):
            raise ValueError("quantity bases must be unique")
        if (self.promotion_revision_id is None) != (self.promotion_version is None):
            raise ValueError("promotion identity and version must be supplied together")
        if (self.free_purpose == "SCHEME_PAID_BUNDLE") != (
            self.promotion_revision_id is not None
        ):
            raise ValueError("scheme quantities require published promotion evidence")
        if (
            self.free_purpose in {"MANUAL_PAID_BUNDLE", "GIFT", "SAMPLE"}
            and self.free_reason is None
        ):
            raise ValueError("manual/free purpose requires a source reason")
        if self.supply_kind == "GOODS" and self.item_line_key is None:
            raise ValueError("goods require the common item detail")
        if self.unit_price is None and self.price_denominator != 1:
            raise ValueError("price denominator requires a unit price")
        return self


class InvoiceComponent(Contract):
    component_key: uuid.UUID
    purpose: Literal[
        "DISCOUNT", "FREIGHT", "PACKING", "INSURANCE", "HANDLING", "OTHER_CHARGE"
    ]
    scope: Scope
    effect: Literal["ADD", "DEDUCT"]
    input_kind: InputKind
    value: ComponentValue
    targets: tuple[uuid.UUID, ...] = Field(min_length=1, max_length=200)
    dependencies: tuple[uuid.UUID, ...] = Field(default=(), max_length=32)
    amount_basis: Literal["NET_EXCL_TAX", "GROSS_INCL_TAX"] = "NET_EXCL_TAX"
    allocation_basis: Literal["VALUE", "QUANTITY"] = "VALUE"
    quantity_basis: QuantityBasis | None = None
    unit_id: uuid.UUID | None = None
    denominator: Amount = Decimal(1)
    commercial_treatment: Literal["COUNTERPARTY", "THIRD_PARTY_COST"] = "COUNTERPARTY"
    tax_treatment: Literal["ASSESSABLE", "NO_CHANGE"] = "ASSESSABLE"
    # Empty targets / omitted basis retain the commercial distribution.
    tax_targets: tuple[uuid.UUID, ...] = Field(default=(), max_length=200)
    tax_allocation_basis: Literal["VALUE", "QUANTITY"] | None = None
    cost_targets: tuple[uuid.UUID, ...] = Field(default=(), max_length=200)
    cost_allocation_basis: Literal["VALUE", "QUANTITY"] = "VALUE"
    account_id: uuid.UUID | None = None
    account_version: int | None = Field(default=None, strict=True, ge=1)
    source_evidence: str = Field(min_length=1, max_length=500)
    return_treatment: Literal["PROPORTIONAL", "NONRETURNABLE"] = "PROPORTIONAL"

    @model_validator(mode="after")
    def consistent(self) -> Self:
        for refs in (
            self.targets,
            self.dependencies,
            self.cost_targets,
            self.tax_targets,
        ):
            if len(set(refs)) != len(refs):
                raise ValueError("component references must be distinct")
        if self.input_kind == "PERCENT":
            exact_rate(self.value)
        else:
            exact_decimal(self.value)
        if (self.scope == "LINE") != (len(self.targets) == 1) and self.scope == "LINE":
            raise ValueError("line scope requires one target")
        if (self.purpose == "DISCOUNT") != (self.effect == "DEDUCT"):
            raise ValueError("discounts deduct and charges add")
        if self.purpose == "DISCOUNT" and self.commercial_treatment != "COUNTERPARTY":
            raise ValueError("manual discounts must reduce counterparty consideration")
        if (self.account_id is None) != (self.account_version is None):
            raise ValueError("component account identity requires its version")
        if (
            self.input_kind == "PERCENT"
            and self.effect == "DEDUCT"
            and self.value > 100
        ):
            raise ValueError("discount percentage exceeds 100")
        uses_quantity = (
            self.input_kind == "PER_QUANTITY"
            or self.allocation_basis == "QUANTITY"
            or bool(self.cost_targets and self.cost_allocation_basis == "QUANTITY")
            or self.tax_allocation_basis == "QUANTITY"
        )
        if uses_quantity != (
            self.quantity_basis is not None and self.unit_id is not None
        ):
            raise ValueError("quantity recipe requires its basis and unit")
        if (self.quantity_basis is None) != (self.unit_id is None):
            raise ValueError("quantity basis and unit must be supplied together")
        if self.input_kind == "PER_QUANTITY" and self.allocation_basis != "QUANTITY":
            raise ValueError("per-quantity input requires quantity allocation")
        if self.input_kind != "PER_QUANTITY" and self.denominator != 1:
            raise ValueError("non-quantity input cannot carry a denominator")
        if self.commercial_treatment == "THIRD_PARTY_COST" and not self.cost_targets:
            raise ValueError("third-party costs require explicit cost targets")
        if self.tax_treatment == "NO_CHANGE" and (
            self.tax_targets or self.tax_allocation_basis is not None
        ):
            raise ValueError(
                "non-assessable components cannot carry tax allocation instructions"
            )
        if self.amount_basis == "GROSS_INCL_TAX" and (
            self.tax_targets or self.tax_allocation_basis is not None
        ):
            raise ValueError(
                "gross adjustments require their original tax distribution"
            )
        return self


class InvoiceSettlement(Contract):
    account_id: uuid.UUID
    account_version: int = Field(strict=True, ge=1)
    tender: Tender


class InvoiceInput(Contract):
    schema_version: Literal[1] = 1
    accepted_calculation_hash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    # The owner's accepted ``payable`` at the same moment as ``accepted_calculation_hash``;
    # unset until that acceptance, never recomputed here. Read-only display, never posting input.
    payable_total: Value | None = None
    source_invoice_id: uuid.UUID | None = None
    party_line_key: uuid.UUID
    party_account_id: uuid.UUID
    party_account_version: int = Field(strict=True, ge=1)
    bill_reference: str = Field(min_length=1, max_length=120)
    due_date: dt.date
    exchange_rate: Rate = Decimal(1)
    supplies: tuple[InvoiceSupply, ...] = Field(min_length=1, max_length=200)
    components: tuple[InvoiceComponent, ...] = Field(default=(), max_length=200)
    tax: InvoiceTaxContext
    tenders: tuple[InvoiceSettlement, ...] = Field(default=(), max_length=100)
    allocations: tuple[BillAllocation, ...] = Field(default=(), max_length=100)
    rounding_increment: Amount | None = None
    rounding_account_id: uuid.UUID | None = None
    rounding_account_version: int | None = Field(default=None, strict=True, ge=1)
    supplier_declared_total: Value | None = None
    supplier_difference_reason: str | None = Field(
        default=None, min_length=1, max_length=500
    )

    @model_serializer(mode="wrap")
    def stable_legacy_content(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        result: dict[str, object] = handler(self)
        if self.source_invoice_id is None:
            result.pop("source_invoice_id", None)
        return result

    @model_validator(mode="after")
    def consistent(self) -> Self:
        keys = {row.line_key for row in self.supplies}
        components = {row.component_key for row in self.components}
        if (
            len(keys) != len(self.supplies)
            or len(components) != len(self.components)
            or keys & components
        ):
            raise ValueError("invoice identities must be unique")
        tender_lines = {row.tender.line_key for row in self.tenders}
        if self.party_line_key in keys | components | tender_lines or tender_lines & (
            keys | components
        ):
            raise ValueError(
                "party, supply, component and settlement identities must be disjoint"
            )
        item_keys = [
            row.item_line_key for row in self.supplies if row.item_line_key is not None
        ]
        if len(set(item_keys)) != len(item_keys) or any(
            row.item_line_key is not None and row.item_line_key != row.line_key
            for row in self.supplies
        ):
            raise ValueError(
                "an item supply must reuse its unique common line identity"
            )
        for row in self.components:
            if (
                not set(row.targets) <= keys
                or not set(row.cost_targets) <= keys
                or not set(row.tax_targets) <= keys
                or not set(row.dependencies) <= components
                or row.component_key in row.dependencies
            ):
                raise ValueError("component references must remain within the invoice")
            if row.scope == "INVOICE" and set(row.targets) != keys:
                raise ValueError(
                    "invoice scope must include every supply; use selected lines otherwise"
                )
        if (self.rounding_account_id is None) != (
            self.rounding_account_version is None
        ):
            raise ValueError("rounding account identity requires its version")
        if self.rounding_increment is not None and self.rounding_account_id is None:
            raise ValueError("invoice rounding requires its posting account")
        if len({row.tender.tender_key for row in self.tenders}) != len(self.tenders):
            raise ValueError("duplicate invoice tender")
        return self


class InvoicePreviewCommand(Contract):
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID
    authority: DelegatedAuthority = Field(repr=False)
    kind: Literal["SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"]
    profile: Literal["STANDARD"] = "STANDARD"
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    document_date: dt.date
    posting_date: dt.date
    invoice: InvoiceInput
    policy: InvoicePolicy
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    # A goods Purchase also sends its stock lines, so Accounting can read each item's
    # published facts (base unit, purchase GST) for exactly the lines being billed.
    stock: StockInput | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def goods_match_their_stock_lines(self) -> Self:
        goods = {
            row.item_line_key: row
            for row in self.invoice.supplies
            if row.supply_kind == "GOODS" and row.item_line_key is not None
        }
        if self.stock is None:
            return self
        if self.kind != "PURCHASE" or self.stock.action != "PURCHASE_INVOICE":
            raise ValueError("only a goods Purchase bill sends its stock lines")
        if {line.line_id for line in self.stock.lines} != set(goods):
            raise ValueError("every goods supply needs exactly one stock line, and only they")
        if self.stock.stock_date != self.posting_date or self.stock.currency != self.currency:
            raise ValueError("a bill's stock date and currency are its posting date and currency")
        return self


SignedValue = Annotated[
    Decimal,
    BeforeValidator(exact_decimal),
    WithJsonSchema({"type": "string"}, mode="validation"),
    PlainSerializer(
        lambda value: format(value, ".4f"), return_type=str, when_used="json"
    ),
]


class TaxCalculation(Contract):
    key: str = Field(max_length=100)
    code: Literal["CGST", "SGST", "UTGST", "IGST", "CESS"]
    basis: Value
    amount: Value
    supplier_charged: StrictBool


class SupplyCalculation(Contract):
    key: uuid.UUID
    entered: Value
    commercial: Value
    taxable: Value
    taxes: tuple[TaxCalculation, ...] = Field(max_length=8)
    price_rounding: SignedValue
    payable: Value
    # Goods only: the value the line adds to stock (commercial value plus GST that is not
    # claimable). Omitted for other lines so existing calculation hashes are unchanged.
    stock_cost: Value | None = Field(default=None, exclude_if=lambda value: value is None)


class ComponentCalculation(Contract):
    key: uuid.UUID
    basis_amount: Value
    basis_quantity: Value | None
    input_amount: SignedValue
    amount: SignedValue


class ComponentAllocation(Contract):
    component_key: uuid.UUID
    line_key: uuid.UUID
    purpose: Literal["COMMERCIAL", "TAX_BASE", "STOCK_COST"]
    amount: SignedValue


class InvoiceCalculationDetail(Contract):
    calculation_version: Literal[1] = 1
    calculation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    currency: str
    commercial_total: Value
    tax_total: Value
    charged_tax_total: Value
    rounding: SignedValue
    payable: Value
    supplier_difference: SignedValue | None = None
    lines: tuple[SupplyCalculation, ...] = Field(max_length=200)
    components: tuple[ComponentCalculation, ...] = Field(max_length=200)
    allocations: tuple[ComponentAllocation, ...] = Field(max_length=4000)
    tax_evidence: tuple[dict[str, object], ...] = Field(max_length=200)
