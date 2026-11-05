"""Bounded authenticated owner projections, never user-authored master facts."""

import datetime as dt
import uuid
from typing import Literal, Self

from billing_platform.custom_fields import CustomDefinition
from pydantic import Field, StrictBool, model_validator
from voucher_execution.stock_decimal import Exact

from vouchers.schemas.configuration import Contract


class Presentation(Contract):
    label: str = Field(default="", max_length=160)
    help_text: str | None = Field(default=None, max_length=1000)


class CompanyDefaultsFacts(Contract):
    inventory: StrictBool
    bom_definitions: StrictBool
    approval_workflow: StrictBool
    multi_currency: StrictBool

    @model_validator(mode="after")
    def dependencies(self) -> Self:
        if self.bom_definitions and not self.inventory:
            raise ValueError("BOM definitions require inventory")
        return self


class DefinitionFact(Contract):
    presentation: Presentation = Field(default_factory=Presentation)
    entity_type: Literal["vouchers.voucher", "vouchers.voucher_item"]
    source_version: int = Field(strict=True, ge=1)
    definition: CustomDefinition


class RegulatoryFacts(Contract):
    item_id: uuid.UUID
    valid_from: dt.date
    valid_to: dt.date | None
    product_kind: Literal["NON_DRUG", "MEDICINE", "FOOD"]
    licence_class: Literal["OTHER_THAN_C_C1_X", "C_C1_EXCLUDING_X", "SCHEDULE_X"] | None
    prescription_schedule: Literal["NONE", "H", "H1", "X"] | None
    food_category_code: str | None = Field(default=None, pattern=r"^[A-Z0-9][A-Z0-9_.-]{0,29}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_by: uuid.UUID
    reviewed_at: dt.datetime

    @model_validator(mode="after")
    def valid_evidence(self) -> Self:
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("regulatory review timestamp must have a timezone")
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("regulatory source interval is reversed")
        if self.product_kind == "MEDICINE":
            if (
                self.licence_class is None
                or self.prescription_schedule is None
                or self.food_category_code is not None
            ):
                raise ValueError("medicine classification is incomplete")
            if (self.licence_class == "SCHEDULE_X") != (self.prescription_schedule == "X"):
                raise ValueError("Schedule X axes disagree")
        elif self.product_kind == "FOOD":
            if (
                self.licence_class is not None
                or self.prescription_schedule is not None
                or self.food_category_code is None
            ):
                raise ValueError("food classification requires only its category code")
        elif any(
            value is not None
            for value in (self.licence_class, self.prescription_schedule, self.food_category_code)
        ):
            raise ValueError("ordinary goods cannot assert food or medicine classifications")
        return self


class PartyDrugLicenceFacts(Contract):
    party_id: uuid.UUID
    address_id: uuid.UUID
    licence_form: Literal["20", "20B", "21", "21B"]
    licence_number: str = Field(min_length=1, max_length=80)
    valid_from: dt.date
    valid_to: dt.date | None
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_by: uuid.UUID
    reviewed_at: dt.datetime

    @model_validator(mode="after")
    def valid_evidence(self) -> Self:
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("drug licence review timestamp must have a timezone")
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("drug licence interval is reversed")
        return self


class ItemTransactionFacts(Contract):
    kind: Literal["GOODS", "SERVICE"]
    item_version: int = Field(strict=True, ge=1)
    inventory_mode: Literal["STOCK", "NON_STOCK", "UNAVAILABLE"]
    sellable: StrictBool
    purchasable: StrictBool

    @model_validator(mode="after")
    def valid_mode(self) -> Self:
        if self.kind == "SERVICE" and self.inventory_mode != "NON_STOCK":
            raise ValueError("services cannot have stock")
        return self


class UnitMasterFacts(Contract):
    dimension: Literal["COUNT", "MASS", "VOLUME", "LENGTH", "AREA", "TIME", "JOB"]
    decimal_places: int = Field(strict=True, ge=0, le=4)
    quantity_increment: Exact = Field(gt=0)


class ItemUnitFacts(Contract):
    version: Literal[1] = 1
    item_id: uuid.UUID
    unit_id: uuid.UUID
    binding_id: uuid.UUID
    usage_role: Literal["BASE", "SALE", "PURCHASE", "BOTH", "PACK", "MEASURED"]
    conversion_mode: Literal["FIXED", "MEASURED"]
    numerator: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,18}$")
    denominator: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,18}$")
    quantity_decimal_places: int = Field(strict=True, ge=0, le=4)
    quantity_increment: Exact = Field(gt=0)
    fractional_entry: StrictBool
    valid_from: dt.date
    valid_to: dt.date | None

    @model_validator(mode="after")
    def valid_shape(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("unit interval is reversed")
        fixed = self.conversion_mode == "FIXED"
        if fixed != (self.numerator is not None and self.denominator is not None):
            raise ValueError("fixed unit requires exact ratio parts")
        if not fixed and (self.numerator is not None or self.denominator is not None):
            raise ValueError("measured unit cannot assert an actual fixed ratio")
        if any(int(part) >= 2**63 for part in (self.numerator, self.denominator) if part):
            raise ValueError("ratio part exceeds signed BIGINT")
        return self


class MasterFact(Contract):
    entity_type: Literal[
        "company",
        "item",
        "item_transaction_policy",
        "item_unit_revision",
        "unit",
        "item_regulatory_classification",
        "party",
        "party_drug_licence",
        "broker_party",
        "account",
        "fiscal_period",
        "salesperson",
    ]
    source_id: uuid.UUID
    source_version: int = Field(strict=True, ge=1)
    status: Literal["ACTIVE", "RETIRED"]
    facts: dict[str, str | int | bool | None] = Field(default_factory=dict, max_length=20)

    @model_validator(mode="after")
    def validate_regulatory_facts(self) -> Self:
        if self.entity_type == "company":
            CompanyDefaultsFacts.model_validate(self.facts)
        if self.entity_type == "unit" and self.facts:
            UnitMasterFacts.model_validate(self.facts)
        if self.entity_type == "item_unit_revision":
            ItemUnitFacts.model_validate(self.facts)
            if self.status != "ACTIVE":
                raise ValueError("unit history uses dated closure, never silent retirement")
        if self.entity_type == "item_transaction_policy":
            ItemTransactionFacts.model_validate(self.facts)
        if self.entity_type == "item_regulatory_classification":
            RegulatoryFacts.model_validate(self.facts)
            if self.status != "ACTIVE":
                raise ValueError("regulatory history cannot be retired by a source snapshot")
        if self.entity_type == "party_drug_licence":
            PartyDrugLicenceFacts.model_validate(self.facts)
            if self.status != "ACTIVE":
                raise ValueError("drug licence history cannot be retired by a source snapshot")
        return self


class SourceBundle(Contract):
    message_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    definitions: tuple[DefinitionFact, ...] = Field(default=(), max_length=128)
    masters: tuple[MasterFact, ...] = Field(default=(), max_length=200)

    @model_validator(mode="after")
    def company_identity(self) -> Self:
        company_facts = [fact for fact in self.masters if fact.entity_type == "company"]
        if len(company_facts) > 1 or any(
            fact.source_id != self.company_id for fact in company_facts
        ):
            raise ValueError("company defaults facts must identify this company exactly once")
        return self
