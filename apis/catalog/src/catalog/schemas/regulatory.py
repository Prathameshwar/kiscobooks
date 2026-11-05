"""Explicit reviewed food and medicine classification, separate from custom fields."""

import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from catalog.schemas.pricing import DatedInput

LicenceClass = Literal["OTHER_THAN_C_C1_X", "C_C1_EXCLUDING_X", "SCHEDULE_X"]
PrescriptionSchedule = Literal["NONE", "H", "H1", "X"]


class RegulatoryClassificationInput(DatedInput):
    product_kind: Literal["NON_DRUG", "MEDICINE", "FOOD"]
    licence_class: LicenceClass | None = None
    prescription_schedule: PrescriptionSchedule | None = None
    food_category_code: str | None = Field(default=None, pattern=r"^[A-Z0-9][A-Z0-9_.-]{0,29}$")
    source_reference: str = Field(min_length=1, max_length=500)
    source_url: str = Field(min_length=1, max_length=1000)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def coherent_classification(self) -> Self:
        if self.product_kind == "MEDICINE":
            if (
                self.licence_class is None
                or self.prescription_schedule is None
                or self.food_category_code is not None
            ):
                raise ValueError("medicine requires both independent regulatory classifications")
            if (self.licence_class == "SCHEDULE_X") != (self.prescription_schedule == "X"):
                raise ValueError("Schedule X licence class and prescription schedule must agree")
        elif self.product_kind == "FOOD":
            if (
                self.licence_class is not None
                or self.prescription_schedule is not None
                or self.food_category_code is None
            ):
                raise ValueError("food requires a category code and no medicine classification")
        elif any(
            value is not None
            for value in (self.licence_class, self.prescription_schedule, self.food_category_code)
        ):
            raise ValueError("ordinary goods cannot carry food or medicine classification")
        return self


class EffectiveRegulatoryClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    row_version: int
    item_id: uuid.UUID
    valid_from: dt.date
    valid_to: dt.date | None
    product_kind: Literal["NON_DRUG", "MEDICINE", "FOOD"]
    licence_class: LicenceClass | None
    prescription_schedule: PrescriptionSchedule | None
    food_category_code: str | None
    source_reference: str
    source_url: str
    source_sha256: str
    review_reason: str
    reviewed_at: dt.datetime
    reviewed_by: uuid.UUID
