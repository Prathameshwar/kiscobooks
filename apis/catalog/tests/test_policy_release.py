"""Release manifests, dating and acknowledgement arithmetic — no database, no framework.

docs/catalog-warehouses.md §5. The refusals are the requirement here: Catalog never reports its
own release as enforced, an older acknowledgement never regresses what is enforced, and no
clearance carries from the release or the policy revision it was granted against to a newer one.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7

from catalog.domain.policy_release import (
    CONSUMERS,
    MANIFEST_LIMIT,
    MAX_FUTURE_DAYS,
    OPERATION_POLICY_AGGREGATE,
    REASON_CODES,
    RELEASE_AGGREGATE,
    RETIREMENT_AGGREGATE,
    ManifestEntry,
    acknowledgement_action,
    assert_clearance,
    assert_effective_date,
    assert_reason,
    combined_state,
    manifest_digest,
)
from catalog.domain.warehouse_resolution import (
    ACTIVITY_DEFAULTS,
    APPLIED,
    PENDING,
    REJECTED,
    Acknowledgement,
)

TODAY = dt.date(2026, 9, 18)
SALE = frozenset({"allow_sale_issue"})
CLEARED: dict[str, uuid.UUID | None] = dict.fromkeys(ACTIVITY_DEFAULTS)


def entry(*, identity: uuid.UUID | None = None, revision: int = 1) -> ManifestEntry:
    return ManifestEntry(warehouse_id=identity or uuid7(), revision=revision, flags=SALE)


def clearance(**overrides: object) -> None:
    """The clearance that should pass, with one fact at a time replaced by the failing one."""
    assert_clearance(
        **{
            "aggregate": RETIREMENT_AGGREGATE,
            "result": APPLIED,
            "reason_code": None,
            "acknowledged_release": 7,
            "in_force_release": 7,
            "enforced_revision": 3,
            "policy_revision": 3,
            **overrides,
        }  # type: ignore[arg-type]  # one keyword table drives every branch
    )


def test_a_manifest_entry_names_a_real_location_and_a_published_revision() -> None:
    with pytest.raises(ValidationFailedError):
        ManifestEntry(warehouse_id=uuid.UUID(int=0), revision=1, flags=SALE)
    with pytest.raises(ValidationFailedError):
        ManifestEntry(warehouse_id=uuid7(), revision=0, flags=SALE)
    with pytest.raises(ValidationFailedError):
        ManifestEntry(warehouse_id=uuid7(), revision=1, flags=frozenset({"allow_teleport"}))


def test_the_digest_is_order_independent_and_covers_every_delivered_fact() -> None:
    first, second = uuid7(), uuid7()
    main = uuid7()
    defaults: dict[str, uuid.UUID | None] = dict.fromkeys(ACTIVITY_DEFAULTS, main)
    entries = [entry(identity=first), entry(identity=second)]
    assert manifest_digest(entries, defaults) == manifest_digest(
        list(reversed(entries)), dict(reversed(list(defaults.items())))
    )
    # Every fact a consumer must enforce moves the digest: the revision, the flags and each
    # activity default. A digest that ignored one would let a consumer believe it read this
    # release when it read another.
    assert manifest_digest(entries, defaults) != manifest_digest(
        [entry(identity=first, revision=2), entry(identity=second)], defaults
    )
    assert manifest_digest(entries, defaults) != manifest_digest(
        [
            ManifestEntry(warehouse_id=first, revision=1, flags=frozenset()),
            entry(identity=second),
        ],
        defaults,
    )
    assert manifest_digest(entries, defaults) != manifest_digest(entries, CLEARED)
    assert manifest_digest(entries, {**defaults, "default_sale_warehouse_id": first}) != (
        manifest_digest(entries, defaults)
    )
    # A cleared pointer is a stated fact, not a missing key: both spellings mean the same policy.
    assert manifest_digest(entries, CLEARED) == manifest_digest(entries, {})


def test_the_digest_refuses_a_duplicate_location_an_unknown_default_and_the_bound() -> None:
    shared = uuid7()
    with pytest.raises(ValidationFailedError):
        manifest_digest([entry(identity=shared), entry(identity=shared)], CLEARED)
    with pytest.raises(ValidationFailedError):
        manifest_digest([entry()], {"default_scrap_warehouse_id": uuid7()})
    assert manifest_digest([entry() for _ in range(MANIFEST_LIMIT)], CLEARED)
    with pytest.raises(ConflictError):
        manifest_digest([entry() for _ in range(MANIFEST_LIMIT + 1)], CLEARED)


def test_a_release_takes_force_ahead_of_its_publication_and_its_predecessor() -> None:
    assert_effective_date(TODAY, today=TODAY, predecessor=None)
    assert_effective_date(TODAY, today=TODAY, predecessor=TODAY)
    assert_effective_date(
        TODAY + dt.timedelta(days=MAX_FUTURE_DAYS), today=TODAY, predecessor=TODAY
    )
    with pytest.raises(ValidationFailedError):
        assert_effective_date(TODAY - dt.timedelta(days=1), today=TODAY, predecessor=None)
    with pytest.raises(ValidationFailedError):
        assert_effective_date(
            TODAY + dt.timedelta(days=MAX_FUTURE_DAYS + 1), today=TODAY, predecessor=None
        )
    # Later than today, earlier than the release it supersedes: a 409, because the reviewed
    # order and the dated order would otherwise disagree.
    with pytest.raises(ConflictError):
        assert_effective_date(
            TODAY + dt.timedelta(days=1), today=TODAY, predecessor=TODAY + dt.timedelta(days=2)
        )


def test_a_release_is_pending_until_every_trusted_consumer_enforces_that_revision() -> None:
    assert combined_state(4, {}) == PENDING
    assert combined_state(4, {"billing": Acknowledgement(revision=3, accepted=True)}) == PENDING
    assert combined_state(4, {"billing": Acknowledgement(revision=4, accepted=True)}) == APPLIED
    assert combined_state(4, {"billing": Acknowledgement(revision=5, accepted=True)}) == APPLIED
    assert combined_state(4, {"billing": Acknowledgement(revision=4, accepted=False)}) == REJECTED
    # Unanimity, checked against the catalogue rather than against however many claims arrived.
    assert CONSUMERS == frozenset({"billing"})
    with pytest.raises(ValidationFailedError):
        combined_state(4, {"reports": Acknowledgement(revision=4, accepted=True)})
    with pytest.raises(ValidationFailedError):
        combined_state(0, {})


def test_a_refusal_states_a_closed_reason_and_an_acceptance_states_none() -> None:
    assert_reason(APPLIED, None)
    for code in sorted(REASON_CODES):
        assert_reason(REJECTED, code)
    with pytest.raises(ValidationFailedError):
        assert_reason(APPLIED, "STOCK_ON_HAND")
    with pytest.raises(ValidationFailedError):
        assert_reason(REJECTED, None)
    with pytest.raises(ValidationFailedError):
        assert_reason(REJECTED, "TOO_MUCH_STOCK")
    with pytest.raises(ValidationFailedError):
        assert_reason("WORKING_ON_IT", None)


def test_an_acknowledgement_advances_or_weakens_and_never_regresses() -> None:
    def action(stored: tuple[int, str] | None, incoming_revision: int, incoming_result: str) -> str:
        return acknowledgement_action(
            stored_revision=None if stored is None else stored[0],
            stored_result=None if stored is None else stored[1],
            incoming_revision=incoming_revision,
            incoming_result=incoming_result,
        )

    assert action(None, 1, APPLIED) == "apply"
    assert action(None, 1, REJECTED) == "apply"
    assert action((2, APPLIED), 3, APPLIED) == "apply"
    assert action((2, APPLIED), 3, REJECTED) == "apply"
    # Redelivered and reordered claims are ordinary broker behaviour, so they are dropped.
    assert action((3, APPLIED), 2, REJECTED) == "ignore"
    assert action((3, APPLIED), 3, APPLIED) == "ignore"
    assert action((3, REJECTED), 3, REJECTED) == "ignore"
    # At one revision a claim may only weaken: "it works now" needs new evidence.
    assert action((3, APPLIED), 3, REJECTED) == "apply"
    assert action((3, REJECTED), 3, APPLIED) == "ignore"
    with pytest.raises(ValidationFailedError):
        action(None, 0, APPLIED)
    with pytest.raises(ValidationFailedError):
        action(None, 1, "MAYBE")
    with pytest.raises(ValidationFailedError):
        action((3, "MAYBE"), 4, APPLIED)


def test_a_clearance_carries_no_further_than_the_release_and_policy_it_was_granted_against() -> (
    None
):
    clearance()
    for aggregate in (RELEASE_AGGREGATE, OPERATION_POLICY_AGGREGATE):
        with pytest.raises(ConflictError, match="cleared this stock location"):
            clearance(aggregate=aggregate)
    with pytest.raises(ConflictError, match="STOCK_ON_HAND"):
        clearance(result=REJECTED, reason_code="STOCK_ON_HAND")
    with pytest.raises(ValidationFailedError):
        clearance(reason_code="STOCK_ON_HAND")
    with pytest.raises(ConflictError, match="predates the policy release"):
        clearance(acknowledged_release=6)
    # A clearance granted against a *newer* release is refused too: it was not checked against
    # the policy operating today, so it is evidence about something else.
    with pytest.raises(ConflictError, match="predates the policy release"):
        clearance(acknowledged_release=8)
    with pytest.raises(ConflictError, match="predates this location's operation policy"):
        clearance(enforced_revision=2)
