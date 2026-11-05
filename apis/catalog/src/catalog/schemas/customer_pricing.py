"""Customer-pricing effective-read schemas.

Read schema only for v1 — authoring `price_level_assignment` and its scope
happens through the seed fixture and (v1.1) through explicit routes with
`customer_pricing.manage`/`.publish`.
"""

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class CustomerPricingChain(BaseModel):
    """One step of the audit chain returned by :func:`resolve`."""

    model_config = ConfigDict(extra="forbid")
    kind: str  # party / customer_type / company
    ref: str


class CustomerPricingEffective(BaseModel):
    """The effective buyer-level read for a quote or invoice price lookup."""

    model_config = ConfigDict(extra="forbid")
    party_id: uuid.UUID
    as_of: dt.date
    price_level_id: uuid.UUID
    chain: tuple[CustomerPricingChain, ...]
