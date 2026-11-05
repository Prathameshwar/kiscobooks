import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from reports.schemas.requests import GenerationDetail


class SourceGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: Literal["FRESH", "REFRESH", "COMPACT"] = "FRESH"
    base_generation_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def parent_required(self) -> Self:
        if (self.strategy == "FRESH") != (self.base_generation_id is None):
            raise ValueError("refresh/compaction require a base generation; fresh does not")
        return self


class SourceGenerationDetail(GenerationDetail):
    verified_at: dt.datetime | None = None
    strategy: Literal["FRESH", "REFRESH", "COMPACT"]
    base_generation_id: uuid.UUID | None
    source_mode: Literal["VERSIONED"] = "VERSIONED"
