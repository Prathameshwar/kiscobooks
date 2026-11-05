"""Stock-location definition rules. Definitions only — no balance, no movement.

docs/catalog-warehouses.md. Catalog owns *where stock may be kept and what a location
is allowed to do*; Billing owns what is actually in it. Nothing in this module reads or
asserts a quantity, and no rule here may be satisfied by inferring one.

Three company modes, and the middle one is the interesting case: with ``inventory`` on
and ``multi_godown`` off, a document naming a location other than Main is **rejected**.
Silently mapping it to Main would post stock somewhere the caller did not ask for, and
the caller would have no way to discover the substitution (§1).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Final

from billing_platform.errors import FeatureNotEnabledError, ValidationFailedError

#: STORE and GODOWN are labels on one location model, not separate inventories (§1).
#: INTERNAL_TRANSIT is custody during a dispatch/receive transfer: company-owned, in no
#: store's sale availability, reachable only by typed transfer handlers (§4).
WAREHOUSE_KINDS: Final[frozenset[str]] = frozenset({"STORE", "GODOWN", "INTERNAL_TRANSIT"})

#: Kinds Catalog provisions itself and no client may create, retype or delete.
SYSTEM_KINDS: Final[frozenset[str]] = frozenset({"INTERNAL_TRANSIT"})

#: Reserved codes for the two system rows. Stable: they are the built-in fallback and
#: the transfer custody scope, and both are referenced by id from other companies'
#: configuration rows, so a rename would strand those references (§1).
MAIN_CODE: Final[str] = "MAIN"
TRANSIT_CODE: Final[str] = "TRANSIT"
RESERVED_CODES: Final[frozenset[str]] = frozenset({MAIN_CODE, TRANSIT_CODE})

#: The eight operations a location's policy either allows or denies (§2), in the order the
#: revision table declares them. One name per typed column: a flag that lived in a JSON map
#: could not be constrained, indexed or migrated, and a typo in it would read as "denied"
#: on one release and "allowed" on the next.
OPERATION_FLAGS: Final[tuple[str, ...]] = (
    "allow_sale_issue",
    "allow_purchase_receipt",
    "allow_transfer_in",
    "allow_transfer_out",
    "allow_customer_return_receipt",
    "allow_supplier_return_issue",
    "allow_opening_stock",
    "allow_adjustment",
)

#: What a company may do with locations, given its feature state.
METADATA_ONLY: Final[str] = "METADATA_ONLY"
SINGLE_LOCATION: Final[str] = "SINGLE_LOCATION"
MULTI_LOCATION: Final[str] = "MULTI_LOCATION"


def location_mode(features: Collection[str]) -> str:
    """The mode of §1's table. ``multi_godown`` requires ``inventory`` in the feature
    catalogue, so the third case cannot be reached without the second's prerequisite."""
    if "inventory" not in features:
        return METADATA_ONLY
    return MULTI_LOCATION if "multi_godown" in features else SINGLE_LOCATION


def assert_additional_locations(features: Collection[str]) -> None:
    """Gate for creating or activating a location beyond the two system rows.

    409, not 403: no role can lift it. Creating an empty master is *not* financial use
    of ``multi_godown`` and does not trip its ratchet — first use is a movement (§1).
    """
    mode = location_mode(features)
    if mode == METADATA_ONLY:
        raise FeatureNotEnabledError(
            "stock locations beyond Main require the inventory feature",
            feature="inventory",
        )
    if mode == SINGLE_LOCATION:
        raise FeatureNotEnabledError(
            "additional stock locations require the multiple-godown feature",
            feature="multi_godown",
        )


def assert_selectable(features: Collection[str], *, is_main: bool, kind: str) -> None:
    """Gate for *naming* a location on an operation or a default.

    The rejection is the point. With ``multi_godown`` off the only selectable location is
    Main, and a request naming another one fails rather than being rewritten to Main.
    Transit is never selectable in either mode: only typed transfer handlers reach it,
    so a public sale, purchase, opening or default naming it is a client error (§4).
    """
    if kind == "INTERNAL_TRANSIT":
        raise ValidationFailedError("the internal transit location cannot be selected directly")
    if is_main:
        return
    assert_additional_locations(features)


def assert_kind(kind: str, *, system: bool) -> None:
    """A client supplies STORE or GODOWN. Catalog supplies the rest."""
    if kind not in WAREHOUSE_KINDS:
        raise ValidationFailedError("unsupported stock-location kind")
    if not system and kind in SYSTEM_KINDS:
        raise ValidationFailedError("that stock-location kind is provisioned by the system")


def assert_code_available(code: str, *, system: bool) -> None:
    """Reserved codes belong to the bootstrap, which passes ``system=True`` (§1)."""
    if not system and code.upper() in RESERVED_CODES:
        raise ValidationFailedError("that stock-location code is reserved by the system")
