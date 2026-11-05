"""The permission catalogue — code, not data.

docs/roles-permissions.md §2. A permission key says *what an actor may do*. It is
not a feature flag, which says what the company does (``features.py``), and it is
not a field policy, which subtracts a single field from an update already permitted
(docs/field-permissions.md). Every gate that matters passes all three.

**There is no ``permission`` table** (CLAUDE.md invariant 13, docs/org-model.md
§5.3). Roles are data a tenant composes; permissions are a fixed catalogue here.
The reason is static checkability: a route declares its required permission as a
constant, and a typo has to be catchable by reading the code rather than by
discovering that nobody can reach the endpoint. A table would make the key set
user-editable and nothing about it could be checked before a request arrives.

``role_permission.permission_key`` is therefore a plain ``VARCHAR`` with no foreign
key, and the compensating control is the boot check: a stored key absent from this
catalogue **fails the boot** (docs/identity-schema.md §5.2). A role granting a
permission no code recognizes grants nothing, silently, forever.

The catalogue is validated at **import time**, like the feature catalogue, so a
malformed key fails the boot rather than the first request that resolves it.

Namespaces are owned by the service that enforces them, and a service extends its
own — the whole list lives here because permission *resolution* is shared
mechanism (CLAUDE.md §3) and a resolver that could not see every key would report
a legitimate grant as unknown.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from typing import Final

from billing_platform.errors import ValidationFailedError

#: Two or three lowercase segments: ``invoice.post``, ``company.licence.manage``.
#: No wildcards — ``audit.*`` in a stored row or a seed would have to be expanded
#: by whoever read it, and two readers would expand it differently.
_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,2}$")

#: docs/roles-permissions.md §2, in the doc's own order and grouping. Keys are
#: **immutable once shipped**: they are stored in ``role_permission`` rows and named
#: in seeds, so a rename is a silent revocation for every tenant holding it.
_CATALOGUE: Final[tuple[str, ...]] = (
    # Shared voucher document/configuration authority; effects remain owner-gated.
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
    # Bulk voucher import jobs; each draft still requires vouchers.create.
    "vouchers.import.read",
    "vouchers.import.manage",
    "vouchers.import.commit",
    # platform — the platform itself, never a tenant's business data (§1.6)
    "platform.tenant.create",
    "platform.tenant.read",
    "platform.tenant_access.read",
    "platform.tenant_access.manage",
    "platform.tenant.suspend",
    "platform.plan.manage",
    "platform.config.manage",
    "platform.account.read",
    "platform.account.review",
    # tenant and org — identity
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
    # `field_config.manage` is form layout — show, hide, order, label — and is
    # grantable at company scope. `field_policy.manage` is field *access control*,
    # tenant scope only and a `security`-category audit event. Granting the first
    # must never imply the second (docs/identity-schema.md §6.2).
    "field_config.manage",
    "field_policy.manage",
    "accounting.finance.read",
    "accounting.finance.manage",
    # Initializing a company's `financial_setup` from signed Identity facts, and nothing
    # else. Deliberately narrower than `accounting.finance.manage`, which also authorizes
    # the opening-balance controls (`opening_batch`) — those set a company's starting
    # ledger position and stay with the controller. Setting a new company's books up is an
    # administrator's act; restating its balances is not.
    "accounting.finance.initialize",
    "period.read",
    "period.manage",
    # accounting masters; no financial posting or period-control grant is implied.
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
    # TDS/TCS withholding masters and the read-only preview; no posting is implied.
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
    # Tracking registration/holds do not authorize quantity, value or voucher posting.
    "accounting.batch.read",
    "accounting.stock.read",
    "accounting.stock.post",
    "accounting.stock.reverse",
    "accounting.stock.configure",
    "accounting.batch.manage",
    "accounting.batch.hold",
    "accounting.serial.read",
    "accounting.serial.manage",
    "accounting.serial.hold",
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
    "product_type.read",
    "product_type.manage",
    "brand.read",
    "brand.manage",
    "brand_series.read",
    "brand_series.manage",
    "manufacturer.read",
    "manufacturer.manage",
    "manufacturer_site.read",
    "manufacturer_site.manage",
    "brand_manufacturer.read",
    "brand_manufacturer.manage",
    "brand.move",
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
    "manufacturing_operation.read",
    "manufacturing_route.read",
    "manufacturing_operation.manage",
    "manufacturing_route.manage",
    "manufacturing_operation.publish",
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
    "warranty_policy.read",
    "warranty_policy.manage",
    "warranty_policy.publish",
    "return_policy.read",
    "return_policy.manage",
    "return_policy.publish",
    "master_alias.read",
    "master_alias.manage",
    "master_external_key.read",
    "master_external_key.manage",
    "handling_profile.read",
    "handling_profile.manage",
    "handling_profile.publish",
    "product_configuration.read",
    "product_configuration.manage",
    "product_configuration.publish",
    "product_configuration.adopt",
    "item.activate",
    "item.create",
    "item.read",
    "item.update",
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
    # stock-location definitions (docs/catalog-warehouses.md). Definitions only:
    # none of these authorizes a stock movement, which is Billing's. `warehouse.publish`
    # publishes an operation-policy revision; `warehouse.deactivate` is separate from
    # `.manage` because deactivation is fenced behind a consumer acknowledgement and is
    # the one warehouse action that can strand stock (§5).
    "warehouse.read",
    "warehouse.manage",
    "warehouse.publish",
    "warehouse.deactivate",
    "warehouse_group.read",
    "warehouse_group.manage",
    # Reparenting a dated hierarchy is not a `manage` PATCH, for the same reason
    # `item_group.move` is separate: it rewrites history for every descendant.
    "warehouse_group.move",
    "warehouse_bin.read",
    "warehouse_bin.manage",
    # Per-SKU location allowlists and per-location replenishment targets. One manage
    # key for both: they are the same per-SKU-per-location definition maintained by the
    # same role, and neither moves money, so splitting them adds a key with no
    # separation-of-duties reason behind it.
    "item_warehouse_policy.read",
    "item_warehouse_policy.manage",
    # Reads a published release and what a trusted consumer acknowledged. There is no
    # write key: acknowledgement is source-only ingestion through the consumer worker,
    # never an HTTP route a client could use to claim its own policy is enforced.
    "catalog.release.read",
    # v1 customer-pricing + channel + identifier masters. Read / manage / publish
    # split follows the existing pricing pattern; `customer_pricing.publish` is the
    # separate key that lets a role bind a rule to production, distinct from
    # authoring the rule.
    "sales_channel.read",
    "sales_channel.manage",
    "customer_pricing.read",
    "customer_pricing.manage",
    "customer_pricing.publish",
    "identifier_type.read",
    "identifier_type.manage",
    "identifier_namespace.read",
    "identifier_namespace.manage",
    "catalog.bulk.read",
    "catalog.bulk.manage",
    "catalog.bulk.commit",
    # billing
    "invoice.create",
    "invoice.read",
    "invoice.update",
    "invoice.post",
    "invoice.approve",
    "invoice.cancel",
    "invoice.export",
    "credit_note.create",
    # `credit_note.read` is absent from the doc's §2 list and granted by the
    # `billing_approver` role in the same doc's §4. Added here as the omission it
    # is: an approver that cannot read what it approves is not a workflow.
    "credit_note.read",
    "credit_note.post",
    "credit_note.approve",
    "accounting.credit.read",
    "accounting.credit.manage",
    "accounting.credit.override_approve",
    "accounting.charges.read",
    "accounting.charges.manage",
    "accounting.charges.approve",
    "ledger.read",
    "ledger.post_journal",
    "opening_balance.read",
    "opening_balance.manage",
    "opening_balance.initialize_zero",
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
    # design — document layout, owned by the `design` service (docs/invoice-design.md
    # §5). Authoring a layout is configuration, never a money permission: a template
    # decides what a document *looks* like, and `design.template.publish` is separate
    # from `manage` for the same reason `vouchers.configuration.publish` is — the act
    # that makes a draft the one every future document renders from is its own grant.
    # `design.render.record` writes print evidence, so it belongs to whoever issues
    # documents, not to whoever designs them.
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
    # reports
    "report.read",
    "report.export",
    "report.definition.manage",
    # audit
    "audit.read",
    "audit.read_security",
    "audit.export",
    "activity.read",
    # notification
    "notification.attachment.scan",
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
    "platform.notification_attachment.scan",
    # Platform-owned notification configuration; never tenant business authority.
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
)

PERMISSIONS: Final[frozenset[str]] = frozenset(_CATALOGUE)

#: docs/roles-permissions.md §1.4. Pairs no **system** role holds out of the box,
#: and that a tenant role should be warned about rather than silently allowed —
#: a small business often has one person who must hold both, and refusing outright
#: would leave them unable to operate.
#:
#: The doc's fourth row reads ``role.assign`` + "``audit.*`` management". There is
#: deliberately **no audit-management permission in the catalogue**: the audit
#: trail is immutable by database grant, not by convention (docs/audit.md §4.1),
#: and retention runs as a privileged job outside the permission model with its
#: period still an open question (audit.md §7). So the half of that rule the
#: catalogue *can* express is independence of review — whoever changes permissions
#: must not also be the one reviewing the security trail — which is
#: ``audit.read_security``, and that is what is encoded.
SEGREGATED_DUTIES: Final[tuple[tuple[str, str], ...]] = (
    # Self-approval defeats the control entirely.
    ("invoice.create", "invoice.approve"),
    ("vouchers.create", "vouchers.approve"),
    # The person recording transactions must not decide when the books shut.
    ("invoice.post", "period.close"),
    # Money leaving the business on one signature.
    ("payment.refund", "payment.refund_approve"),
    # Change permissions, then review your own change.
    ("role.assign", "audit.read_security"),
    # Restate the prior year and seal it in one action.
    ("opening_balance.manage", "period.lock"),
)


def namespace(permission: str) -> str:
    """The leading segment — ``invoice`` for ``invoice.post``.

    Used to group the catalogue for display and to keep a service's additions
    inside its own namespace. Does not validate: callers that need the key to be
    real call ``assert_known_permission`` first, and this stays cheap enough to
    use in a comprehension.
    """
    return permission.split(".", 1)[0]


# Ownership for the internal Catalog job-authority protocol. Permissions remain
# the fixed catalogue above; a resource name cannot invent a new permission key.
_CATALOG_RESOURCES: Final[frozenset[str]] = frozenset(
    {
        "unit",
        "pack_type",
        "item_group",
        "category_scheme",
        "item_category",
        "item",
        "price_plan",
        "purchase_price",
        "reference_cost",
        "tax_rule",
        "catalog",
        "product_type",
        "brand",
        "brand_series",
        "manufacturer",
        "manufacturer_site",
        "brand_manufacturer",
        "attribute_set",
        "attribute_definition",
        "attribute_option",
        "identifier_profile",
        "inventory_profile_template",
        "manufacturing_operation",
        "manufacturing_route",
        "promotion_stack_policy",
        "promotion_limit",
        "warranty_policy",
        "return_policy",
        "master_alias",
        "master_external_key",
        "handling_profile",
        "warehouse",
        "warehouse_group",
        "warehouse_bin",
        "item_warehouse_policy",
        "sales_channel",
        "customer_pricing",
        "identifier_type",
        "identifier_namespace",
        "promotion",
        "campaign",
        "coupon_program",
        "bom",
        "routing",
        "product_configuration",
    }
)
CATALOG_PERMISSIONS: Final[frozenset[str]] = frozenset(
    key for key in PERMISSIONS if key.split(".", 1)[0] in _CATALOG_RESOURCES
)


def assert_known_permission(permission: str, *, named_by: str | None = None) -> None:
    """Boot check: refuse a permission key the catalogue does not contain.

    ``ValueError``, not a 422 and not a 403. This is the check the seed and the
    startup assertion run (docs/identity-schema.md §5.2, roles-permissions.md §6),
    where an unknown key means a shipped role grants nothing and the only useful
    outcome is a failed boot. A 403 here would be indistinguishable from a
    legitimate denial and the typo would survive forever.

    ``named_by`` puts the *owner* of the bad key in the message — the seeded role,
    the stored row — because the key alone does not say where to go and fix it.
    """
    if permission in PERMISSIONS:
        return
    context = f" named by {named_by}" if named_by else ""
    raise ValueError(
        f"unknown permission{context}: {permission!r} is not in the code catalogue "
        "(docs/roles-permissions.md §2)"
    )


def validated_permission_key(permission: str) -> str:
    """The same check for a **client-supplied** key, as a 422.

    Composing a tenant role is a legitimate request that can legitimately be
    wrong, so it is input validation rather than a boot failure. Deliberately a
    separate function from ``assert_known_permission``: the two differ only in
    status, and one function with a flag would eventually be called with the wrong
    one — a 500 on a typed form field, or worse, a boot that survives bad data.
    """
    if permission not in PERMISSIONS:
        raise ValidationFailedError(
            f"unknown permission: {permission!r}",
            fields={"permission_key": "not in the platform catalogue"},
        )
    return permission


def separation_of_duties_conflicts(
    permissions: Iterable[str],
) -> tuple[tuple[str, str], ...]:
    """The §1.4 pairs this permission set holds both halves of.

    Returns them rather than raising: the policy differs by who is asking — the
    system-role seed must hold none, while a tenant role composing one is warned
    and audited — and that decision belongs to ``identity``'s domain, not here.
    """
    held = frozenset(permissions)
    return tuple(pair for pair in SEGREGATED_DUTIES if held >= frozenset(pair))


def _validate_catalogue() -> None:
    """Four ways the literal above can be wrong, none of them visible at runtime.

    A malformed key would be stored and compared as a string and simply never
    match. A duplicate is invisible in the frozenset, so a reviewer would be
    reading a list that is not what shipped. A separation-of-duties pair naming a
    key that does not exist is a control that silently never fires — the worst of
    the four, because it reads as enforced. And a pair of one key with itself
    would flag every role holding it.
    """
    for permission in _CATALOGUE:
        if not _KEY_PATTERN.match(permission):
            raise ValueError(f"malformed permission key: {permission!r}")

    counts = Counter(_CATALOGUE)
    repeated = sorted(key for key, count in counts.items() if count > 1)
    if repeated:
        raise ValueError(f"duplicate permission keys in the catalogue: {repeated}")

    for pair in SEGREGATED_DUTIES:
        for permission in pair:
            assert_known_permission(permission, named_by="a separation-of-duties pair")
        if pair[0] == pair[1]:
            raise ValueError(f"separation-of-duties pair names one permission twice: {pair}")

    if len({frozenset(pair) for pair in SEGREGATED_DUTIES}) != len(SEGREGATED_DUTIES):
        raise ValueError("the same separation-of-duties pair is listed twice")


_validate_catalogue()
