"""Release publication input and the read projections that report enforcement.

docs/catalog-warehouses.md §5. Every field of a release is stated by a reviewer or derived
from the company's own reviewed rows; nothing here is a quantity, and nothing here claims a
consumer is enforcing anything — that is the acknowledgement's job alone.
"""

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from catalog.domain.policy_release import MAX_REASON_LENGTH
from catalog.schemas.pricing import PublicationInput


class PolicyReleaseInput(PublicationInput):
    """Publish the company's stock-location policy as one numbered, dated release.

    There is no manifest in the body. A caller that could state which locations a release
    covers could publish a release that omits the one location it changed, and a consumer
    reading it would enforce a policy the company never approved. Catalog builds the manifest
    from its own reviewed rows and records the digest.

    ``expected_generation`` and ``expected_source_version`` come from the configuration read,
    as they do for a defaults change: the release describes the company the reviewer looked at,
    or it is refused.
    """

    #: When it takes force. Never behind today — a release that applied retroactively would be
    #: a permission change nobody could have obeyed (``domain/policy_release``).
    effective_date: dt.date
    change_reason: str = Field(min_length=1, max_length=MAX_REASON_LENGTH)


class AcknowledgementDetail(BaseModel):
    """One trusted consumer's claim about one aggregate, as a reader sees it.

    ``reason_code`` is from a closed vocabulary and carries no quantity, party or document
    identity: a Catalog reader learns what to fix, not what Billing holds.
    """

    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    consumer: str
    aggregate: str
    aggregate_id: uuid.UUID
    release_revision: int
    enforced_revision: int
    result: str
    reason_code: str | None = None
    acknowledged_at: dt.datetime


class ReleaseListItem(BaseModel):
    """A release in the history list. Lean by design (docs/api-conventions.md).

    ``delivery_state`` is computed from the acknowledgements, never stored: Catalog can say
    what it published, and only a consumer can say what is enforced.
    """

    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    revision: int
    delivery_state: str
    effective_date: dt.date | None = None
    published_at: dt.datetime | None = None
    location_count: int | None = None
    default_count: int | None = None


class ReleaseDetail(ReleaseListItem):
    """One release in full, with the acknowledgements that speak about it.

    Everything but the identity and the delivery state is optional and unset when a field
    policy denies reading it: a read deny holds in projections, not only in forms
    (docs/field-permissions.md §6).
    """

    change_reason: str | None = None
    policy_generation: int | None = None
    source_version: int | None = None
    manifest_digest: str | None = None
    row_version: int | None = None
    acknowledgements: list[AcknowledgementDetail] = Field(default_factory=list)


class ReleaseView(BaseModel):
    """The release in force, and the ones before it.

    History is returned rather than summarized, for the same reason an operation policy's is:
    a reader investigating what a consumer enforced last week needs the release that was in
    force then, not today's.
    """

    model_config = ConfigDict(extra="forbid")
    policy_generation: int
    source_version: int
    current: ReleaseDetail | None = None
    history: list[ReleaseListItem] = Field(default_factory=list)
