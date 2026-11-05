"""Location resolution and operation flags — no database, no framework.

docs/catalog-warehouses.md §2 and §3. Every branch of the chain, and every branch of the
refusals, because the refusals are the requirement: the convenient behaviour — quietly
using Main when the configured default cannot serve — is exactly what these forbid.
"""

from __future__ import annotations

import uuid

import pytest
from billing_platform.errors import (
    FeatureNotEnabledError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.ids import uuid7

from catalog.domain.warehouse_resolution import (
    ACTIVITY_DEFAULTS,
    APPLIED,
    COMPANY_DEFAULT,
    EXPLICIT,
    MAIN,
    OPERATIONS,
    PENDING,
    REJECTED,
    SKU_DEFAULT,
    Acknowledgement,
    Allocation,
    Location,
    NoEligibleLocationError,
    allowed_flags,
    assert_can_serve,
    delivery_state,
    resolve,
    serving_revision,
)
from catalog.domain.warehouses import OPERATION_FLAGS

NONE: frozenset[str] = frozenset()
INVENTORY = frozenset({"inventory"})
MULTI = frozenset({"inventory", "multi_godown"})
ALL_FLAGS = frozenset(OPERATION_FLAGS)


def location(
    *,
    flags: frozenset[str] = ALL_FLAGS,
    kind: str = "STORE",
    is_main: bool = False,
    is_active: bool = True,
    authorized: bool = True,
    revision: int | None = 1,
    identity: uuid.UUID | None = None,
) -> Location:
    return Location(
        id=identity or uuid7(),
        kind=kind,
        is_main=is_main,
        is_active=is_active,
        authorized=authorized,
        revision=revision,
        flags=flags,
    )


def among(*locations: Location) -> dict[uuid.UUID, Location]:
    return {row.id: row for row in locations}


# --- the eight flags are independent ------------------------------------------------


def test_every_documented_operation_maps_to_exactly_one_flag() -> None:
    """One flag per operation, and no flag serving two: an operation that shared a flag
    would be enabled as a side effect of the one the reviewer actually looked at (§2)."""
    assert set(OPERATIONS.values()) == set(OPERATION_FLAGS)
    assert len(set(OPERATIONS.values())) == len(OPERATIONS) == len(OPERATION_FLAGS) == 8


def test_a_sale_only_location_cannot_receive_a_purchase() -> None:
    sale_only = location(flags=frozenset({"allow_sale_issue"}), is_main=True)
    assert sale_only.allows("SALE_ISSUE")
    with pytest.raises(NoEligibleLocationError):
        serving_revision(sale_only, operation="PURCHASE_RECEIPT", features=MULTI, origin=EXPLICIT)


def test_a_purchase_only_location_cannot_issue_a_sale() -> None:
    """The other direction, asserted separately. The pair is the point: neither flag
    implies the other, in either order (§2)."""
    purchase_only = location(flags=frozenset({"allow_purchase_receipt"}), is_main=True)
    assert purchase_only.allows("PURCHASE_RECEIPT")
    with pytest.raises(NoEligibleLocationError):
        serving_revision(purchase_only, operation="SALE_ISSUE", features=MULTI, origin=EXPLICIT)


def test_purchase_disabled_leaves_transfer_in_and_customer_return_alone() -> None:
    """Named in §2 because the shortcut is tempting: "this location does not buy" is not
    "this location receives nothing"."""
    inbound = location(
        flags=ALL_FLAGS - {"allow_purchase_receipt"},
        is_main=True,
    )
    assert serving_revision(inbound, operation="TRANSFER_IN", features=MULTI, origin=MAIN) == 1
    assert (
        serving_revision(inbound, operation="CUSTOMER_RETURN_RECEIPT", features=MULTI, origin=MAIN)
        == 1
    )
    with pytest.raises(NoEligibleLocationError):
        serving_revision(inbound, operation="PURCHASE_RECEIPT", features=MULTI, origin=MAIN)


def test_a_zero_price_giveaway_still_needs_sale_issue() -> None:
    """§2. Resolution takes no amount at all, so there is no "free, therefore not a sale"
    path: a gift leaves the location as stock issued to a customer and needs the flag."""
    gifting = location(flags=ALL_FLAGS - {"allow_sale_issue"}, is_main=True)
    with pytest.raises(NoEligibleLocationError):
        serving_revision(gifting, operation="SALE_ISSUE", features=MULTI, origin=MAIN)


def test_flags_never_come_from_an_unknown_operation_name() -> None:
    everything = location(is_main=True)
    with pytest.raises(ValidationFailedError):
        everything.allows("STOCK_TAKE")
    with pytest.raises(ValidationFailedError):
        serving_revision(everything, operation="STOCK_TAKE", features=MULTI, origin=MAIN)


def test_an_unknown_origin_is_refused_rather_than_treated_as_a_fallback() -> None:
    with pytest.raises(ValidationFailedError):
        serving_revision(location(is_main=True), operation="SALE_ISSUE", features=MULTI, origin="X")


# --- the precedence chain -----------------------------------------------------------


def test_an_explicit_allocation_wins_over_both_defaults() -> None:
    chosen, sku, company, main = (location() for _ in range(4))
    allocation = resolve(
        "SALE_ISSUE",
        features=MULTI,
        candidates=among(chosen, sku, company, main),
        main_warehouse_id=main.id,
        explicit=chosen.id,
        sku_default=sku.id,
        company_default=company.id,
    )
    assert allocation == Allocation(warehouse_id=chosen.id, revision=1, origin=EXPLICIT)


def test_the_sku_default_wins_over_the_company_default() -> None:
    sku, company, main = (location() for _ in range(3))
    allocation = resolve(
        "SALE_ISSUE",
        features=MULTI,
        candidates=among(sku, company, main),
        main_warehouse_id=main.id,
        sku_default=sku.id,
        company_default=company.id,
    )
    assert allocation.origin == SKU_DEFAULT
    assert allocation.warehouse_id == sku.id


def test_the_company_default_serves_when_the_sku_has_none() -> None:
    company, main = location(), location()
    allocation = resolve(
        "SALE_ISSUE",
        features=MULTI,
        candidates=among(company, main),
        main_warehouse_id=main.id,
        company_default=company.id,
    )
    assert allocation.origin == COMPANY_DEFAULT
    assert allocation.warehouse_id == company.id


def test_main_serves_only_when_no_activity_default_is_configured() -> None:
    """§3's built-in tail. Reached because nothing is configured — never because something
    configured turned out to be unusable."""
    main = location(is_main=True)
    allocation = resolve(
        "SALE_ISSUE",
        features=MULTI,
        candidates=among(main),
        main_warehouse_id=main.id,
    )
    assert allocation == Allocation(warehouse_id=main.id, revision=1, origin=MAIN)


def test_the_resolved_revision_is_the_one_that_permitted_it() -> None:
    """The allocation pins the revision so an audit reader can see which policy allowed
    the operation without re-resolving against today's flags."""
    main = location(is_main=True, revision=7)
    assert (
        resolve(
            "ADJUSTMENT", features=MULTI, candidates=among(main), main_warehouse_id=main.id
        ).revision
        == 7
    )


# --- a configured default that cannot serve is an error, never a fallback ------------


def test_an_inactive_company_default_is_an_error_not_a_fall_through_to_main() -> None:
    """The rule this module exists for. Falling back would post stock into Main, and the
    document would carry no trace of the substitution (§3)."""
    company, main = location(is_active=False), location(is_main=True)
    with pytest.raises(NoEligibleLocationError):
        resolve(
            "SALE_ISSUE",
            features=MULTI,
            candidates=among(company, main),
            main_warehouse_id=main.id,
            company_default=company.id,
        )


def test_a_company_default_the_actor_may_not_use_is_an_error_not_a_fall_through() -> None:
    """409, not 403: the actor named nothing, so this is the company's configuration being
    unusable here, and still not permission to choose another location."""
    company, main = location(authorized=False), location(is_main=True)
    with pytest.raises(NoEligibleLocationError):
        resolve(
            "SALE_ISSUE",
            features=MULTI,
            candidates=among(company, main),
            main_warehouse_id=main.id,
            company_default=company.id,
        )


def test_a_stale_company_default_pointing_at_a_missing_location_is_an_error() -> None:
    main = location(is_main=True)
    with pytest.raises(NoEligibleLocationError):
        resolve(
            "SALE_ISSUE",
            features=MULTI,
            candidates=among(main),
            main_warehouse_id=main.id,
            company_default=uuid7(),
        )


def test_a_company_default_without_a_published_policy_is_an_error() -> None:
    """An absent policy allows nothing. Permissions are never inferred from a name (§2)."""
    company, main = location(revision=None, flags=NONE), location(is_main=True)
    with pytest.raises(NoEligibleLocationError):
        resolve(
            "SALE_ISSUE",
            features=MULTI,
            candidates=among(company, main),
            main_warehouse_id=main.id,
            company_default=company.id,
        )


def test_a_company_default_that_denies_the_operation_is_an_error() -> None:
    company = location(flags=ALL_FLAGS - {"allow_opening_stock"})
    main = location(is_main=True)
    with pytest.raises(NoEligibleLocationError):
        resolve(
            "OPENING_STOCK",
            features=MULTI,
            candidates=among(company, main),
            main_warehouse_id=main.id,
            company_default=company.id,
        )


def test_a_sku_default_that_cannot_serve_does_not_fall_to_the_company_default() -> None:
    """Precedence, not retry: the level that supplies the location is the level that
    decides, so a usable company default does not rescue a broken SKU default."""
    sku, company, main = location(is_active=False), location(), location(is_main=True)
    with pytest.raises(NoEligibleLocationError):
        resolve(
            "SALE_ISSUE",
            features=MULTI,
            candidates=among(sku, company, main),
            main_warehouse_id=main.id,
            sku_default=sku.id,
            company_default=company.id,
        )


# --- explicit allocations answer as the caller's own request -------------------------


def test_an_explicit_location_the_actor_may_not_reach_is_a_403() -> None:
    """Object-level scope, not a configuration conflict: the caller named this one."""
    named, main = location(authorized=False), location(is_main=True)
    with pytest.raises(PermissionDeniedError):
        resolve(
            "SALE_ISSUE",
            features=MULTI,
            candidates=among(named, main),
            main_warehouse_id=main.id,
            explicit=named.id,
        )


def test_an_explicit_location_that_does_not_exist_is_a_404() -> None:
    main = location(is_main=True)
    with pytest.raises(NotFoundError):
        resolve(
            "SALE_ISSUE",
            features=MULTI,
            candidates=among(main),
            main_warehouse_id=main.id,
            explicit=uuid7(),
        )


def test_a_second_location_is_refused_rather_than_mapped_to_main() -> None:
    """`multi_godown` off. The refusal is the behaviour: rewriting the request to Main
    would move stock the caller never named (§1)."""
    named, main = location(), location(is_main=True)
    with pytest.raises(FeatureNotEnabledError):
        resolve(
            "SALE_ISSUE",
            features=INVENTORY,
            candidates=among(named, main),
            main_warehouse_id=main.id,
            explicit=named.id,
        )


def test_transit_custody_is_never_reachable_through_resolution() -> None:
    """Only typed transfer handlers touch it, so naming it here is a client error (§4)."""
    transit = location(kind="INTERNAL_TRANSIT")
    main = location(is_main=True)
    with pytest.raises(ValidationFailedError):
        resolve(
            "TRANSFER_OUT",
            features=MULTI,
            candidates=among(transit, main),
            main_warehouse_id=main.id,
            explicit=transit.id,
        )


# --- blocked even at Main -----------------------------------------------------------


def test_an_activity_blocked_at_main_reports_no_eligible_location() -> None:
    """§2's explicit instruction: no re-enabled flag, no unrelated store, no silent
    success. The company blocked the activity and the answer says so."""
    main = location(is_main=True, flags=ALL_FLAGS - {"allow_supplier_return_issue"})
    other = location(flags=ALL_FLAGS)
    with pytest.raises(NoEligibleLocationError) as raised:
        resolve(
            "SUPPLIER_RETURN_ISSUE",
            features=MULTI,
            candidates=among(main, other),
            main_warehouse_id=main.id,
        )
    assert raised.value.status_code == 409


def test_main_without_a_published_policy_blocks_rather_than_allowing_everything() -> None:
    main = location(is_main=True, revision=None, flags=NONE)
    with pytest.raises(NoEligibleLocationError):
        resolve("SALE_ISSUE", features=MULTI, candidates=among(main), main_warehouse_id=main.id)


# --- activity defaults --------------------------------------------------------------


def test_each_company_pointer_is_validated_against_its_own_operation() -> None:
    assert set(ACTIVITY_DEFAULTS.values()) <= set(OPERATIONS)
    assert len(set(ACTIVITY_DEFAULTS.values())) == len(ACTIVITY_DEFAULTS) == 4


def test_a_default_pointing_at_a_location_that_denies_that_activity_is_refused() -> None:
    """Checked when the default is *set*, so the failure lands on the configuration change
    rather than on a document weeks later (§3)."""
    candidate = location(flags=ALL_FLAGS - {"allow_customer_return_receipt"})
    with pytest.raises(NoEligibleLocationError):
        assert_can_serve(
            candidate,
            operation=ACTIVITY_DEFAULTS["default_customer_return_warehouse_id"],
            features=MULTI,
        )


def test_with_multi_godown_off_only_main_may_be_an_activity_default() -> None:
    """§3's last line, and it needs no separate rule: selectability already says it."""
    main = location(is_main=True)
    other = location()
    for column, operation in ACTIVITY_DEFAULTS.items():
        assert column
        assert_can_serve(main, operation=operation, features=INVENTORY)
        with pytest.raises(FeatureNotEnabledError):
            assert_can_serve(other, operation=operation, features=INVENTORY)


def test_activity_defaults_need_the_inventory_feature_at_all() -> None:
    other = location()
    with pytest.raises(FeatureNotEnabledError) as raised:
        assert_can_serve(other, operation="SALE_ISSUE", features=NONE)
    assert raised.value.extra["feature"] == "inventory"


# --- flag sets and delivery state ---------------------------------------------------


def test_allowed_flags_keeps_only_the_true_ones_in_declaration_order() -> None:
    values = dict.fromkeys(OPERATION_FLAGS, False) | {"allow_transfer_in": True}
    assert allowed_flags(values) == frozenset({"allow_transfer_in"})


def test_allowed_flags_refuses_a_name_that_is_not_an_operation_flag() -> None:
    with pytest.raises(ValidationFailedError):
        allowed_flags({"allow_teleport": True})


def test_a_fresh_publish_reports_pending() -> None:
    """§5. Catalog cannot claim its own revision is enforced; only a consumer can."""
    assert delivery_state(1, None) == PENDING


def test_an_acknowledgement_of_an_older_revision_leaves_the_new_one_pending() -> None:
    assert delivery_state(3, Acknowledgement(revision=2, accepted=True)) == PENDING


def test_an_acknowledged_revision_is_applied_and_a_refused_one_is_rejected() -> None:
    assert delivery_state(3, Acknowledgement(revision=3, accepted=True)) == APPLIED
    assert delivery_state(3, Acknowledgement(revision=3, accepted=False)) == REJECTED


# --- the value objects refuse nonsense ----------------------------------------------


def test_a_location_cannot_carry_flags_without_a_published_revision() -> None:
    with pytest.raises(ValidationFailedError):
        location(revision=None, flags=frozenset({"allow_sale_issue"}))


def test_a_location_cannot_carry_an_unknown_flag_or_kind_or_empty_identity() -> None:
    with pytest.raises(ValidationFailedError):
        location(flags=frozenset({"allow_teleport"}))
    with pytest.raises(ValidationFailedError):
        location(kind="DEPOT")
    with pytest.raises(ValidationFailedError):
        location(identity=uuid.UUID(int=0))
    with pytest.raises(ValidationFailedError):
        location(revision=0)


def test_an_allocation_and_an_acknowledgement_are_numbered_from_one() -> None:
    with pytest.raises(ValidationFailedError):
        Allocation(warehouse_id=uuid7(), revision=0, origin=MAIN)
    with pytest.raises(ValidationFailedError):
        Allocation(warehouse_id=uuid7(), revision=1, origin="ELSEWHERE")
    with pytest.raises(ValidationFailedError):
        Allocation(warehouse_id=uuid.UUID(int=0), revision=1, origin=MAIN)
    with pytest.raises(ValidationFailedError):
        Acknowledgement(revision=0, accepted=True)
