"""Stock-location authority in the shipped roles (docs/catalog-warehouses.md).

Definitions are company-administration work. The operational roles read a location
because a document has to name one; none of them configures the location model, and
which locations any of them actually sees is its assignment scope, not a key here.
"""

from identity.domain.system_roles import SYSTEM_ROLES, get

WRITES = frozenset(
    {
        "warehouse.manage",
        "warehouse.publish",
        "warehouse.deactivate",
        "warehouse_group.manage",
        "warehouse_group.move",
        "warehouse_bin.manage",
        "item_warehouse_policy.manage",
    }
)


def test_location_configuration_requires_company_administration() -> None:
    for role in SYSTEM_ROLES:
        held = WRITES & role.permissions
        assert held == (WRITES if role.key == "company_admin" else frozenset())


def test_the_auditor_reads_every_location_definition_and_writes_none() -> None:
    """The role's promise is "read everything, change nothing". The import-time check
    would already refuse a missing read key; this pins the write half too."""
    auditor = get("tenant_auditor").permissions

    assert {
        "warehouse.read",
        "warehouse_group.read",
        "warehouse_bin.read",
        "item_warehouse_policy.read",
        "catalog.release.read",
    } <= auditor
    assert not WRITES & auditor


def test_operational_roles_read_a_location_without_configuring_one() -> None:
    """A salesperson picks the store a sale issues from; it does not follow that they
    may add one, retire one, or see the SKU allowlist behind it."""
    for key in ("salesperson", "billing_clerk", "viewer"):
        role = get(key)
        assert "warehouse.read" in role.permissions
        assert not WRITES & role.permissions
        assert "warehouse_group.read" not in role.permissions
        assert "item_warehouse_policy.read" not in role.permissions


def test_deactivation_is_not_implied_by_managing_a_location() -> None:
    """Separate keys, so a role could hold one without the other — asserted because
    `company_admin` holds both and would otherwise hide a collapsed pair."""
    for role in SYSTEM_ROLES:
        if "warehouse.deactivate" in role.permissions:
            assert role.key == "company_admin"
