"""Company location modes — no database, no framework (docs/catalog-warehouses.md §1)."""

from __future__ import annotations

import pytest
from billing_platform.errors import FeatureNotEnabledError, ValidationFailedError

from catalog.domain.warehouses import (
    MAIN_CODE,
    METADATA_ONLY,
    MULTI_LOCATION,
    SINGLE_LOCATION,
    TRANSIT_CODE,
    assert_additional_locations,
    assert_code_available,
    assert_kind,
    assert_selectable,
    location_mode,
)

NONE: frozenset[str] = frozenset()
INVENTORY = frozenset({"inventory"})
MULTI = frozenset({"inventory", "multi_godown"})


def test_inventory_off_is_metadata_only() -> None:
    assert location_mode(NONE) == METADATA_ONLY


def test_inventory_on_without_multiple_godowns_is_a_single_location() -> None:
    assert location_mode(INVENTORY) == SINGLE_LOCATION


def test_both_features_allow_additional_locations() -> None:
    assert location_mode(MULTI) == MULTI_LOCATION


def test_a_stray_multiple_godown_flag_without_inventory_is_not_multi_location() -> None:
    """`multi_godown` requires `inventory` in the feature catalogue, so this state should
    be unreachable. Asserted anyway: if it ever arrives, the safe reading is the weaker
    one, not silent enablement of stock operations."""
    assert location_mode(frozenset({"multi_godown"})) == METADATA_ONLY


def test_creating_another_location_needs_inventory_first() -> None:
    with pytest.raises(FeatureNotEnabledError) as raised:
        assert_additional_locations(NONE)

    assert raised.value.status_code == 409
    assert raised.value.extra["feature"] == "inventory"


def test_creating_another_location_needs_multiple_godowns() -> None:
    """409, not 403: no role can lift a feature gate, so it is not an authorization
    outcome and must not land in the permission-denial audit signal."""
    with pytest.raises(FeatureNotEnabledError) as raised:
        assert_additional_locations(INVENTORY)

    assert raised.value.status_code == 409
    assert raised.value.extra["feature"] == "multi_godown"


def test_creating_another_location_is_allowed_with_both_features() -> None:
    assert_additional_locations(MULTI)


def test_a_single_location_company_rejects_another_source_rather_than_mapping_it() -> None:
    """The rule this exists for. Rewriting the request to Main would post stock somewhere
    the caller did not ask for, and the caller could not tell that it happened."""
    with pytest.raises(FeatureNotEnabledError):
        assert_selectable(INVENTORY, is_main=False, kind="STORE")


def test_main_stays_selectable_in_every_mode() -> None:
    for features in (NONE, INVENTORY, MULTI):
        assert_selectable(features, is_main=True, kind="STORE")


def test_transit_is_never_selectable_even_with_every_feature_on() -> None:
    """Only typed transfer handlers reach transit custody (§4), so a public sale,
    purchase, opening or default naming it is a client error rather than a feature gate."""
    with pytest.raises(ValidationFailedError):
        assert_selectable(MULTI, is_main=False, kind="INTERNAL_TRANSIT")
    with pytest.raises(ValidationFailedError):
        assert_selectable(MULTI, is_main=True, kind="INTERNAL_TRANSIT")


def test_a_client_may_only_name_a_store_or_a_godown() -> None:
    for kind in ("STORE", "GODOWN"):
        assert_kind(kind, system=False)
    with pytest.raises(ValidationFailedError):
        assert_kind("INTERNAL_TRANSIT", system=False)
    with pytest.raises(ValidationFailedError):
        assert_kind("WAREHOUSE", system=False)


def test_the_bootstrap_may_create_the_system_kind() -> None:
    assert_kind("INTERNAL_TRANSIT", system=True)


def test_reserved_codes_are_refused_to_clients_in_any_case() -> None:
    for code in (MAIN_CODE, TRANSIT_CODE, "main", "Transit"):
        with pytest.raises(ValidationFailedError):
            assert_code_available(code, system=False)


def test_the_bootstrap_may_use_the_reserved_codes() -> None:
    assert_code_available(MAIN_CODE, system=True)
    assert_code_available(TRANSIT_CODE, system=True)


def test_an_ordinary_code_is_available() -> None:
    assert_code_available("STORE-01", system=False)
