"""The permission catalogue and the separation-of-duties list.

Two things here are load-bearing beyond the usual. The catalogue is asserted
**key by key** against docs/roles-permissions.md Â§2, because drift is invisible at
runtime: a role granting a key no code knows grants nothing, and a route requiring
a key no role grants denies everyone. And the separation-of-duties pairs are
asserted to name real keys, because a control that references a permission which
does not exist reads as enforced and never fires.

The seeded system roles are checked against this catalogue in ``identity``'s suite,
where the roles live.
"""

from __future__ import annotations

import re

import pytest

from billing_platform.errors import ValidationFailedError
from billing_platform.permissions import (
    PERMISSIONS,
    SEGREGATED_DUTIES,
    assert_known_permission,
    namespace,
    separation_of_duties_conflicts,
    validated_permission_key,
)

#: docs/roles-permissions.md Â§2, transcribed. Written out rather than derived so the
#: two lists have to be reconciled by a person when either changes â€” a comprehension
#: over ``PERMISSIONS`` would assert only that the code equals itself.
DOCUMENTED = {
    # Vouchers foundation: docs/roles-permissions.md.
    "vouchers.read",
    "vouchers.create",
    "vouchers.edit",
    "vouchers.submit",
    "vouchers.approve",
    "vouchers.reject",
    "vouchers.issue",
    "vouchers.share",
    "vouchers.cancel",
    "vouchers.accept",
    "vouchers.decline",
    "vouchers.expire",
    "vouchers.post",
    "vouchers.reverse",
    "vouchers.export",
    "vouchers.history.read",
    "vouchers.operation.read",
    "vouchers.operation.recover",
    "vouchers.type.manage",
    "vouchers.configuration.manage",
    "vouchers.configuration.publish",
    "vouchers.series.manage",
    "vouchers.template.manage",
    "vouchers.artifact.create",
    "vouchers.artifact.read",
    "vouchers.field.adopt",
    "vouchers.counter.read",
    "vouchers.counter.operate",
    "vouchers.counter.close",
    "vouchers.counter.supervise",
    "vouchers.import.read",
    "vouchers.import.manage",
    "vouchers.import.commit",
    # Accounting master and finance authorities, docs/roles-permissions.md.
    "accounting.head.read",
    "accounting.head.manage",
    "accounting.group.read",
    "accounting.group.manage",
    "accounting.account.read",
    "accounting.account.manage",
    "accounting.party.read",
    "accounting.party.manage",
    "accounting.tax.read",
    "accounting.tax.manage",
    "accounting.bank.read",
    "accounting.bank.manage",
    "accounting.statement.read",
    "accounting.statement.import",
    "accounting.statement.review",
    "accounting.bank_match.manage",
    "accounting.bank_session.finalize",
    "accounting.policy.read",
    "accounting.policy.manage",
    "accounting.withholding.read",
    "accounting.withholding.manage",
    "accounting.setup.read",
    "accounting.setup.manage",
    "accounting.mapping.read",
    "accounting.mapping.manage",
    "accounting.mapping.publish",
    "accounting.import.manage",
    "accounting.export.read",
    "accounting.history.read",
    "accounting.finance.read",
    "accounting.finance.manage",
    "accounting.finance.initialize",
    "period.read",
    "period.manage",
    "accounting.credit.read",
    "accounting.credit.manage",
    "accounting.credit.override_approve",
    "accounting.charges.read",
    "accounting.charges.manage",
    "accounting.charges.approve",
    "catalog.bulk.read",
    "catalog.bulk.manage",
    "catalog.bulk.commit",
    # platform
    "platform.tenant.create",
    "platform.tenant.read",
    "platform.tenant_access.read",
    "platform.tenant_access.manage",
    "platform.tenant.suspend",
    "platform.plan.manage",
    "platform.config.manage",
    "platform.account.read",
    "platform.account.review",
    # tenant and org
    "tenant.read",
    "tenant.update",
    "tenant.subscription.manage",
    "company.create",
    "company.read",
    "company.update",
    "company.deactivate",
    "company.tax_registration.manage",
    "company.statutory_id.manage",
    "company.licence.manage",
    "company.visibility.manage",
    "department.read",
    "department.manage",
    "user.invite",
    "user.read",
    "user.update",
    "user.deactivate",
    "user.impersonate",
    "group.read",
    "group.manage",
    "role.read",
    "role.assign",
    "role.manage",
    "custom_field.manage",
    "field_config.manage",
    "field_policy.manage",
    # catalog
    "unit.read",
    "unit.manage",
    "pack_type.read",
    "pack_type.manage",
    "item_group.read",
    "item_group.manage",
    "item_group.move",
    "category_scheme.read",
    "category_scheme.manage",
    "item_category.read",
    "item_category.manage",
    "item_category.move",
    "brand.read",
    "brand.manage",
    "brand.move",
    "brand_series.read",
    "brand_series.manage",
    "manufacturer.read",
    "manufacturer.manage",
    "manufacturer_site.read",
    "manufacturer_site.manage",
    "brand_manufacturer.read",
    "brand_manufacturer.manage",
    "product_type.read",
    "product_type.manage",
    "product_type.publish",
    "attribute_definition.read",
    "attribute_definition.manage",
    "attribute_option.read",
    "attribute_option.manage",
    "attribute_set.read",
    "attribute_set.manage",
    "attribute_set.publish",
    "identifier_profile.read",
    "identifier_profile.manage",
    "inventory_profile_template.read",
    "inventory_profile_template.manage",
    "inventory_profile_template.publish",
    "warranty_policy.read",
    "warranty_policy.manage",
    "warranty_policy.publish",
    "return_policy.read",
    "return_policy.manage",
    "return_policy.publish",
    "handling_profile.read",
    "handling_profile.manage",
    "handling_profile.publish",
    "master_alias.read",
    "master_alias.manage",
    "master_external_key.read",
    "master_external_key.manage",
    "item.create",
    "item.read",
    "product_configuration.read",
    "product_configuration.manage",
    "product_configuration.publish",
    "product_configuration.adopt",
    "item.update",
    "item.activate",
    "item.deactivate",
    "price_plan.read",
    "price_plan.manage",
    "price_plan.publish",
    "price_plan.override",
    "purchase_price.read",
    "purchase_price.manage",
    "reference_cost.read",
    "reference_cost.manage",
    "tax_rule.read",
    "tax_rule.manage",
    "tax_rule.publish",
    "warehouse.read",
    "warehouse.manage",
    "warehouse.publish",
    "warehouse.deactivate",
    "warehouse_group.read",
    "warehouse_group.manage",
    "warehouse_group.move",
    "warehouse_bin.read",
    "warehouse_bin.manage",
    "item_warehouse_policy.read",
    "item_warehouse_policy.manage",
    "catalog.release.read",
    "sales_channel.read",
    "sales_channel.manage",
    "customer_pricing.read",
    "customer_pricing.manage",
    "customer_pricing.publish",
    "identifier_type.read",
    "identifier_type.manage",
    "identifier_namespace.read",
    "identifier_namespace.manage",
    # billing
    "invoice.create",
    "invoice.read",
    "invoice.update",
    "invoice.post",
    "invoice.approve",
    "invoice.cancel",
    "invoice.export",
    "credit_note.create",
    "credit_note.read",
    "credit_note.post",
    "credit_note.approve",
    "ledger.read",
    "ledger.post_journal",
    "opening_balance.read",
    "opening_balance.manage",
    "exchange_rate.manage",
    "period.post",
    "period.post_adjustment",
    "period.close",
    "period.reopen",
    "period.lock",
    # payments
    "payment.read",
    "payment.record",
    "payment.allocate",
    "payment.refund",
    "payment.refund_approve",
    "integration.read",
    "integration.manage",
    # reports
    "report.read",
    "report.export",
    "report.definition.manage",
    # audit
    "audit.read",
    "audit.read_security",
    "audit.export",
    "activity.read",
    # notification â€” the entities in docs/notification.md. There is no
    # `notification.send`: send commands arrive over RabbitMQ, never over HTTP.
    "notification.provider.read",
    "notification.provider.manage",
    "notification.recipient.read",
    "notification.consent.manage",
    "notification.suppression.manage",
    "notification.template.read",
    "notification.template.manage",
    "notification.route.read",
    "notification.route.manage",
    "notification.request.read",
    "notification.delivery.read",
    "notification.delivery.retry",
}

# design — document layout, the entities in docs/invoice-design.md. `manage` and
# `publish` are separate grants, and `render.record` belongs to whoever issues documents
# rather than to whoever designs them (invoice-design.md §5.3).
DOCUMENTED.update(
    {
        "design.template.read",
        "design.template.manage",
        "design.template.publish",
        "design.assignment.read",
        "design.assignment.manage",
        "design.asset.read",
        "design.asset.manage",
        "design.component.read",
        "design.component.manage",
        "design.render.read",
        "design.render.record",
    }
)

# Explicit platform notification boundary; scanner authority is deliberately separate.
DOCUMENTED.update(
    {
        "notification.attachment.scan",
        "platform.notification_attachment.scan",
        "platform.notification_provider.read",
        "platform.notification_provider.manage",
        "platform.notification_recipient.read",
        "platform.notification_consent.manage",
        "platform.notification_suppression.manage",
        "platform.notification_template.read",
        "platform.notification_template.manage",
        "platform.notification_route.read",
        "platform.notification_route.manage",
        "platform.notification_request.read",
        "platform.notification_delivery.read",
        "platform.notification_delivery.retry",
    }
)

# Extension definition authorities; no operational stock or sale execution.
DOCUMENTED.update(
    {
        "manufacturing_operation.read",
        "manufacturing_operation.manage",
        "manufacturing_operation.publish",
        "manufacturing_route.read",
        "manufacturing_route.manage",
        "manufacturing_route.publish",
        "bom.read",
        "bom.manage",
        "bom.publish",
        "bom.assign",
        "promotion_stack_policy.read",
        "promotion_stack_policy.manage",
        "promotion_stack_policy.publish",
        "promotion_limit.read",
        "promotion_limit.manage",
        "promotion_limit.publish",
    }
)

# --- the catalogue as shipped -------------------------------------------------

# Existing stock/tracking and controlled zero-opening authorities, documented with
# their native master owners. This mirror must include their independent grants.
DOCUMENTED.update(
    {
        "accounting.batch.read",
        "accounting.batch.manage",
        "accounting.batch.hold",
        "accounting.serial.read",
        "accounting.serial.manage",
        "accounting.serial.hold",
        "accounting.stock.read",
        "accounting.stock.post",
        "accounting.stock.reverse",
        "accounting.stock.configure",
        "opening_balance.initialize_zero",
    }
)


def test_the_documented_permissions_are_the_ones_the_code_knows() -> None:
    assert PERMISSIONS == DOCUMENTED


def test_credit_note_read_exists_even_though_section_2_omits_it() -> None:
    """The one deliberate addition to the doc's list. ``billing_approver`` is granted
    it in Â§4 of the same document, and an approver that cannot read what it approves
    is not a workflow."""
    assert "credit_note.read" in PERMISSIONS


def test_every_key_is_two_or_three_lowercase_segments() -> None:
    """The shape the boot check enforces, asserted against the shipped list rather
    than only against the validator: a key that does not match is stored, compared
    as a string, and simply never matches anything."""
    pattern = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,2}$")

    assert [key for key in sorted(PERMISSIONS) if not pattern.match(key)] == []


def test_no_key_is_a_wildcard() -> None:
    """Â§4 of the doc writes ``company.*`` as shorthand for a role's grant list. It
    must never reach a stored row: whoever read it would have to expand it, and two
    readers would expand it differently â€” one of them at the moment a new key is
    added, silently widening every tenant's access."""
    assert [key for key in sorted(PERMISSIONS) if "*" in key] == []


def test_the_catalogue_cannot_be_extended_at_runtime() -> None:
    """A frozenset because a service that could append to the catalogue could grant
    itself a permission the reviewed list does not contain."""
    assert isinstance(PERMISSIONS, frozenset)


def test_namespace_is_the_leading_segment() -> None:
    assert namespace("invoice.post") == "invoice"
    assert namespace("company.tax_registration.manage") == "company"
    assert namespace("tenant.read") == "tenant"


def test_field_config_and_field_policy_are_separate_keys() -> None:
    """docs/identity-schema.md Â§6.2. Layout and access control are different
    authorities, and granting the first must never imply the second â€” a company
    admin arranging a form must not thereby be able to lift a field-level deny."""
    assert {"field_config.manage", "field_policy.manage"} <= PERMISSIONS


def test_initializing_books_is_a_narrower_key_than_managing_them() -> None:
    """docs/roles-permissions.md: setting a new company's books up and restating its
    opening balances are different authorities.

    ``accounting.finance.manage`` authorizes both ``financial_setup`` and the
    ``opening_batch`` controls, so granting it to an administrator would hand them a
    company's starting ledger position. ``accounting.finance.initialize`` exists so the
    first of those can be granted without the second, and the two must stay distinct
    keys for that to mean anything."""
    assert {"accounting.finance.initialize", "accounting.finance.manage"} <= PERMISSIONS
    assert "accounting.finance.initialize" != "accounting.finance.manage"
    # It is not half of a separation-of-duties pair: nothing it authorizes is the other
    # side of a control. Opening balances, closing and locking remain their own keys.
    assert all("accounting.finance.initialize" not in pair for pair in SEGREGATED_DUTIES)
    assert {"opening_balance.manage", "period.close", "period.lock"} <= PERMISSIONS


def test_no_stock_location_key_grants_a_stock_movement() -> None:
    """docs/catalog-warehouses.md §2. The location keys are definition authority. A
    movement key here would let a Catalog grant authorize a physical operation Billing
    owns, and the flags on a location deliberately grant nothing by themselves."""
    location_keys = {
        key
        for key in PERMISSIONS
        if namespace(key) in {"warehouse", "warehouse_group", "warehouse_bin"}
    }

    assert location_keys == {
        "warehouse.read",
        "warehouse.manage",
        "warehouse.publish",
        "warehouse.deactivate",
        "warehouse_group.read",
        "warehouse_group.manage",
        "warehouse_group.move",
        "warehouse_bin.read",
        "warehouse_bin.manage",
    }
    assert not {
        key
        for key in location_keys
        if key.rsplit(".", 1)[-1] not in {"read", "manage", "publish", "deactivate", "move"}
    }


def test_deactivating_a_location_is_a_separate_key_from_managing_one() -> None:
    """docs/catalog-warehouses.md §5. Deactivation is fenced behind a consumer
    acknowledgement and is the one location action that can strand stock, so an actor
    permitted to rename a store is not thereby permitted to retire it."""
    assert {"warehouse.manage", "warehouse.deactivate"} <= PERMISSIONS


def test_there_is_no_write_key_for_consumer_acknowledgement() -> None:
    """docs/catalog-warehouses.md §5, docs/catalog-inventory-integration.md §2.
    Acknowledgement is source-only ingestion. A write key would let a client assert
    that its own policy is enforced in a database Catalog cannot see."""
    release_keys = {key for key in PERMISSIONS if key.startswith("catalog.release.")}

    assert release_keys == {"catalog.release.read"}


def test_there_is_no_audit_management_permission() -> None:
    """The audit trail is immutable by database grant (docs/audit.md Â§4.1), so no
    permission alters it and none is offered. Asserted so that adding one becomes a
    deliberate act: it would be the first key in the system capable of destroying
    evidence, and Â§1.4's fourth pair depends on its absence."""
    audit_keys = {key for key in PERMISSIONS if namespace(key) == "audit"}

    assert audit_keys == {"audit.read", "audit.read_security", "audit.export"}
    assert not {key for key in PERMISSIONS if key.startswith("audit.") and "manage" in key}


# --- the boot check -----------------------------------------------------------


def test_a_known_permission_passes_the_boot_check() -> None:
    assert_known_permission("invoice.post")


def test_an_unknown_permission_fails_the_boot_rather_than_a_request() -> None:
    """``ValueError``, not a 403 and not a 422 (docs/identity-schema.md Â§5.2). A
    stored key absent from the catalogue means a shipped role grants nothing, and the
    only useful outcome is a boot that refuses to come up."""
    with pytest.raises(ValueError, match="not in the code catalogue"):
        assert_known_permission("invoice.postt")


def test_the_boot_failure_names_who_referenced_the_bad_key() -> None:
    """The key alone does not say where to go and fix it â€” the seed names the role,
    the startup assertion names the row."""
    with pytest.raises(ValueError, match="named by the seeded role billing_clerk"):
        assert_known_permission("invoice.publish", named_by="the seeded role billing_clerk")


def test_a_client_supplied_key_is_a_422_not_a_boot_failure() -> None:
    """Composing a tenant role is a legitimate request that can legitimately be
    wrong. Same catalogue, different status, deliberately a different function."""
    with pytest.raises(ValidationFailedError) as raised:
        validated_permission_key("invoice.publish")

    assert raised.value.status_code == 422
    assert raised.value.extra["fields"] == {"permission_key": "not in the platform catalogue"}


def test_a_valid_client_supplied_key_is_returned_unchanged() -> None:
    assert validated_permission_key("period.close") == "period.close"


def test_the_two_checks_agree_on_every_key_in_the_catalogue() -> None:
    """They differ only in status, so a key one accepts and the other rejects would
    mean a role could be composed through the API and then fail the next boot."""
    for key in sorted(PERMISSIONS):
        assert_known_permission(key)
        assert validated_permission_key(key) == key


# --- separation of duties -----------------------------------------------------


def test_every_segregated_pair_names_real_permissions() -> None:
    """The failure this catches is the quiet one: a pair naming a key that does not
    exist can never be held by anybody, so the control reads as enforced and never
    fires."""
    for first, second in SEGREGATED_DUTIES:
        assert first in PERMISSIONS
        assert second in PERMISSIONS


def test_the_documented_pairs_are_the_ones_enforced() -> None:
    """docs/roles-permissions.md Â§1.4. The fourth row's ``audit.*`` management does
    not exist as a permission and deliberately never will, so what is enforced is
    the expressible half â€” the administrator must not also be the security
    reviewer."""
    assert {frozenset(pair) for pair in SEGREGATED_DUTIES} == {
        frozenset({"invoice.create", "invoice.approve"}),
        frozenset({"vouchers.create", "vouchers.approve"}),
        frozenset({"invoice.post", "period.close"}),
        frozenset({"payment.refund", "payment.refund_approve"}),
        frozenset({"role.assign", "audit.read_security"}),
        frozenset({"opening_balance.manage", "period.lock"}),
    }


def test_holding_one_half_of_a_pair_is_not_a_conflict() -> None:
    """The clerk raises, the approver approves. Neither alone is a finding, which is
    what makes the pair a control rather than a ban on the permission."""
    assert separation_of_duties_conflicts({"invoice.create", "invoice.read"}) == ()
    assert separation_of_duties_conflicts({"invoice.approve", "invoice.read"}) == ()


def test_holding_both_halves_is_reported() -> None:
    assert separation_of_duties_conflicts(
        {"invoice.create", "invoice.approve", "invoice.read"}
    ) == (("invoice.create", "invoice.approve"),)


def test_every_conflict_in_a_permission_set_is_reported_not_just_the_first() -> None:
    """A caller deciding whether to warn or refuse needs the whole list: reporting
    one at a time turns a review into a loop the reviewer abandons."""
    conflicts = separation_of_duties_conflicts(
        {
            "invoice.create",
            "invoice.approve",
            "payment.refund",
            "payment.refund_approve",
        }
    )

    assert conflicts == (
        ("invoice.create", "invoice.approve"),
        ("payment.refund", "payment.refund_approve"),
    )


def test_conflicts_are_reported_in_catalogue_order() -> None:
    """Stable output, so a warning shown to a tenant does not reorder itself between
    two reads of the same role."""
    everything = separation_of_duties_conflicts(PERMISSIONS)

    assert everything == SEGREGATED_DUTIES


def test_reporting_returns_rather_than_raises() -> None:
    """The policy differs by who is asking â€” a system role must hold none, a tenant
    role composing one is warned and audited (Â§1.4) â€” and that decision belongs to
    ``identity``'s domain, not to the catalogue."""
    assert isinstance(separation_of_duties_conflicts(PERMISSIONS), tuple)


def test_an_unknown_permission_in_the_set_is_ignored_rather_than_raising() -> None:
    """This function answers "does this set combine duties", not "is this set
    valid". Two checks in one would mean the validity failure of a stored row
    surfaced as a duties warning."""
    assert separation_of_duties_conflicts({"invoice.create", "not.a.permission"}) == ()


# --- the catalogue rejects a malformed literal at import -----------------------


def test_a_malformed_key_would_fail_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """The import-time check, exercised against a deliberately broken catalogue.

    Patched rather than reimplemented: a copy of the shape check in the test would
    pass while the real one was broken.
    """
    from billing_platform import permissions as module

    monkeypatch.setattr(module, "_CATALOGUE", ("Invoice.Post",))

    with pytest.raises(ValueError, match="malformed permission key"):
        module._validate_catalogue()


def test_a_single_segment_key_would_fail_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """``invoice`` alone is not a permission â€” it names a resource and no action, so
    every check against it would be a guess about which action was meant."""
    from billing_platform import permissions as module

    monkeypatch.setattr(module, "_CATALOGUE", ("invoice",))

    with pytest.raises(ValueError, match="malformed permission key"):
        module._validate_catalogue()


def test_a_wildcard_key_would_fail_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    from billing_platform import permissions as module

    monkeypatch.setattr(module, "_CATALOGUE", ("audit.*",))

    with pytest.raises(ValueError, match="malformed permission key"):
        module._validate_catalogue()


def test_a_duplicated_key_would_fail_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invisible in the frozenset, which is the point: a reviewer approving the list
    would be reading something other than what shipped."""
    from billing_platform import permissions as module

    monkeypatch.setattr(module, "_CATALOGUE", ("invoice.post", "invoice.read", "invoice.post"))

    with pytest.raises(ValueError, match=r"duplicate permission keys .*invoice.post"):
        module._validate_catalogue()


def test_a_pair_naming_an_unknown_permission_would_fail_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worst of the four failures, because it reads as enforced: a pair whose key
    does not exist can never be held by anybody, so the control never fires."""
    from billing_platform import permissions as module

    monkeypatch.setattr(module, "SEGREGATED_DUTIES", (("invoice.create", "invoice.bless"),))

    with pytest.raises(ValueError, match="named by a separation-of-duties pair"):
        module._validate_catalogue()


def test_a_pair_of_one_permission_with_itself_would_fail_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It would flag every role holding that permission, which is a ban on the
    permission wearing the costume of a duties control."""
    from billing_platform import permissions as module

    monkeypatch.setattr(module, "SEGREGATED_DUTIES", (("period.close", "period.close"),))

    with pytest.raises(ValueError, match="names one permission twice"):
        module._validate_catalogue()


def test_the_same_pair_listed_twice_would_fail_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Order within a pair is presentation only, so the reversed duplicate is the same
    control â€” and it would report every conflict twice to whoever reviews the role."""
    from billing_platform import permissions as module

    monkeypatch.setattr(
        module,
        "SEGREGATED_DUTIES",
        (("invoice.create", "invoice.approve"), ("invoice.approve", "invoice.create")),
    )

    with pytest.raises(ValueError, match="listed twice"):
        module._validate_catalogue()


def test_the_shipped_catalogue_passes_its_own_check() -> None:
    """The import already ran it, and running it again is not redundant: the patched
    tests above prove the check *can* fail, and this proves the shipped literal is
    what passes it rather than a lenient check that passes anything."""
    from billing_platform import permissions as module

    module._validate_catalogue()
