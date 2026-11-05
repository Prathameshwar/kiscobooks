"""Catalog GST publication payloads consumed by ``accounting.catalog_tax.v1`` (version 1).

Catalog publishes these through its outbox. ``source_version`` is Catalog's company
``CatalogPolicyState.generation`` at the change. Decimals travel as JSON strings, never
numbers, so no float ever reaches the replica.
"""

import datetime as dt
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    model_validator,
)

CLASSIFICATION_EVENT = "catalog.tax_classification.changed"
RULE_EVENT = "catalog.tax_rule.changed"
RATE_EVENT = "catalog.tax_rate.changed"
EVENT_TYPES = frozenset({CLASSIFICATION_EVENT, RULE_EVENT, RATE_EVENT})

DECIMAL_PATTERN = r"^[0-9]{1,15}(\.[0-9]{1,4})?$"
_DECIMAL = re.compile(DECIMAL_PATTERN)


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
        raise ValueError("decimal values are non-negative strings with at most four places")
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - the pattern admits only decimals
        raise ValueError("invalid decimal") from exc


#: A non-negative DECIMAL(19,4) carried as a JSON string.
DecimalString = Annotated[
    Decimal,
    BeforeValidator(_decimal),
    WithJsonSchema({"type": "string", "pattern": DECIMAL_PATTERN}),
]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Reference = Annotated[str, Field(min_length=1, max_length=500)]
Action = Literal["PUBLISH", "UPDATE", "WITHDRAW"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Change(Strict):
    """Fields every Catalog tax publication carries."""

    schema_version: Literal[1]
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    source_version: int = Field(strict=True, ge=1, le=2**63 - 1)
    action: Action


class Dated(Strict):
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))
    valid_to: dt.date | None = None

    @model_validator(mode="after")
    def ordered(self) -> "Dated":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to precedes valid_from")
        return self


class Classification(Dated):
    id: uuid.UUID
    jurisdiction: Literal["IN"]
    code_system: Literal["HSN", "SAC"]
    code: str = Field(pattern=r"^[0-9]{4,8}$")
    item_kind: Literal["GOODS", "SERVICE"]
    description: str = Field(min_length=1, max_length=1000)
    source_reference: Reference
    source_sha256: Sha256

    @model_validator(mode="after")
    def shape(self) -> "Classification":
        pattern = r"99[0-9]{4}" if self.code_system == "SAC" else r"(?!99)[0-9]{4}(?:[0-9]{2}){0,2}"
        if not re.fullmatch(pattern, self.code):
            raise ValueError("classification code does not match its code system")
        if {"HSN": "GOODS", "SAC": "SERVICE"}[self.code_system] != self.item_kind:
            raise ValueError("code system and item kind are incompatible")
        return self


class Rule(Strict):
    id: uuid.UUID
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    tax_system: Literal["gst_in"]
    jurisdiction: Literal["IN"]
    item_kind: Literal["GOODS", "SERVICE"]
    treatment: Literal["TAXABLE", "NIL_RATED", "EXEMPT", "NON_GST"]
    tax_category_id: uuid.UUID
    is_active: bool = Field(strict=True)
    source_reference: Reference
    source_sha256: Sha256


class Component(Strict):
    id: uuid.UUID
    component_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,29}$")
    component: Literal["CGST", "SGST", "UTGST", "IGST", "CESS"]
    kind: Literal["PERCENT", "FIXED_PER_UNIT"]
    percentage: DecimalString | None = None
    amount: DecimalString | None = None
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    unit_id: uuid.UUID | None = None
    basis_quantity: DecimalString | None = None
    rounding_mode: Literal["HALF_UP", "UP", "DOWN"]
    position: int = Field(strict=True, ge=0, le=15)

    @model_validator(mode="after")
    def shape(self) -> "Component":
        fixed = (self.amount, self.currency, self.unit_id, self.basis_quantity)
        if self.kind == "PERCENT":
            valid = (
                self.percentage is not None
                and (self.component == "CESS" or self.percentage <= 100)
                and all(value is None for value in fixed)
            )
        else:
            valid = (
                self.component == "CESS"
                and self.percentage is None
                and all(value is not None for value in fixed)
                and self.amount is not None
                and self.amount > 0
                and self.basis_quantity is not None
                and self.basis_quantity > 0
            )
        if not valid:
            raise ValueError("tax component shape is invalid")
        return self


class Rate(Dated):
    id: uuid.UUID
    rule_id: uuid.UUID
    series_id: uuid.UUID
    applicability: Literal["INTRA_STATE", "INTRA_UT", "INTER_STATE"]
    supersedes_id: uuid.UUID | None = None
    source_reference: Reference
    source_sha256: Sha256
    components: tuple[Component, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def distinct(self) -> "Rate":
        keys = [component.component_key for component in self.components]
        ids = [component.id for component in self.components]
        if len(set(keys)) != len(keys) or len(set(ids)) != len(ids):
            raise ValueError("rate components must be distinct")
        return self


class ClassificationChanged(Change):
    classification: Classification

    @model_validator(mode="after")
    def withdrawn(self) -> "ClassificationChanged":
        if self.action == "WITHDRAW" and self.classification.valid_to is None:
            raise ValueError("a withdrawn classification carries its end date")
        return self


class RuleChanged(Change):
    rule: Rule

    @model_validator(mode="after")
    def withdrawn(self) -> "RuleChanged":
        if self.action == "WITHDRAW" and self.rule.is_active:
            raise ValueError("a withdrawn rule is inactive")
        return self


class RateChanged(Change):
    rate: Rate

    @model_validator(mode="after")
    def withdrawn(self) -> "RateChanged":
        if self.action == "WITHDRAW" and self.rate.valid_to is None:
            raise ValueError("a withdrawn rate carries its end date")
        return self


PAYLOADS: dict[str, type[Change]] = {
    CLASSIFICATION_EVENT: ClassificationChanged,
    RULE_EVENT: RuleChanged,
    RATE_EVENT: RateChanged,
}
