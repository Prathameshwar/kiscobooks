"""Stock workflow grants remain company scoped and separate from approval/closing."""

from billing_platform.permissions import separation_of_duties_conflicts

from identity.domain.system_roles import get


def test_stock_operator_has_native_capture_and_posting_dependencies():
    held = get("stock_operator").permissions
    assert {
        "vouchers.read",
        "vouchers.create",
        "vouchers.import.read",
        "vouchers.import.manage",
        "vouchers.import.commit",
        "vouchers.edit",
        "vouchers.submit",
        "vouchers.post",
        "vouchers.reverse",
        "accounting.stock.read",
        "accounting.stock.post",
        "accounting.stock.reverse",
        "accounting.batch.read",
        "accounting.batch.manage",
        "accounting.serial.read",
        "accounting.serial.manage",
        "ledger.read",
        "ledger.post_journal",
        "period.read",
        "period.post",
        "warehouse.read",
        "warehouse_bin.read",
        "item.read",
        "unit.read",
        "inventory_profile_template.read",
    } <= held
    assert (
        not {
            "vouchers.approve",
            "vouchers.reject",
            "period.close",
            "period.reopen",
            "period.lock",
            "accounting.finance.manage",
            "role.assign",
            "role.manage",
        }
        & held
    )
    assert not separation_of_duties_conflicts(held)
    assert get("stock_operator").scope_hint == "company"
    assert "vouchers.create" not in get("company_admin").permissions


def test_company_admin_zero_opening_authority_is_narrow_and_scoped():
    admin = get("company_admin")
    assert "opening_balance.initialize_zero" in admin.permissions
    assert admin.scope_hint == "company"
    assert (
        not {
            "accounting.finance.manage",
            "opening_balance.manage",
            "vouchers.approve",
            "period.close",
            "period.reopen",
            "period.lock",
        }
        & admin.permissions
    )
    # The approved Tenant Administrator opening policy also includes zero declaration.
    assert "opening_balance.initialize_zero" in get("tenant_admin").permissions
    for key in ("stock_operator", "platform_admin", "viewer"):
        assert "opening_balance.initialize_zero" not in get(key).permissions
