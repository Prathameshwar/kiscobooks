import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SourceReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    company_id: uuid.UUID
    state: Literal["PREPARING", "CURRENT", "UPDATING", "DELAYED", "NEEDS_ACTION"]
    generation_id: uuid.UUID | None = None
    verified_sequence: int | None = None
    owner_sequence: int | None = None
    owner_checked_at: dt.datetime | None = None
    failure_code: str | None = None
    business_state: Literal[
        "PREPARING", "OPENING_REQUIRED", "BOOKS_NOT_STARTED", "YEAR_REQUIRED", "READY"
    ] = "PREPARING"
    inventory_state: Literal["PREPARING", "READY", "UPDATING"] = "PREPARING"
