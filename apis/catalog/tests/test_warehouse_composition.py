"""Product-over-location policy composition and replenishment bands — no database.

docs/catalog-warehouses.md §2, §3. Every assertion here is a refusal or an identity, because
the convenient behaviour is what these forbid:

* a product restriction that *widens* the location's own policy is refused, not trimmed;
* composition is an intersection, so it answers the same whichever side is applied first;
* a missing row means the documented baseline, never a guessed deny and never a caller claim;
* a band no order can satisfy is rejected at review time rather than on a purchase order.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7

from catalog.domain.warehouse_policy_composition import (
    ALLOW_ALL_ACTIVE,
    ALLOW_LIST,
    LOCATION_LIMIT,
    MAX_LEAD_TIME_DAYS,
    SELECTION_MODES,
    ProductPermission,
    ProductPolicy,
    Replenishment,
    assert_narrows,
    assert_stock_allocatable,
)
from catalog.domain.warehouse_resolution import (
    OPERATIONS,
    SKU_DEFAULT,
    Location,
    NoEligibleLocationError,
    assert_can_serve,
)
from catalog.domain.warehouses import OPERATION_FLAGS

NONE: frozenset[str] = frozenset()
ALL_FLAGS = frozenset(OPERATION_FLAGS)
MULTI = frozenset({"inventory", "multi_godown"})
SALE = "allow_sale_issue"
PURCHASE = "allow_purchase_receipt"


def location(
    *,
    flags: frozenset[str] = ALL_FLAGS,
    kind: str = "STORE",
    is_main: bool = False,
    is_active: bool = True,
    revision: int | None = 1,
    identity: uuid.UUID | None = None,
) -> Location:
    return Location(
        id=identity or uuid7(),
        kind=kind,
        is_main=is_main,
        is_active=is_active,
        authorized=True,
        revision=revision,
        flags=flags,
    )


def band(**changes: object) -> Replenishment:
    """A satisfiable band: safety 2, reorder 5, target 20, ordered in tens."""
    values: dict[str, object] = {
        "safety_quantity": Decimal("2"),
        "reorder_quantity": Decimal("5"),
        "target_quantity": Decimal("20"),
        "min_order_quantity": Decimal("10"),
        "max_order_quantity": Decimal("100"),
        "order_multiple": Decimal("10"),
        "lead_time_days": 7,
    }
    values.update(changes)
    return Replenishment(**values)  # type: ignore[arg-type]  # keyword fan-out for one factory


# --- a stock location is for stock ---------------------------------------------------


def test_only_stocked_goods_may_be_kept_at_a_location() -> None:
    """Both halves are checked because they disagree: a goods family may be typed NON_STOCK,
    and Main's existence grants nothing to a product that never has a quantity."""
    assert_stock_allocatable(kind="GOODS", inventory_modes=["STOCK", "NON_STOCK"])
    with pytest.raises(ConflictError) as service:
        assert_stock_allocatable(kind="SERVICE", inventory_modes=["STOCK"])
    assert service.value.message == "a service is never stocked at a location"
    with pytest.raises(ConflictError) as non_stock:
        assert_stock_allocatable(kind="GOODS", inventory_modes=["NON_STOCK"])
    assert non_stock.value.message == "a non-stock product is never stocked at a location"
    with pytest.raises(ConflictError):
        assert_stock_allocatable(kind="GOODS", inventory_modes=[])


# --- narrowing only ------------------------------------------------------------------


def test_a_product_policy_may_narrow_and_never_widen() -> None:
    reviewed = frozenset({SALE, PURCHASE})
    assert_narrows(reviewed, reviewed)
    assert_narrows(reviewed, frozenset({SALE}))
    assert_narrows(reviewed, NONE)
    with pytest.raises(ConflictError) as widened:
        assert_narrows(reviewed, frozenset({SALE, "allow_adjustment"}))
    assert widened.value.message == "a product policy cannot allow what the stock location does not"
    # An unreviewed location allows nothing at all, so anything is a widening of it.
    with pytest.raises(ConflictError):
        assert_narrows(NONE, frozenset({SALE}))
    assert_narrows(NONE, NONE)


def test_an_unknown_flag_is_a_validation_error_not_a_widening() -> None:
    """422, not 409: the caller sent a field this system has never had, which no reviewed
    location policy could have permitted either."""
    with pytest.raises(ValidationFailedError):
        assert_narrows(ALL_FLAGS, frozenset({"allow_teleport"}))
    with pytest.raises(ValidationFailedError):
        ProductPermission(uuid7(), frozenset({"allow_teleport"}))


def test_composition_is_an_intersection_in_either_order() -> None:
    """Applied product-first or location-first, the answer is the same set. A composition
    that depended on order would make "may this product sell here" a question about how the
    caller happened to ask it."""
    identity = uuid7()
    reviewed = frozenset({SALE, PURCHASE, "allow_adjustment"})
    permitted = frozenset({SALE, PURCHASE})
    policy = ProductPolicy(ALLOW_LIST, (ProductPermission(identity, permitted),))
    forwards = policy.restrict(location(flags=reviewed, identity=identity)).flags
    backwards = policy.restrict(location(flags=permitted, identity=identity)).flags & reviewed
    assert forwards == backwards == permitted
    assert reviewed & permitted == permitted


def test_a_narrowed_product_cannot_serve_what_the_location_allows() -> None:
    """The point of the intersection: the location may issue sales, this product may not be
    sold from here, and the refusal happens at resolution rather than on a document."""
    identity = uuid7()
    policy = ProductPolicy(ALLOW_LIST, (ProductPermission(identity, frozenset({PURCHASE})),))
    composed = policy.restrict(location(flags=ALL_FLAGS, identity=identity))
    assert composed.flags == frozenset({PURCHASE})
    assert_can_serve(composed, operation="PURCHASE_RECEIPT", features=MULTI, origin=SKU_DEFAULT)
    with pytest.raises(NoEligibleLocationError) as refused:
        assert_can_serve(composed, operation="SALE_ISSUE", features=MULTI, origin=SKU_DEFAULT)
    assert refused.value.message.endswith("does not allow this operation")


def test_an_unreviewed_location_gains_nothing_from_a_product_policy() -> None:
    """A location with no reviewed revision keeps its empty flag set through composition:
    the intersection cannot invent a permission the company never reviewed."""
    identity = uuid7()
    policy = ProductPolicy(ALLOW_LIST, (ProductPermission(identity, ALL_FLAGS),))
    composed = policy.restrict(location(flags=NONE, revision=None, identity=identity))
    assert composed.flags == NONE
    for operation in OPERATIONS:
        with pytest.raises(NoEligibleLocationError):
            assert_can_serve(composed, operation=operation, features=MULTI, origin=SKU_DEFAULT)


# --- the missing row is the baseline -------------------------------------------------


def test_a_missing_policy_means_the_location_decides() -> None:
    """Adding these tables changed no existing product's reach: absent a row the product is
    stocked wherever the location's own policy allows, not denied everywhere."""
    baseline = ProductPolicy.baseline()
    assert baseline.selection_mode == ALLOW_ALL_ACTIVE and baseline.entries == ()
    spot = location(flags=frozenset({SALE}))
    assert baseline.permits(spot.id) is True
    assert baseline.restrict(spot) == spot
    assert_can_serve(baseline.restrict(spot), operation="SALE_ISSUE", features=MULTI)


def test_allow_all_active_still_narrows_a_location_it_names() -> None:
    """The mode is the gate; a named entry under it is a restriction, not a permission."""
    named, other = uuid7(), uuid7()
    policy = ProductPolicy(ALLOW_ALL_ACTIVE, (ProductPermission(named, frozenset({PURCHASE})),))
    assert policy.permits(named) and policy.permits(other)
    assert policy.restrict(location(identity=named)).flags == frozenset({PURCHASE})
    assert policy.restrict(location(identity=other)).flags == ALL_FLAGS


def test_an_allowlist_refuses_an_unnamed_location_as_a_different_error() -> None:
    """ "Not stocked here" is not "that operation is not allowed here": one is a membership
    answer and the other is a flag answer, and a reader fixing the configuration needs to
    know which."""
    named = uuid7()
    policy = ProductPolicy(ALLOW_LIST, (ProductPermission(named, ALL_FLAGS),))
    assert policy.permits(named) is True
    unnamed = location()
    assert policy.permits(unnamed.id) is False
    with pytest.raises(NoEligibleLocationError) as refused:
        policy.restrict(unnamed)
    assert refused.value.message == "this product is not stocked at that location"


def test_a_policy_is_hashable_bounded_and_free_of_duplicates() -> None:
    entry = ProductPermission(uuid7(), frozenset({SALE}))
    assert ProductPolicy(ALLOW_LIST, (entry,)) == ProductPolicy(ALLOW_LIST, (entry,))
    assert len({ProductPolicy(ALLOW_LIST, (entry,)), ProductPolicy(ALLOW_LIST, (entry,))}) == 1
    assert SELECTION_MODES == {ALLOW_ALL_ACTIVE, ALLOW_LIST}
    with pytest.raises(ValidationFailedError):
        ProductPolicy("ALLOW_NONE")
    with pytest.raises(ValidationFailedError):
        ProductPolicy(ALLOW_LIST, (entry, ProductPermission(entry.warehouse_id, NONE)))
    with pytest.raises(ValidationFailedError):
        ProductPolicy(
            ALLOW_LIST,
            tuple(ProductPermission(uuid7(), NONE) for _ in range(LOCATION_LIMIT + 1)),
        )
    # The nil UUID is the item-wide replenishment sentinel, never a location identity.
    with pytest.raises(ValidationFailedError):
        ProductPermission(uuid.UUID(int=0), NONE)


def test_an_entry_lookup_answers_none_rather_than_guessing() -> None:
    entry = ProductPermission(uuid7(), frozenset({SALE}))
    policy = ProductPolicy(ALLOW_ALL_ACTIVE, (entry,))
    assert policy.entry(entry.warehouse_id) is entry
    assert policy.entry(uuid7()) is None


# --- replenishment bands -------------------------------------------------------------


def test_a_reviewed_band_keeps_exact_decimals() -> None:
    reviewed = band()
    assert isinstance(reviewed.reorder_quantity, Decimal)
    assert reviewed.smallest_order() == Decimal("10")
    assert band(max_order_quantity=None).max_order_quantity is None


def test_band_quantities_must_be_ordered_and_positive() -> None:
    for changes in (
        {"safety_quantity": Decimal("6")},
        {"reorder_quantity": Decimal("25")},
        {"safety_quantity": Decimal("-1"), "reorder_quantity": Decimal("-1")},
        {
            "safety_quantity": Decimal("0"),
            "reorder_quantity": Decimal("0"),
            "target_quantity": Decimal("0"),
        },
        {"min_order_quantity": Decimal("0")},
        {"order_multiple": Decimal("0")},
        {"order_multiple": Decimal("-10")},
    ):
        with pytest.raises(ValidationFailedError):
            band(**changes)
    # Zero safety and zero reorder are legitimate: keep nothing, order when it runs out.
    assert band(safety_quantity=Decimal("0"), reorder_quantity=Decimal("0")).safety_quantity == 0


def test_a_float_quantity_is_refused_rather_than_coerced() -> None:
    """A binary-rounded reorder point would drift against the unit grid these same values
    are validated on, and nothing downstream could tell (CLAUDE.md §6.1)."""
    for changes in (
        {"safety_quantity": 2.0},
        {"order_multiple": 10.0},
        {"max_order_quantity": 100.0},
    ):
        with pytest.raises(ValidationFailedError) as refused:
            band(**changes)
        assert refused.value.message == "replenishment quantities are exact decimals"


def test_a_band_no_order_can_satisfy_is_refused_at_review_time() -> None:
    """Minimum 10 in multiples of 7 means the smallest real order is 14, which the maximum
    of 12 forbids: every suggestion inside the band would be rejected later, on a purchase
    order, with nothing recording why."""
    with pytest.raises(ValidationFailedError) as refused:
        band(order_multiple=Decimal("7"), max_order_quantity=Decimal("12"))
    assert refused.value.message == "no order multiple falls within the order band"
    assert (
        band(order_multiple=Decimal("7"), max_order_quantity=Decimal("14")).smallest_order() == 14
    )
    with pytest.raises(ValidationFailedError) as inverted:
        band(min_order_quantity=Decimal("10"), max_order_quantity=Decimal("9"))
    assert inverted.value.message == "maximum order is below the minimum order"


def test_satisfiability_is_decided_by_the_data_not_by_the_arithmetic() -> None:
    """A multiple of 0.3 against a minimum of 1 has no exact decimal quotient. Rounding the
    quotient would answer the question with the division instead of with the band."""
    reviewed = band(
        min_order_quantity=Decimal("1"),
        order_multiple=Decimal("0.3"),
        max_order_quantity=Decimal("1.2"),
    )
    assert reviewed.smallest_order() == Decimal("1.2")
    with pytest.raises(ValidationFailedError):
        band(
            min_order_quantity=Decimal("1"),
            order_multiple=Decimal("0.3"),
            max_order_quantity=Decimal("1.1"),
        )


def test_lead_time_is_a_whole_number_of_days_inside_ten_years() -> None:
    assert band(lead_time_days=0).lead_time_days == 0
    assert band(lead_time_days=MAX_LEAD_TIME_DAYS).lead_time_days == MAX_LEAD_TIME_DAYS
    for value in (-1, MAX_LEAD_TIME_DAYS + 1):
        with pytest.raises(ValidationFailedError):
            band(lead_time_days=value)
