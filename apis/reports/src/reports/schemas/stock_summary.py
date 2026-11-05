"""Frozen inventory readiness and scoped master choices for the stock workspace."""

import uuid

from pydantic import BaseModel, ConfigDict
from reporting_contract.inventory import Coverage


class StockReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    code: str
    name: str


class StockReferencePage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generation_id: uuid.UUID
    coverage: Coverage
    items: list[StockReference]
    next_cursor: str | None
