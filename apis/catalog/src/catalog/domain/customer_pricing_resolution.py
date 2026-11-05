"""Pure customer-pricing resolution chain.

Given a party and a posting date, return the applicable ``price_level_id`` by
walking the precedence chain **party > customer_type > company**. Every input
is passed in from the caller; this module has no session, no ORM query and no
clock. It is deterministic and directly unit-testable.

The caller is responsible for gathering the inputs from the database (the
active projection rows and the effective assignments). The refusal path is a
single :class:`CustomerPricingUnavailableError` naming the missing input, not a
silent fallback — a fallback here would let a stale projection choose a
different price level from the buyer's authoritative commercial type.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Literal


class CustomerPricingUnavailableError(RuntimeError):
    """The chain could not answer for the given inputs.

    Carries the *reason* so the caller can surface it verbatim; the caller
    decides the HTTP shape (``503 source_unavailable`` vs ``409``).
    """


@dataclass(frozen=True, slots=True)
class PartyMembership:
    """One authoritative projection row: ``party -> customer_type`` on a date range."""

    party_id: uuid.UUID
    customer_type_code: str | None
    valid_from: dt.date
    valid_to: dt.date | None
    is_active: bool
    source_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class Assignment:
    """One authored price-level assignment against a subject.

    ``subject_kind`` picks which of ``customer_ref`` / ``pricing_type_ref`` is
    non-null. The caller is expected to have already joined the assignment to
    its scope row and to pass both fields together.
    """

    subject_kind: Literal["CUSTOMER", "PRICING_TYPE"]
    customer_ref: uuid.UUID | None
    pricing_type_ref: str | None
    price_level_id: uuid.UUID
    valid_from: dt.date
    valid_to: dt.date | None
    assignment_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class Resolution:
    """Answer with its complete audit chain.

    ``chain`` names the precedence step that won (``party`` / ``customer_type``
    / ``company``) followed by the subject that matched.
    """

    price_level_id: uuid.UUID
    chain: tuple[str, ...]
    source_ids: tuple[uuid.UUID, ...] = ()


def _covers(valid_from: dt.date, valid_to: dt.date | None, on: dt.date) -> bool:
    return valid_from <= on and (valid_to is None or on <= valid_to)


def resolve(
    *,
    party_id: uuid.UUID,
    posting_date: dt.date,
    memberships: tuple[PartyMembership, ...],
    assignments: tuple[Assignment, ...],
    company_default_price_level_id: uuid.UUID | None,
) -> Resolution:
    """Walk **party > customer_type > company**.

    ``memberships`` is the ``customer_pricing_projection`` filtered to
    ``party_id``. ``assignments`` is every currently-authored assignment for
    the company. ``company_default_price_level_id`` is the company's default
    from ``company_pricing_policy``. A missing default is reported
    verbatim so a caller can distinguish a stale party from an unconfigured
    default.
    """
    # Validate source membership even when a direct assignment would win.
    active = [
        m
        for m in memberships
        if m.party_id == party_id
        and m.is_active
        and _covers(m.valid_from, m.valid_to, posting_date)
    ]
    if len(active) > 1:
        raise CustomerPricingUnavailableError(
            "party has more than one active customer-type membership on this date"
        )
    membership = active[0] if active else None
    membership_ids = (
        (membership.source_id,) if membership is not None and membership.source_id else ()
    )
    direct = [
        row for row in assignments
        if row.subject_kind == "CUSTOMER"
        and row.customer_ref == party_id
        and _covers(row.valid_from, row.valid_to, posting_date)
    ]
    if len(direct) > 1:
        raise CustomerPricingUnavailableError("party has overlapping price-level assignments")
    if direct:
        selected = direct[0]
        return Resolution(
            selected.price_level_id,
            ("party", str(party_id)),
            (*membership_ids, *((selected.assignment_id,) if selected.assignment_id else ())),
        )

    # Step 2: the party's active customer type on this date decides.
    if membership is not None and membership.customer_type_code is not None:
        matching = [
            row for row in assignments
            if row.subject_kind == "PRICING_TYPE"
            and row.pricing_type_ref == membership.customer_type_code
            and _covers(row.valid_from, row.valid_to, posting_date)
        ]
        if len(matching) > 1:
            raise CustomerPricingUnavailableError(
                "customer type has overlapping price-level assignments"
            )
        if matching:
            selected = matching[0]
            return Resolution(
                selected.price_level_id,
                ("customer_type", membership.customer_type_code),
                (*membership_ids, *((selected.assignment_id,) if selected.assignment_id else ())),
            )

    # Step 3: the company default.
    if company_default_price_level_id is None:
        raise CustomerPricingUnavailableError(
            "no company default price level; configure company_pricing_policy first"
        )
    return Resolution(
        price_level_id=company_default_price_level_id,
        chain=("company", "default"),
        source_ids=membership_ids,
    )
