"""The signed acknowledgement contract a trusted consumer publishes to Catalog.

docs/catalog-warehouses.md §5. Separate from ``schemas/releases.py`` on purpose: that module
holds what an HTTP reader sees, and this one is a versioned inter-service message contract that
changes on its own schedule and has no route at all.

**There is no ``consumer`` field, and that omission is the security property.** Which service is
speaking comes from the signed envelope's verified key, never from the body. A payload that could
name its own consumer could name a different one, and ``APPLIED`` — the single fact that lets
Catalog stop reporting a policy as pending — would become a claim anyone on the exchange can
make (CLAUDE.md §5.12).
"""

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from catalog.domain.policy_release import AGGREGATES, REASON_CODES, RESULTS

#: Contract version, carried in the envelope's ``schema_version`` and pinned by the worker. A
#: consumer speaking a version Catalog does not know is dead-lettered rather than guessed at.
CONTRACT_VERSION = 1
#: The contract's closed vocabularies, by the field that carries each one. The field name is
#: also the term's name in the refusal message, so "reason_code" reads back as "reason code".
VOCABULARIES: dict[str, frozenset[str]] = {
    "aggregate": AGGREGATES,
    "result": RESULTS,
    "reason_code": REASON_CODES,
}


class AcknowledgementEvent(BaseModel):
    """One consumer's claim about one aggregate of one release.

    Every field is checked again on ingestion against Catalog's own rows: the release must be one
    Catalog published, at the revision named, and a location aggregate must name a real location
    and a revision Catalog actually wrote. A trusted source is trusted about *its* half —
    whether it enforces something — not about what Catalog published.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: uuid.UUID
    company_id: uuid.UUID
    #: The release the claim is about, by id and by number. Both travel so a mismatch is a
    #: detectable error rather than a silent re-pointing at whatever release holds that id.
    release_id: uuid.UUID
    release_revision: int = Field(strict=True, ge=1, le=2**31 - 1)
    aggregate: str = Field(min_length=1, max_length=30)
    aggregate_id: uuid.UUID
    enforced_revision: int = Field(strict=True, ge=1, le=2**31 - 1)
    result: str = Field(min_length=1, max_length=10)
    reason_code: str | None = Field(default=None, max_length=30)
    acknowledged_at: dt.datetime

    @field_validator("aggregate", "result", "reason_code")
    @classmethod
    def known_term(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Every closed vocabulary on the contract, checked by one rule.

        Keyed off the domain's own sets rather than restated here: a term added there arrives
        checked, and a fourth vocabulary field added to this model without an entry in
        ``VOCABULARIES`` fails loudly instead of passing unchecked.
        """
        if value is not None and value not in VOCABULARIES[str(info.field_name)]:
            raise ValueError(f"unknown acknowledgement {str(info.field_name).replace('_', ' ')}")
        return value

    def model_post_init(self, context: Any, /) -> None:
        if self.acknowledged_at.tzinfo is None:
            raise ValueError("acknowledged_at must be timezone-aware")
