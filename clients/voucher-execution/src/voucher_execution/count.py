"""Reference to an immutable native physical-count observation."""

import uuid

from pydantic import Field, field_validator

from voucher_execution.contracts import Contract


class CountCapture(Contract):
    observation_id: uuid.UUID
    expected_revision: int = Field(strict=True, ge=2)

    @field_validator("observation_id")
    @classmethod
    def real_observation(cls, value: uuid.UUID) -> uuid.UUID:
        if not value.int:
            raise ValueError("count requires a real native observation")
        return value
