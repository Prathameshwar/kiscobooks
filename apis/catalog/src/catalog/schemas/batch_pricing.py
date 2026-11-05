"""Native initial rates for a verified Accounting batch."""

import datetime as dt
import uuid

from pydantic import Field

from catalog.schemas.pricing import PublicationInput
from catalog.schemas.product_initial import InitialPrice


class BatchPricingInput(PublicationInput):
    item_id: uuid.UUID
    lot_id: uuid.UUID
    unit_revision_id: uuid.UUID
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))
    prices: list[InitialPrice] = Field(default_factory=list, max_length=65)
