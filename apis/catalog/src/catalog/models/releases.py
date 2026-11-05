"""Numbered policy releases and the trusted acknowledgements that make one enforced.

docs/catalog-warehouses.md §5. Two tables, and the split is the whole point: Catalog owns what
it *published*, a consumer owns what it *enforces*, and no row lets one write the other's half.

* ``catalog_policy_release`` — one numbered, dated release per company, carrying a bounded
  manifest summary and the digest of the location facts it asks consumers to enforce. Nothing
  in it says the policy is in effect anywhere.
* ``catalog_policy_consumer_ack`` — one row per (consumer, aggregate, release) saying what that
  consumer enforces. Written only by the source-only ingestion worker from a signed event; no
  HTTP route can create one, because a client asserting "Billing applied this" would make
  ``APPLIED`` mean nothing.

There is no stored ``effective_to`` or ``superseded_by``. The successor release is what closes
a predecessor, so the interval is derived from ``revision`` and ``effective_date`` rather than
maintained — one lifecycle mechanism per entity (CLAUDE.md §6.11), and no window to fall out
of step with the numbering.
"""

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog.domain.policy_release import (
    AGGREGATES,
    CONSUMERS,
    MANIFEST_LIMIT,
    REASON_CODES,
    RELEASE_AGGREGATE,
    RESULTS,
)
from catalog.models.pricing import PricingRow
from catalog.models.tax import reference, scope


def _in_list(column: str, values: frozenset[str]) -> str:
    """A bounded vocabulary as SQL, generated from the domain's own set so the two cannot drift.

    The vocabularies are closed in the schema as well as in ``domain/policy_release.py``. The
    domain check is what a caller sees; this one is what survives a bad migration, a manual
    fix-up or a future writer that forgets the domain call.
    """
    return column + " IN (" + ", ".join("'" + value + "'" for value in sorted(values)) + ")"


class CatalogPolicyRelease(PricingRow):
    """One numbered, dated release of a company's stock-location policy.

    A release is a *delivery boundary*, not a new authority: every flag in it was already
    reviewed and published on its location's own revision. What the release adds is a single
    thing a consumer can name — "I enforce release 7" — and a digest it can check that claim
    against.

    Immutable once written. There is no draft and no edit: publishing again produces the next
    revision, so "what did release 7 say" has one answer forever.
    """

    __tablename__ = "catalog_policy_release"
    __table_args__ = (
        *scope("catalog_policy_release"),
        UniqueConstraint(
            "tenant_id", "company_id", "revision", name="uq_catalog_policy_release_number"
        ),
        # Ordered by revision, not by date: two releases may share a date, and the number is
        # what decides which one supersedes the other.
        Index(
            "ix_catalog_policy_release_order",
            "tenant_id",
            "company_id",
            "revision",
            "effective_date",
            "id",
        ),
        # Short local names, as elsewhere in Catalog: the table already prefixes them, and the
        # usual "<table>_<rule>" form would exceed MySQL's 64-character identifier limit.
        CheckConstraint("revision >= 1", name="revision"),
        CheckConstraint("policy_generation >= 1 AND source_version > 0", name="expectations"),
        CheckConstraint(
            f"location_count BETWEEN 1 AND {MANIFEST_LIMIT} AND default_count BETWEEN 0 AND 4",
            name="manifest",
        ),
        MARIADB_TABLE_ARGS,
    )
    #: One per company, from 1, never reused. This is the number a consumer acknowledges.
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The business date the release takes force on, never before it was published: a release
    #: that applied retroactively would be a permission change nobody could have obeyed (§5).
    effective_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    #: When the release was published. A separate fact from ``effective_date``: one is the
    #: instant of the reviewed action, the other the day the company means it to apply.
    published_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    #: The ``catalog_policy_state`` generation and Identity checkpoint the manifest was built
    #: from. Both are recorded, not just checked: a consumer investigating a disagreement needs
    #: to know which picture of the company the release described.
    policy_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Typed counts rather than a JSON manifest. A count can be constrained and compared; a
    #: JSON blob would be an unindexable column in every list projection that reads this row
    #: (docs/api-conventions.md), and the locations themselves are still queryable rows.
    location_count: Mapped[int] = mapped_column(Integer, nullable=False)
    default_count: Mapped[int] = mapped_column(Integer, nullable=False)
    #: SHA-256 over the canonical manifest: every active location, its reviewed revision and
    #: allowed operations, plus the four company activity defaults. A consumer that computed a
    #: different digest read a different release.
    manifest_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class CatalogPolicyConsumerAck(PricingRow):
    """What one trusted consumer says it enforces, for one aggregate, from one release.

    One row per ``(consumer, aggregate, aggregate_id, release)``, advanced in place rather than
    appended: the question this table answers is *what is enforced now*, and a growing log of
    superseded claims would make that a scan. The audit trail is where the history lives — the
    row records ``create`` on arrival and ``update`` when a consumer advances it.

    ``enforced_revision`` is counted in the series its ``aggregate`` names, never a mix: the
    release's own number for ``CATALOG_POLICY_RELEASE``, and the location's operation-policy
    revision for the two location aggregates
    (``domain/policy_release.AGGREGATES``).
    """

    __tablename__ = "catalog_policy_consumer_ack"
    __table_args__ = (
        *scope("catalog_policy_consumer_ack"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "consumer",
            "aggregate",
            "aggregate_id",
            "release_id",
            name="uq_catalog_policy_ack_subject",
        ),
        reference("catalog_policy_ack", "release_id", "catalog_policy_release"),
        # Answers "what does this consumer enforce for that location, most recently" without
        # a scan: the delivery state of every revision on a location's policy read.
        Index(
            "ix_catalog_policy_ack_aggregate",
            "tenant_id",
            "company_id",
            "aggregate",
            "aggregate_id",
            "release_revision",
        ),
        # Short local names, as on the release above.
        CheckConstraint(
            "release_revision >= 1 AND enforced_revision >= 1",
            name="revision",
        ),
        CheckConstraint(_in_list("consumer", CONSUMERS), name="consumer"),
        CheckConstraint(_in_list("aggregate", AGGREGATES), name="aggregate"),
        CheckConstraint(_in_list("result", RESULTS), name="result"),
        # A release-level claim is about the release itself, so its subject *is* the release.
        # Held in the schema because the uniqueness above depends on it: were the two allowed to
        # differ, one consumer could hold several conflicting claims about one release and
        # "what does Billing enforce" would have no single answer.
        CheckConstraint(
            f"aggregate <> '{RELEASE_AGGREGATE}' OR aggregate_id = release_id", name="subject"
        ),
        # A refusal says why, from the closed list; an acceptance says nothing. The second half
        # matters as much: a stale reason attached to an enforced policy misleads every reader.
        CheckConstraint(
            "(result = 'APPLIED' AND reason_code IS NULL) OR "
            "(reason_code IS NOT NULL AND " + _in_list("reason_code", REASON_CODES) + ")",
            name="verdict",
        ),
        MARIADB_TABLE_ARGS,
    )
    #: The release this claim was made against, by id and by number. The number is stored as
    #: well as the reference because the retirement fence compares it with the release in force
    #: on a hot path, and reading the parent row for one integer would be a join per location.
    release_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    release_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Which trusted service is speaking. Verified from the signed envelope, never from the
    #: payload: a message that could name its own consumer could impersonate one.
    consumer: Mapped[str] = mapped_column(String(20), nullable=False)
    #: What the claim is about, and the thing it is about. ``aggregate_id`` is the release id,
    #: or a location id for the two location aggregates.
    aggregate: Mapped[str] = mapped_column(String(30), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: The revision of that aggregate the consumer enforces. Advanced only upward: an older
    #: acknowledgement cannot regress current enforcement
    #: (``domain/policy_release.acknowledgement_action``).
    enforced_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Why a consumer refused, from the closed list. Never free text: this reaches a Catalog
    #: reader, and a Billing quantity or document number must not travel with it.
    reason_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    #: The signed source event this row was last written from, for tracing a claim back to the
    #: message that made it. The platform inbox is what dedupes redelivery; this is evidence.
    source_message_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    acknowledged_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)


RELEASE_MODELS = (CatalogPolicyRelease, CatalogPolicyConsumerAck)
