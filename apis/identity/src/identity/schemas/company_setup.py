"""Creation intent is bounded business input, not arbitrary background commands."""

import datetime as dt
import uuid
from typing import Literal, Self

from billing_platform.features import required_closure
from pydantic import Field, model_validator

from identity.schemas.base import StrictModel


class CompanySetupOptions(StrictModel):
    features: list[str] = Field(default_factory=lambda: ["inventory"], max_length=30)
    opening_choice: Literal["ZERO_CONFIRMED", "IMPORT_EXISTING", "DECIDE_LATER"] = "ZERO_CONFIRMED"
    opening_reason: str | None = Field(
        default="New company; individual product openings will be entered during product creation",
        min_length=3,
        max_length=500,
    )

    @model_validator(mode="after")
    def validate_intent(self) -> Self:
        from identity.domain.company_features import OFFERED_FEATURES

        if not set(self.features) <= {offer.key for offer in OFFERED_FEATURES}:
            raise ValueError("unknown or unavailable company feature")
        self.features = sorted(
            {dependency for key in self.features for dependency in required_closure(key)}
        )
        if self.opening_choice == "ZERO_CONFIRMED" and not (
            self.opening_reason and len(self.opening_reason.strip()) >= 3
        ):
            raise ValueError("explicit zero opening requires a reason")
        if (
            self.opening_choice != "ZERO_CONFIRMED"
            and "opening_reason" not in self.model_fields_set
        ):
            self.opening_reason = None
        if self.opening_choice != "ZERO_CONFIRMED" and self.opening_reason is not None:
            raise ValueError("an opening reason requires explicit zero confirmation")
        return self


class SetupStepView(StrictModel):
    key: str
    status: str
    failure_code: str | None


class CompanySetupStatus(StrictModel):
    id: uuid.UUID
    company_id: uuid.UUID
    status: str
    opening_choice: str
    failure_code: str | None
    updated_at: dt.datetime
    steps: list[SetupStepView]
