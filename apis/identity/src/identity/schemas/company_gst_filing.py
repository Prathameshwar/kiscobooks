import datetime as dt
import uuid
from typing import Any, Literal, Self

from pydantic import model_validator

from identity.schemas.base import StrictModel
from identity.schemas.reference import StateChoice


class GstRegistrationSetup(StrictModel):
    country_code: str
    default_tax_system: str
    can_manage: bool
    regimes: dict[str, str]
    states: list[StateChoice]
    create_schema: dict[str, Any]


class GstFilingCreate(StrictModel):
    registration_id: uuid.UUID
    frequency: Literal["MONTHLY", "QRMP"]
    valid_from: dt.date
    valid_to: dt.date | None = None

    @model_validator(mode="after")
    def complete_periods(self) -> Self:
        if self.valid_from.day != 1 or (
            self.frequency == "QRMP" and self.valid_from.month not in {1, 4, 7, 10}
        ):
            raise ValueError("frequency must start at a complete statutory period")
        if self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must follow valid_from (exclusive)")
        if self.valid_to and (
            self.valid_to.day != 1
            or (self.frequency == "QRMP" and self.valid_to.month not in {1, 4, 7, 10})
        ):
            raise ValueError("frequency must end at a complete statutory period")
        return self


class GstFilingItem(GstFilingCreate):
    id: uuid.UUID


class GstFilingClose(StrictModel):
    valid_to: dt.date
