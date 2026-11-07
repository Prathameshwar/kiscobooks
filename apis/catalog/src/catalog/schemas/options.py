"""Lean option projection with an explicit parent and bounded signed cursor."""

import datetime as dt
import uuid

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict


class OptionQuery(ListQuery):
    parent_id: uuid.UUID | None = None
    as_of: dt.date | None = None
    product_type_revision_id: uuid.UUID | None = None


class OptionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    code: str
    label: str
