"""Native bounded policy schema. No administrator-defined executable keys."""

import datetime as dt
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StrictBool,
    field_serializer,
    model_serializer,
    model_validator,
)
from voucher_execution.invoice import InvoicePolicy
from voucher_execution.money import MoneyPolicy
from voucher_execution.stock import StockPolicy

from vouchers.schemas.purchase_calculation import PurchaseCalculationPolicy


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OrderPolicy(Contract):
    """Bounded capture controls for existing non-posting order/quote/indent profiles."""

    allowed_purposes: frozenset[
        Literal["PROCURE", "INTERNAL_ISSUE", "SALE", "PURCHASE", "QUOTE"]
    ] = frozenset({"PROCURE", "INTERNAL_ISSUE", "SALE", "PURCHASE", "QUOTE"})
    max_validity_days: int | None = Field(default=None, strict=True, ge=0, le=3650)
    max_required_by_days: int | None = Field(default=None, strict=True, ge=0, le=3650)
    delivery_terms_required: StrictBool = False
    payment_terms_required: StrictBool = False

    @field_serializer("*", when_used="json")
    def sorted_sets(self, value: object) -> object:
        return sorted(value) if isinstance(value, frozenset) else value

    @model_validator(mode="after")
    def has_purpose(self) -> Self:
        if not self.allowed_purposes:
            raise ValueError("order purpose choices cannot be empty")
        return self


class MoneyConfiguration(Contract):
    """V2 voucher-facing restrictions on the existing owner-validated money input."""

    allowed_purposes: frozenset[
        Literal["GENERAL", "TRANSFER", "SETTLEMENT", "ADVANCE", "REFUND", "BILL_ADJUSTMENT"]
    ] = frozenset({"GENERAL", "TRANSFER", "SETTLEMENT", "ADVANCE", "REFUND", "BILL_ADJUSTMENT"})
    allowed_tender_modes: frozenset[
        Literal["CASH", "CHEQUE", "NEFT", "RTGS", "IMPS", "UPI", "CARD", "BANK_TRANSFER"]
    ] = frozenset({"CASH", "CHEQUE", "NEFT", "RTGS", "IMPS", "UPI", "CARD", "BANK_TRANSFER"})
    max_tenders: int = Field(default=200, strict=True, ge=0, le=200)

    @field_serializer("*", when_used="json")
    def sorted_sets(self, value: object) -> object:
        return sorted(value) if isinstance(value, frozenset) else value

    @model_validator(mode="after")
    def has_purpose(self) -> Self:
        if not self.allowed_purposes:
            raise ValueError("money purpose choices cannot be empty")
        return self


class ManufacturingConfiguration(Contract):
    """Definition-stage limits; these fields never authorize physical production."""

    bom_required: StrictBool = True
    manual_variance_allowed: StrictBool = False
    partial_runs_allowed: StrictBool = False
    max_input_lines: int = Field(default=200, strict=True, ge=1, le=1000)
    max_output_lines: int = Field(default=20, strict=True, ge=1, le=100)
    allowed_output_roles: frozenset[Literal["PRIMARY", "CO_PRODUCT", "BY_PRODUCT", "SCRAP"]] = (
        frozenset({"PRIMARY", "CO_PRODUCT", "BY_PRODUCT", "SCRAP"})
    )

    @field_serializer("*", when_used="json")
    def sorted_sets(self, value: object) -> object:
        return sorted(value) if isinstance(value, frozenset) else value

    @model_validator(mode="after")
    def primary_required(self) -> Self:
        if "PRIMARY" not in self.allowed_output_roles:
            raise ValueError("manufacturing output roles require PRIMARY")
        if not self.bom_required:
            raise ValueError("baseline manufacturing requires a published BOM")
        return self


class JobProcessConfiguration(Contract):
    """Immutable direction and restrictive preparation choices for job work."""

    role: Literal["PRINCIPAL", "WORKER"] | None = None
    order_required: StrictBool = False
    bom_required: StrictBool = False
    allowed_consumption_modes: frozenset[Literal["SEPARATE", "COMBINED"]] = frozenset({"SEPARATE"})

    @field_serializer("*", when_used="json")
    def sorted_sets(self, value: object) -> object:
        return sorted(value) if isinstance(value, frozenset) else value

    @model_validator(mode="after")
    def supported_modes(self) -> Self:
        if not self.allowed_consumption_modes:
            raise ValueError("job consumption choices cannot be empty")
        if "COMBINED" in self.allowed_consumption_modes:
            raise ValueError("combined consumption awaits an atomic stock owner")
        return self


class SalesWorkflowConfiguration(Contract):
    """Sales invoice terms and customer-order evidence, without posting effects."""

    max_due_days: int | None = Field(default=None, strict=True, ge=0, le=3650)
    customer_order_reference_required: StrictBool = False


class CommercialAttributionConfiguration(Contract):
    """Typed, default-off capture settings; no commission posting authority."""

    seller: Literal["OFF", "OPTIONAL", "REQUIRED"] = "OFF"
    broker: Literal["OFF", "OPTIONAL", "REQUIRED"] = "OFF"
    collector: Literal["OFF", "OPTIONAL", "REQUIRED"] = "OFF"
    return_handler: Literal["OFF", "OPTIONAL", "REQUIRED"] = "OFF"
    payment_handler: Literal["OFF", "OPTIONAL", "REQUIRED"] = "OFF"
    max_participants: int = Field(default=1, strict=True, ge=1, le=20)
    allow_line_assignments: StrictBool = False


class CounterConfiguration(Contract):
    mode: Literal["OFF", "OPTIONAL", "REQUIRED"] = "OFF"
    session_required: StrictBool = False


class NotificationConfiguration(Contract):
    """Opt-in external voucher messages; delivery remains Notification-owned."""

    enabled: StrictBool = False
    manual_share_allowed: StrictBool = False
    channels: frozenset[Literal["email", "sms", "whatsapp"]] = frozenset()
    automatic_events: frozenset[Literal["ISSUED", "ACCEPTED", "POSTED"]] = frozenset()

    @model_validator(mode="after")
    def usable(self) -> Self:
        if self.enabled and (
            not self.channels or not (self.manual_share_allowed or self.automatic_events)
        ):
            raise ValueError("enabled notification policy needs a channel and trigger")
        if not self.enabled and (self.manual_share_allowed or self.automatic_events):
            raise ValueError("disabled notification policy cannot request sends")
        return self


class Policy(Contract):
    stock: StockPolicy | None = None
    financial: MoneyPolicy | None = None
    invoice: InvoicePolicy | None = None
    purchase_calculation: PurchaseCalculationPolicy | None = None
    order: OrderPolicy | None = None
    money: MoneyConfiguration | None = None
    manufacturing: ManufacturingConfiguration | None = None
    job_process: JobProcessConfiguration | None = None
    sales_workflow: SalesWorkflowConfiguration | None = None
    commercial_attribution: CommercialAttributionConfiguration | None = None
    counter: CounterConfiguration | None = None
    notification: NotificationConfiguration | None = None

    @model_serializer(mode="wrap")
    def stable_legacy_policy(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.stock is None:
            result.pop("stock", None)
        if self.financial is None:
            result.pop("financial", None)
        if self.invoice is None:
            result.pop("invoice", None)
        if self.purchase_calculation is None:
            result.pop("purchase_calculation", None)
        if self.order is None:
            result.pop("order", None)
        if self.money is None:
            result.pop("money", None)
        if self.manufacturing is None:
            result.pop("manufacturing", None)
        if self.job_process is None:
            result.pop("job_process", None)
        if self.sales_workflow is None:
            result.pop("sales_workflow", None)
        if self.commercial_attribution is None:
            result.pop("commercial_attribution", None)
        if self.counter is None:
            result.pop("counter", None)
        if self.notification is None:
            result.pop("notification", None)
        return result

    @field_serializer("*", when_used="json")
    def sorted_sets(self, value: object) -> object:
        return sorted(value) if isinstance(value, frozenset) else value

    schema_version: Literal[1, 2] = 1
    allowed_modes: frozenset[Literal["ACCOUNTS", "ITEMS", "MIXED"]] = frozenset(
        {"ACCOUNTS", "ITEMS", "MIXED"}
    )
    required_sections: frozenset[
        Literal[
            "ITEMS",
            "PARTIES",
            "REFERENCES",
            "ATTACHMENTS",
            "ACCOUNTS",
            "CHARGES",
            "TAX",
            "TENDERS",
            "BILL_ALLOCATIONS",
        ]
    ] = frozenset()
    forbidden_sections: frozenset[
        Literal[
            "ITEMS",
            "PARTIES",
            "REFERENCES",
            "ATTACHMENTS",
            "ACCOUNTS",
            "CHARGES",
            "TAX",
            "TENDERS",
            "BILL_ALLOCATIONS",
        ]
    ] = frozenset()
    max_lines: int = Field(default=200, strict=True, ge=0, le=200)
    max_parties: int = Field(default=20, strict=True, ge=0, le=20)
    narration_required: StrictBool = False
    line_description_required: StrictBool = False
    approval_required: StrictBool = True
    self_approval_allowed: StrictBool = False
    backdate_days: int = Field(default=3650, strict=True, ge=0, le=3650)
    future_days: int = Field(default=365, strict=True, ge=0, le=365)
    supplier_reference_required: StrictBool = False
    allowed_party_roles: frozenset[
        Literal["CUSTOMER", "SUPPLIER", "CONSIGNEE", "PRINCIPAL", "WORKER", "CARRIER", "OTHER"]
    ] = frozenset({"CUSTOMER", "SUPPLIER", "CONSIGNEE", "PRINCIPAL", "WORKER", "CARRIER", "OTHER"})
    header_field_keys: frozenset[str] | None = Field(default=None, max_length=128)
    item_field_keys: frozenset[str] | None = Field(default=None, max_length=128)
    required_header_fields: frozenset[str] = Field(default=frozenset(), max_length=128)
    required_item_fields: frozenset[str] = Field(default=frozenset(), max_length=128)
    allowed_series_ids: frozenset[UUID] | None = Field(default=None, max_length=128)
    default_series_id: UUID | None = None
    allowed_template_revision_ids: frozenset[UUID] | None = Field(default=None, max_length=128)
    default_template_revision_id: UUID | None = None
    default_mode: Literal["ACCOUNTS", "ITEMS", "MIXED"] = "ACCOUNTS"
    default_narration: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.schema_version == 1 and any(
            value is not None
            for value in (
                self.stock,
                self.order,
                self.money,
                self.manufacturing,
                self.job_process,
                self.sales_workflow,
                self.commercial_attribution,
                self.counter,
                self.notification,
            )
        ):
            raise ValueError("typed controls require policy schema v2")
        if not self.allowed_modes or (
            self.default_mode not in self.allowed_modes
            and not (self.schema_version == 2 and "default_mode" not in self.model_fields_set)
        ):
            raise ValueError("default mode must be allowed")
        if self.required_sections & self.forbidden_sections:
            raise ValueError("section is both required and forbidden")
        for allowed, required in (
            (self.header_field_keys, self.required_header_fields),
            (self.item_field_keys, self.required_item_fields),
        ):
            if allowed is not None and not required <= allowed:
                raise ValueError("required custom fields must be bound")
        for allowed_ids, default_id in (
            (self.allowed_series_ids, self.default_series_id),
            (self.allowed_template_revision_ids, self.default_template_revision_id),
        ):
            if default_id is not None and allowed_ids is not None and default_id not in allowed_ids:
                raise ValueError("configured default must be allowed")
        import re

        for key in (
            (self.header_field_keys or frozenset())
            | (self.item_field_keys or frozenset())
            | self.required_header_fields
            | self.required_item_fields
        ):
            if not re.fullmatch(r"cf_[a-z][a-z0-9_]{0,59}", key):
                raise ValueError("invalid custom field key")
        return self


class TypeCreate(Contract):
    derived_from_revision_id: UUID | None = None
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=40)
    profile: str = Field(default="STANDARD", max_length=40)
    policy: Policy = Field(default_factory=Policy)


class Version(Contract):
    expected_version: int = Field(strict=True, ge=1)
    reason: str = Field(default="", max_length=500)


class TypeRevise(Version):
    policy: Policy


class ConfigurationCreate(Contract):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=120)
    family: Literal["COMMON", "SALES", "PURCHASE"] = "COMMON"
    policy: Policy = Field(default_factory=Policy)


class BindingCreate(Contract):
    expected_version: int = Field(strict=True, ge=1)
    configuration_revision_id: UUID
    valid_from: dt.date
    valid_to: dt.date | None = None


class ClassCreate(Contract):
    expected_version: int = Field(strict=True, ge=1)
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=120)
    policy: Policy = Field(default_factory=Policy)
