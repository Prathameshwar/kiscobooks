import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SourceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    key: str
    owner: Literal["identity", "billing"]
    contract_version: int | None
    status: Literal["unavailable", "ready", "stale"]


class CapabilityStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    key: str
    phase: str
    implemented: bool


class CatalogReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: uuid.UUID
    company_verified: bool = False
    status: Literal["not_ready"] = "not_ready"
    sources: list[SourceStatus]
    capabilities: list[CapabilityStatus]
