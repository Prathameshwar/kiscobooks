"""Numbered policy releases, and the acknowledgements that make one *enforced*.

docs/catalog-warehouses.md §5. Pure: no session, no ORM, no clock, no quantity. The caller
loads the rows and authorizes the actor; this module decides what a release may say and what
an acknowledgement is allowed to change.

Four rules carry the weight, and each is the opposite of the convenient behaviour:

* **Catalog never claims its own policy is enforced.** A release is `PENDING` until a trusted
  consumer acknowledges *that* release; publishing one is not evidence that anything obeys it.
* **An older acknowledgement cannot regress current enforcement.** Brokers redeliver and
  reorder, so an ack naming an earlier revision is a no-op rather than a downgrade.
* **At one revision a claim may only weaken.** A consumer may reject what it previously
  applied — that makes Catalog's answer more honest. Turning a rejection back into `APPLIED`
  needs a new enforced revision, so "it works now" is never asserted without new evidence.
* **A release states a bounded manifest, not "everything".** The digest is over exactly the
  location facts a consumer must enforce, so a consumer can tell whether it read the same
  release Catalog published.

The reason vocabulary is closed and carries no quantity, party or document identity: a
rejection travels to a Catalog reader, and "why can this location not be retired" must be
answerable without leaking what Billing holds (docs/audit.md §5.2, CLAUDE.md §5.11).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from billing_platform.errors import ConflictError, ValidationFailedError
from voucher_execution.stock_policy_manifest import policy_manifest_digest

from catalog.domain.warehouse_resolution import (
    ACTIVITY_DEFAULTS,
    APPLIED,
    PENDING,
    REJECTED,
    Acknowledgement,
    delivery_state,
)
from catalog.domain.warehouses import OPERATION_FLAGS

#: Services allowed to acknowledge a Catalog policy release. Only Billing owns the stock,
#: reservation and pending-document facts behind the location guards, so only Billing can say
#: a location policy is being enforced (docs/catalog-inventory-integration.md §2).
CONSUMERS: Final[frozenset[str]] = frozenset({"billing"})

#: What one acknowledgement is *about*. Each names the revision series its
#: ``enforced_revision`` is counted in, so one column never means two different things:
#:
#: * ``CATALOG_POLICY_RELEASE`` — the release itself, numbered by ``revision``. This is the
#:   release-level ack: the consumer read this manifest and enforces it, activity defaults
#:   included.
#: * ``WAREHOUSE_OPERATION_POLICY`` — one location, numbered by that location's operation
#:   policy revision.
#: * ``WAREHOUSE_RETIREMENT`` — one location's retirement clearance, numbered by the
#:   operation policy revision the consumer checked its stock facts against.
RELEASE_AGGREGATE: Final[str] = "CATALOG_POLICY_RELEASE"
OPERATION_POLICY_AGGREGATE: Final[str] = "WAREHOUSE_OPERATION_POLICY"
RETIREMENT_AGGREGATE: Final[str] = "WAREHOUSE_RETIREMENT"
AGGREGATES: Final[frozenset[str]] = frozenset(
    {RELEASE_AGGREGATE, OPERATION_POLICY_AGGREGATE, RETIREMENT_AGGREGATE}
)

#: A consumer either enforces what the release says or refuses it. There is no third verdict:
#: "working on it" is the absence of an acknowledgement, which is already ``PENDING``.
RESULTS: Final[frozenset[str]] = frozenset({APPLIED, REJECTED})

#: Why a consumer refused, from a closed list. No quantity, no party, no document number —
#: a Catalog reader learns what to fix, not what Billing holds.
REASON_CODES: Final[frozenset[str]] = frozenset(
    {
        "STOCK_ON_HAND",
        "RESERVED_STOCK",
        "PENDING_DOCUMENT",
        "OPEN_TRANSFER",
        "OPEN_COUNT",
        "UNKNOWN_LOCATION",
        "POLICY_CONFLICT",
        "UNSUPPORTED_OPERATION",
        "SOURCE_UNAVAILABLE",
    }
)

#: How many locations one release may carry. A release is a delivery contract, so it fails
#: loudly rather than becoming an unbounded projection (docs/api-conventions.md). Well above
#: any real company's store count, and below anything that would make the digest a scan.
MANIFEST_LIMIT: Final[int] = 500

#: How far ahead a release may be dated. A year and a day covers a fiscal-year rollout;
#: beyond that the reviewer is scheduling something nobody will remember approving.
MAX_FUTURE_DAYS: Final[int] = 366

#: Longest reason a publisher may record, matching every other ``change_reason`` in Catalog.
MAX_REASON_LENGTH: Final[int] = 500


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """One location in a release: its identity, its reviewed revision, its allowed operations.

    The flags travel in the digest as well as the revision number. A consumer that read
    revision 4 must be able to tell that *this* revision 4 is the one Catalog published, and
    a revision number alone could not distinguish a republished set of flags.
    """

    warehouse_id: uuid.UUID
    revision: int
    flags: frozenset[str]

    def __post_init__(self) -> None:
        if self.warehouse_id.int == 0:
            raise ValidationFailedError("a release entry names a real stock location")
        if self.revision < 1:
            raise ValidationFailedError("a release entry names a published policy revision")
        if not self.flags <= frozenset(OPERATION_FLAGS):
            raise ValidationFailedError("unknown stock-location operation flag")


def manifest_digest(
    entries: Sequence[ManifestEntry], defaults: Mapping[str, uuid.UUID | None]
) -> str:
    """A stable digest of exactly the location facts this release asks a consumer to enforce.

    Canonical and order-independent: entries sort by location id and the defaults by column
    name, so two publications of the same policy state produce the same digest whatever order
    the rows came back in. That is what lets a consumer answer "I enforce release 7" and a
    Catalog reader verify the claim was about the release Catalog actually wrote.

    Bounded on the way in. An unbounded manifest would be an unbounded query dressed as a
    receipt, and the loud failure is the documented outcome.
    """
    if len(entries) > MANIFEST_LIMIT:
        raise ConflictError("this company's stock-location set exceeds the release bound")
    keys = {entry.warehouse_id for entry in entries}
    if len(keys) != len(entries):
        raise ValidationFailedError("a release names each stock location once")
    unknown = set(defaults) - set(ACTIVITY_DEFAULTS)
    if unknown:
        raise ValidationFailedError("unknown company activity default")
    return policy_manifest_digest(entries, defaults, ACTIVITY_DEFAULTS)


def assert_effective_date(
    effective_date: dt.date, *, today: dt.date, predecessor: dt.date | None
) -> None:
    """When a release may take force: not behind, not before its predecessor, not far ahead.

    Backdating is refused for the same reason an operation policy's window is server-assigned
    (§5): a release that took force before it was published would be a permission change
    nobody could have obeyed, and every consumer reading it would already be late.

    Equal dates are allowed. Two releases on one day is an ordinary correction, and
    ``revision`` — not the date — is what orders them.
    """
    if effective_date < today:
        raise ValidationFailedError("a policy release cannot take force before it is published")
    if effective_date > today + dt.timedelta(days=MAX_FUTURE_DAYS):
        raise ValidationFailedError("a policy release is dated within the coming year")
    if predecessor is not None and effective_date < predecessor:
        raise ConflictError("a policy release cannot take force before the one it supersedes")


def combined_state(revision: int, claims: Mapping[str, Acknowledgement]) -> str:
    """One delivery state for ``revision`` from every trusted consumer's latest claim.

    Unanimity for ``APPLIED``, a single veto for ``REJECTED``. A policy that only one of two
    consumers enforces is not enforced, and there is deliberately no partial state to report:
    the reader is asking "is this in effect", and "half" is the same answer as "no" with a
    false reassurance attached.
    """
    if revision < 1:
        raise ValidationFailedError("a delivery state describes a published revision")
    if set(claims) - CONSUMERS:
        raise ValidationFailedError("unknown policy release consumer")
    states = {consumer: delivery_state(revision, claim) for consumer, claim in claims.items()}
    if REJECTED in states.values():
        return REJECTED
    if CONSUMERS <= {consumer for consumer, state in states.items() if state == APPLIED}:
        return APPLIED
    return PENDING


def refusal_message(reason_code: str | None) -> str:
    """How a consumer's "no" is worded to the caller, with its safe reason code.

    One wording for the two places that report it: the fence, which keeps a rejection a 409
    while every other missing clearance is a 503, and ``assert_clearance``, which reaches the
    same conclusion from the row itself. A reason code is one of a closed set, so it is safe
    to return; nothing else from the row is.
    """
    return "a consumer refused this retirement: " + str(reason_code)


def assert_reason(result: str, reason_code: str | None) -> None:
    """A refusal says why, from the closed list; an acceptance says nothing.

    Both halves matter. A rejection with no reason is a dead end for the reader who has to
    act on it, and an acceptance carrying one would leave a stale explanation attached to a
    policy that is being enforced.
    """
    if result not in RESULTS:
        raise ValidationFailedError("unknown acknowledgement result")
    if result == REJECTED:
        if reason_code is None:
            raise ValidationFailedError("a rejected acknowledgement states its reason code")
        if reason_code not in REASON_CODES:
            raise ValidationFailedError("unknown acknowledgement reason code")
    elif reason_code is not None:
        raise ValidationFailedError("an applied acknowledgement carries no reason code")


def acknowledgement_action(
    *,
    stored_revision: int | None,
    stored_result: str | None,
    incoming_revision: int,
    incoming_result: str,
) -> Literal["apply", "ignore"]:
    """Whether an arriving acknowledgement changes what Catalog reports, or is a no-op.

    Never a conflict. Redelivery and reordering are ordinary broker behaviour, so an
    acknowledgement Catalog has already superseded is dropped rather than dead-lettered —
    the platform inbox dedupes the identical message, and this decides the rest.

    At an equal revision a claim may only *weaken*: a consumer may reject what it previously
    applied, and turning that back into ``APPLIED`` needs a new enforced revision. Otherwise
    "it works now" could be asserted about the very revision that was found broken, with
    nothing new behind it.
    """
    if incoming_revision < 1:
        raise ValidationFailedError("an acknowledgement names a published revision")
    if incoming_result not in RESULTS:
        raise ValidationFailedError("unknown acknowledgement result")
    if stored_revision is None:
        return "apply"
    if stored_result not in RESULTS:
        raise ValidationFailedError("unknown acknowledgement result")
    if incoming_revision > stored_revision:
        return "apply"
    if incoming_revision < stored_revision:
        return "ignore"
    return "apply" if stored_result == APPLIED and incoming_result == REJECTED else "ignore"


def assert_clearance(
    *,
    aggregate: str,
    result: str,
    reason_code: str | None,
    acknowledged_release: int,
    in_force_release: int,
    enforced_revision: int,
    policy_revision: int,
) -> None:
    """Is this acknowledgement a usable clearance to retire the location it names (§5)?

    Every condition is a refusal to *infer* safety:

    * the ack must be a retirement clearance, not a policy ack that happens to be positive;
    * it must be against the release in force, so a clearance granted before the company
      changed its locations does not authorize a retirement now;
    * it must name the location's own open operation-policy revision, so a clearance checked
      against an older policy does not carry to a newer one;
    * a rejection stays a rejection, and its reason code travels to the caller.

    Raising rather than returning a boolean is deliberate: each failure has a different
    answer, and a caller reading one flag would collapse them into "not allowed".
    """
    if aggregate != RETIREMENT_AGGREGATE:
        raise ConflictError("no consumer has cleared this stock location for retirement")
    assert_reason(result, reason_code)
    if result == REJECTED:
        raise ConflictError(refusal_message(reason_code))
    if acknowledged_release != in_force_release:
        raise ConflictError("the retirement clearance predates the policy release in force")
    if enforced_revision != policy_revision:
        raise ConflictError("the retirement clearance predates this location's operation policy")
