"""Master aliases support readers; integration identities stay in administrative roles."""

from identity.domain.system_roles import SYSTEM_ROLES, get


def test_company_administrator_can_manage_identifier_and_channel_masters() -> None:
    required = {
        "identifier_type.read", "identifier_type.manage",
        "identifier_namespace.read", "identifier_namespace.manage",
        "sales_channel.read", "sales_channel.manage",
    }
    assert required <= get("company_admin").permissions
    for role in SYSTEM_ROLES:
        if role.key != "company_admin":
            assert not {key for key in required if key.endswith(".manage")} & role.permissions


def test_mapping_permissions_do_not_expand_business_roles_to_integration_administration() -> None:
    privileged = {"company_admin"}
    for role in SYSTEM_ROLES:
        if "master_external_key.read" in role.permissions:
            assert role.key in privileged | {"tenant_auditor"}
        if role.key in privileged:
            assert {
                "master_alias.read",
                "master_alias.manage",
                "master_external_key.read",
                "master_external_key.manage",
            } <= role.permissions
        else:
            assert "master_alias.manage" not in role.permissions
            assert "master_external_key.manage" not in role.permissions
        if "item.read" in role.permissions:
            assert "master_alias.read" in role.permissions
    assert "master_external_key.read" in get("tenant_auditor").permissions


def test_product_configuration_writes_require_company_administration() -> None:
    writes = {
        "product_configuration.manage",
        "product_configuration.publish",
        "product_configuration.adopt",
    }
    for role in SYSTEM_ROLES:
        if role.key == "company_admin":
            assert writes <= role.permissions
        else:
            assert not writes & role.permissions
        if "profile.read" in role.permissions:
            assert "product_configuration.read" in role.permissions


def test_purchase_and_estimate_authority_is_separate_from_sale_read() -> None:
    for role in SYSTEM_ROLES:
        if role.key in {"company_admin", "tenant_auditor"}:
            assert {"purchase_price.read", "reference_cost.read"} <= role.permissions
        else:
            assert not {"purchase_price.read", "reference_cost.read"} & role.permissions
        writes = {
            "purchase_price.manage",
            "reference_cost.manage",
            "price_plan.publish",
            "price_plan.override",
        }
        assert bool(writes & role.permissions) == (role.key == "company_admin")


def test_tax_publication_and_product_activation_require_company_administration() -> None:
    writes = {"tax_rule.publish", "item.activate"}
    for role in SYSTEM_ROLES:
        assert bool(writes & role.permissions) == (role.key == "company_admin")
    assert writes <= get("company_admin").permissions


def test_bulk_permissions_retain_company_administration_and_auditor_separation() -> None:
    for role in SYSTEM_ROLES:
        assert bool({"catalog.bulk.manage", "catalog.bulk.commit"} & role.permissions) == (
            role.key == "company_admin"
        )
        assert ("catalog.bulk.read" in role.permissions) == (
            role.key in {"company_admin", "tenant_auditor"}
        )
