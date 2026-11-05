"""Which location an operation uses, and whether that location may perform it.

docs/catalog-warehouses.md §2 and §3. Pure: no session, no ORM, no clock, no quantity. The
caller loads and authorizes the candidate locations; this module decides among them.

Three rules carry the weight, and each is the opposite of the convenient behaviour:

* **A configured default that cannot serve is an error, not permission to keep looking.**
  Falling through to Main would put stock somewhere the company deliberately stopped
  using, and nothing on the document would record the substitution (§3).
* **An activity blocked even at Main resolves to no eligible location** — never a
  re-enabled flag, never an unrelated store (§2).
* **The operation kind comes from the native domain handler, never the caller.** A caller
  that could name its own kind would relabel a sale issue as an adjustment and route
  around the one flag it lacks (§2).

Nothing here reads the revision's validity window. These are live controls resolved at
operation time: the caller passes the revision in force *now*, and a backdated posting
date cannot reach back for a permission that has since been withdrawn (§5).
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Final

from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)

from catalog.domain.warehouses import (
    OPERATION_FLAGS,
    WAREHOUSE_KINDS,
    assert_selectable,
)

#: Operation kind -> the one flag that governs it. Sale and purchase are independent in
#: both directions, and neither implies transfer or return: the map is deliberately flat
#: so no operation can be enabled as a side effect of another (§2).
OPERATIONS: Final[Mapping[str, str]] = {
    "SALE_ISSUE": "allow_sale_issue",
    "PURCHASE_RECEIPT": "allow_purchase_receipt",
    "TRANSFER_IN": "allow_transfer_in",
    "TRANSFER_OUT": "allow_transfer_out",
    "CUSTOMER_RETURN_RECEIPT": "allow_customer_return_receipt",
    "SUPPLIER_RETURN_ISSUE": "allow_supplier_return_issue",
    "OPENING_STOCK": "allow_opening_stock",
    "ADJUSTMENT": "allow_adjustment",
}

#: Company activity default -> the operation it is a default *for*. A pointer is validated
#: against its own operation, so a location that cannot issue sales cannot become the sale
#: default and fail later, on a document (§3).
ACTIVITY_DEFAULTS: Final[Mapping[str, str]] = {
    "default_sale_warehouse_id": "SALE_ISSUE",
    "default_purchase_warehouse_id": "PURCHASE_RECEIPT",
    "default_customer_return_warehouse_id": "CUSTOMER_RETURN_RECEIPT",
    "default_opening_warehouse_id": "OPENING_STOCK",
}

#: Where the resolved location came from, recorded on the allocation so a reader can tell
#: an explicit choice from a fallback without re-running resolution.
EXPLICIT: Final[str] = "EXPLICIT"
SKU_DEFAULT: Final[str] = "SKU_DEFAULT"
COMPANY_DEFAULT: Final[str] = "COMPANY_DEFAULT"
MAIN: Final[str] = "MAIN"
ORIGINS: Final[frozenset[str]] = frozenset({EXPLICIT, SKU_DEFAULT, COMPANY_DEFAULT, MAIN})

#: Delivery state of a published revision (§5). ``APPLIED`` is not something Catalog can
#: assert about itself: it means a consumer acknowledged the revision, so a fresh publish
#: reports ``PENDING`` until that acknowledgement arrives.
PENDING: Final[str] = "PENDING"
APPLIED: Final[str] = "APPLIED"
REJECTED: Final[str] = "REJECTED"


class NoEligibleLocationError(ConflictError):
    """The selected location cannot perform the operation, and nothing substitutes for it.

    409 rather than 403: no role lifts it, and it is not an authorization outcome, so it
    must not land in the permission-denial audit signal.
    """


@dataclass(frozen=True, slots=True)
class Location:
    """One candidate, as the caller already knows it.

    ``authorized`` is the caller's object-level scope decision, made against the actor
    before resolution; this module only refuses to ignore it. ``revision`` is ``None`` when
    the location has no published operation policy, and an absent policy allows nothing —
    permissions are never inferred from a location's name or kind (§2).
    """

    id: uuid.UUID
    kind: str
    is_main: bool
    is_active: bool
    authorized: bool
    revision: int | None
    flags: frozenset[str]

    def __post_init__(self) -> None:
        if self.id.int == 0 or self.kind not in WAREHOUSE_KINDS:
            raise ValidationFailedError("invalid stock-location identity or kind")
        if self.revision is not None and self.revision < 1:
            raise ValidationFailedError("a published operation policy is numbered from 1")
        if not self.flags <= frozenset(OPERATION_FLAGS):
            raise ValidationFailedError("unknown stock-location operation flag")
        if self.revision is None and self.flags:
            raise ValidationFailedError("operation flags require a published policy revision")

    def allows(self, operation: str) -> bool:
        if operation not in OPERATIONS:
            raise ValidationFailedError("unknown stock operation")
        return OPERATIONS[operation] in self.flags


@dataclass(frozen=True, slots=True)
class Allocation:
    """The decision. ``revision`` pins which policy permitted it, for the audit reader."""

    warehouse_id: uuid.UUID
    revision: int
    origin: str

    def __post_init__(self) -> None:
        if self.warehouse_id.int == 0 or self.revision < 1 or self.origin not in ORIGINS:
            raise ValidationFailedError("invalid stock-location allocation")


@dataclass(frozen=True, slots=True)
class Acknowledgement:
    """A consumer's verdict on a published revision, from Phase 6's acknowledgement table."""

    revision: int
    accepted: bool

    def __post_init__(self) -> None:
        if self.revision < 1:
            raise ValidationFailedError("an acknowledgement names a published revision")


def allowed_flags(values: Mapping[str, bool]) -> frozenset[str]:
    """The set form of a policy row's eight booleans, rejecting any name that is not one."""
    unknown = set(values) - set(OPERATION_FLAGS)
    if unknown:
        raise ValidationFailedError("unknown stock-location operation flag")
    return frozenset(flag for flag in OPERATION_FLAGS if values.get(flag, False))


def delivery_state(revision: int, acknowledgement: Acknowledgement | None) -> str:
    """``PENDING`` until a consumer has acknowledged *this* revision (§5).

    An acknowledgement of an older revision leaves the newer one pending: the enforced
    policy is the one the consumer confirmed, not the one Catalog most recently wrote.
    """
    if acknowledgement is None or acknowledgement.revision < revision:
        return PENDING
    return APPLIED if acknowledgement.accepted else REJECTED


def serving_revision(
    location: Location,
    *,
    operation: str,
    features: Collection[str],
    origin: str,
) -> int:
    """The revision that permits ``operation`` here, or the reason it is not permitted.

    Ordered as §3 lists the failure causes, and the order is deliberate: authorization
    first, so an actor without scope for the location learns nothing about how it is
    configured, and the flag check last, so a denied operation is reported as a denied
    operation rather than as a missing feature.

    Authorization is a 403 only when the caller *named* the location. When a stored default
    points at a location this actor may not use, that is the company's configuration being
    unusable here — 409, and still not permission to fall through to another location.
    """
    if operation not in OPERATIONS:
        raise ValidationFailedError("unknown stock operation")
    if origin not in ORIGINS:
        raise ValidationFailedError("unknown stock-location allocation origin")
    if not location.authorized:
        if origin == EXPLICIT:
            raise PermissionDeniedError("that stock location is out of scope for this actor")
        raise NoEligibleLocationError(
            "the configured stock location is not available to this actor"
        )
    assert_selectable(features, is_main=location.is_main, kind=location.kind)
    if not location.is_active:
        raise NoEligibleLocationError("that stock location is inactive")
    if location.revision is None:
        raise NoEligibleLocationError("that stock location has no reviewed operation policy")
    if not location.allows(operation):
        raise NoEligibleLocationError("that stock location does not allow this operation")
    return location.revision


def assert_can_serve(
    location: Location,
    *,
    operation: str,
    features: Collection[str],
    origin: str = COMPANY_DEFAULT,
) -> None:
    """``serving_revision`` for callers that only need the verdict — a defaults change."""
    serving_revision(location, operation=operation, features=features, origin=origin)


def resolve(
    operation: str,
    *,
    features: Collection[str],
    candidates: Mapping[uuid.UUID, Location],
    main_warehouse_id: uuid.UUID,
    explicit: uuid.UUID | None = None,
    sku_default: uuid.UUID | None = None,
    company_default: uuid.UUID | None = None,
) -> Allocation:
    """Authorized explicit allocation > SKU default > company default > built-in Main (§3).

    The chain is a *precedence order, not a retry order*. Whichever level supplies the
    location is the level that decides, and if it cannot serve, the answer is an error.
    Only a level that is genuinely unconfigured passes the question down — which is why
    Main is reached when no activity default is configured, and not when one is configured
    badly.
    """

    def allocate(warehouse_id: uuid.UUID, origin: str) -> Allocation:
        location = candidates.get(warehouse_id)
        if location is None:
            if origin == EXPLICIT:
                raise NotFoundError("stock location not found")
            # A stored pointer to a location that is gone: stale configuration, and not a
            # licence to pick a different one.
            raise NoEligibleLocationError("the configured stock location no longer exists")
        revision = serving_revision(location, operation=operation, features=features, origin=origin)
        return Allocation(warehouse_id=location.id, revision=revision, origin=origin)

    for source, origin in (
        (explicit, EXPLICIT),
        (sku_default, SKU_DEFAULT),
        (company_default, COMPANY_DEFAULT),
    ):
        if source is not None:
            return allocate(source, origin)
    return allocate(main_warehouse_id, MAIN)
