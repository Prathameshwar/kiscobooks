"""Internal cache generation contract; never exposed as a public API record."""

import uuid

from pydantic import Field

from identity.schemas.base import StrictModel


class ReferenceCacheGeneration(StrictModel):
    id: uuid.UUID
    key: str = Field(pattern="^global$")
    token: uuid.UUID
