"""What one product may do at one location, and how much of it to keep there.

docs/catalog-warehouses.md §2, §3. Pure: no session, no ORM, no clock, no permission
lookup. The caller loads the location's own reviewed policy and the product's restriction;
this module composes them and validates a replenishment band.

Three rules carry the weight, and each is the opposite of the convenient behaviour:

* **A product restriction narrows; it never widens.** A location that may not receive
  purchases does not start receiving them because somebody ticked the box on a SKU. The
  location's reviewed revision is the ceiling, and composition is an intersection — so it
  gives the same answer whichever side is applied first (§2).
* **A missing restriction means the documented company baseline, never a guess.** Absent a
  row the SKU may be stocked wherever the location's own policy allows; it is not silently
  denied everywhere, and it is not permitted by a claim the caller sent along.
* **A stock location is for stock.** A service, or goods a type says are non-stock, is
  rejected outright. Main's existence grants no allocation to something that never has a
  quantity.

Nothing here reads a session or a permission: whether the actor may *see* a location is
decided before this module is reached, exactly as in ``warehouse_resolution``.
"""

from __future__ import annotations

import dataclasses
import math
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Final

from billing_platform.errors import ConflictError, ValidationFailedError

from catalog.domain.warehouse_resolution import Location, NoEligibleLocationError
from catalog.domain.warehouses import OPERATION_FLAGS

#: The SKU may be stocked at any location whose own policy allows the operation. This is the
#: baseline a missing row means, so adding the table changed no existing product's reach.
ALLOW_ALL_ACTIVE: Final[str] = "ALLOW_ALL_ACTIVE"
#: Only the named locations, and at each of them only the named operations.
ALLOW_LIST: Final[str] = "ALLOW_LIST"
SELECTION_MODES: Final[frozenset[str]] = frozenset({ALLOW_ALL_ACTIVE, ALLOW_LIST})

#: Bounds on one product's stored policy. Both are list bounds rather than business limits:
#: an unbounded membership would make the policy read an unbounded query
#: (docs/api-conventions.md), and the schemas take these same numbers.
LOCATION_LIMIT: Final[int] = 200
SCOPE_LIMIT: Final[int] = 64

#: Ten years. A lead time beyond that is a data-entry error, not a supply chain.
MAX_LEAD_TIME_DAYS: Final[int] = 3650


def assert_stock_allocatable(*, kind: str, inventory_modes: Collection[str]) -> None:
    """Can this product be kept at a location at all?

    409 rather than 422: the request is well formed and no role lifts it — the product is
    simply not a thing that occupies space. Both halves are checked because they can
    disagree: a goods family may still be typed ``NON_STOCK``, and neither answer alone is
    the whole one.
    """
    if kind != "GOODS":
        raise ConflictError("a service is never stocked at a location")
    if "STOCK" not in set(inventory_modes):
        raise ConflictError("a non-stock product is never stocked at a location")


def assert_narrows(location_flags: frozenset[str], product_flags: frozenset[str]) -> None:
    """Reject a restriction that allows what the location's own policy does not.

    Composition would intersect the surplus away, so this changes no resolution outcome —
    it refuses to *store* a claim that reads as a permission the location never granted.
    Silently trimming it would leave a policy row whose flags mean something different from
    what the reviewer approved.
    """
    if not product_flags <= frozenset(OPERATION_FLAGS):
        raise ValidationFailedError("unknown stock-location operation flag")
    if product_flags - location_flags:
        raise ConflictError("a product policy cannot allow what the stock location does not")


@dataclass(frozen=True, slots=True)
class ProductPermission:
    """One location this product may be stocked at, and the operations allowed there."""

    warehouse_id: uuid.UUID
    flags: frozenset[str]

    def __post_init__(self) -> None:
        if self.warehouse_id.int == 0:
            raise ValidationFailedError("invalid stock-location identity")
        if not self.flags <= frozenset(OPERATION_FLAGS):
            raise ValidationFailedError("unknown stock-location operation flag")


@dataclass(frozen=True, slots=True)
class ProductPolicy:
    """One product's stored location policy, as the resolver needs it.

    ``entries`` is a tuple rather than a mapping so the policy stays hashable and its order
    is the order it was stored in; lookup is by id through :meth:`entry`.
    """

    selection_mode: str
    entries: tuple[ProductPermission, ...] = ()

    def __post_init__(self) -> None:
        if self.selection_mode not in SELECTION_MODES:
            raise ValidationFailedError("unknown stock-location selection mode")
        if len(self.entries) > LOCATION_LIMIT:
            raise ValidationFailedError("too many stock locations in one product policy")
        identities = {entry.warehouse_id for entry in self.entries}
        if len(identities) != len(self.entries):
            raise ValidationFailedError("one stock location appears twice in the product policy")

    @classmethod
    def baseline(cls) -> ProductPolicy:
        """What a product with no stored row means: the location's own policy, unnarrowed."""
        return cls(ALLOW_ALL_ACTIVE)

    def entry(self, warehouse_id: uuid.UUID) -> ProductPermission | None:
        return next((item for item in self.entries if item.warehouse_id == warehouse_id), None)

    def permits(self, warehouse_id: uuid.UUID) -> bool:
        """Is this location within the product's reach at all?

        Under ``ALLOW_ALL_ACTIVE`` an unnamed location is permitted — the mode is the
        baseline, and a named one there restricts operations without being a gate.
        """
        return self.selection_mode == ALLOW_ALL_ACTIVE or self.entry(warehouse_id) is not None

    def assert_permits(self, warehouse_id: uuid.UUID) -> None:
        """The same question as a refusal, so "not stocked here" is worded in one place.

        Authoring a band and resolving a document both ask it — one about a location the
        caller just named, the other about a candidate — and two wordings of the same fact
        would read as two different rules.
        """
        if not self.permits(warehouse_id):
            raise NoEligibleLocationError("this product is not stocked at that location")

    def restrict(self, location: Location) -> Location:
        """The location as this product sees it: its own flags, intersected with the SKU's.

        Under ``ALLOW_LIST`` an unnamed location is not a location with no flags — it is not
        a candidate at all, and saying so is a different error from "that operation is not
        allowed here". A location with no reviewed revision keeps its empty flag set either
        way, so the intersection cannot invent permissions for an unreviewed location.
        """
        self.assert_permits(location.id)
        entry = self.entry(location.id)
        if entry is None:
            return location
        return dataclasses.replace(location, flags=location.flags & entry.flags)


@dataclass(frozen=True, slots=True)
class Replenishment:
    """One product's stock band at one scope, as reviewed rather than as computed.

    Catalog stores the band; Billing compares it against a quantity it owns. Nothing here
    reads a balance, so none of these rules can be satisfied by inferring one.

    ``Decimal`` throughout, never float: these are the quantities a suggested purchase order
    is built from, and a binary-rounded reorder point would drift against the unit grid the
    same values are validated on.
    """

    safety_quantity: Decimal
    reorder_quantity: Decimal
    target_quantity: Decimal
    min_order_quantity: Decimal
    max_order_quantity: Decimal | None
    order_multiple: Decimal
    lead_time_days: int

    def __post_init__(self) -> None:
        quantities = (
            self.safety_quantity,
            self.reorder_quantity,
            self.target_quantity,
            self.min_order_quantity,
            self.order_multiple,
        )
        if any(not isinstance(value, Decimal) for value in quantities):
            raise ValidationFailedError("replenishment quantities are exact decimals")
        if any(value < 0 for value in quantities):
            raise ValidationFailedError("a replenishment quantity cannot be negative")
        if not self.safety_quantity <= self.reorder_quantity <= self.target_quantity:
            raise ValidationFailedError("safety, reorder and target quantities must be ordered")
        if self.target_quantity <= 0:
            raise ValidationFailedError("a replenishment target must be positive")
        if self.order_multiple <= 0 or self.min_order_quantity <= 0:
            raise ValidationFailedError("order multiple and minimum order must be positive")
        if not 0 <= self.lead_time_days <= MAX_LEAD_TIME_DAYS:
            raise ValidationFailedError("lead time is between 0 and 3650 days")
        if self.max_order_quantity is None:
            return
        if not isinstance(self.max_order_quantity, Decimal):
            raise ValidationFailedError("replenishment quantities are exact decimals")
        if self.max_order_quantity < self.min_order_quantity:
            raise ValidationFailedError("maximum order is below the minimum order")
        if self.smallest_order() > self.max_order_quantity:
            # A band no order can satisfy is worse than no band: every suggestion inside it
            # would be rejected later, on a purchase order, with nothing recording why.
            raise ValidationFailedError("no order multiple falls within the order band")

    def smallest_order(self) -> Decimal:
        """The least multiple of ``order_multiple`` that reaches the minimum order.

        ``Fraction`` rather than ``Decimal`` division: a multiple of ``0.3`` against a
        minimum of ``1`` has no exact decimal quotient, and rounding it would answer the
        satisfiability question with the arithmetic instead of with the data.
        """
        steps = math.ceil(Fraction(self.min_order_quantity) / Fraction(self.order_multiple))
        return self.order_multiple * steps
