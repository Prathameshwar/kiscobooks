"""Explicit readiness for native commercial definition authoring."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DefinitionAuthoringContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: uuid.UUID
    enabled: bool
    operational_ready: Literal[False] = False
