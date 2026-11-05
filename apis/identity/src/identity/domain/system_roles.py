"""The shipped system roles — a catalogue, not rows.

docs/roles-permissions.md §4. These are what ``seeds/roles`` writes at
``tenant_id = SCOPE_ALL``, and they are **read-only to tenants** (§1.2): an upgrade
that adds a permission to a shipped role must not be silently reverted by a tenant's
edit, so customising one means cloning it into a tenant role and editing the copy.

Keys are listed **literally, never as wildcards**. ``audit.*`` in a seed would have to
be expanded by whoever read it, and two readers would expand it differently — the same
reason ``billing_platform.permissions`` refuses a wildcard in a key.

The catalogue is validated at **import time**, like the permission and feature
catalogues, so every one of these mistakes fails the boot rather than the first request
that resolves a role:

* a permission absent from the code catalogue — the role would grant nothing, silently
  and forever (§6);
* two roles sharing a key, or a key that ``role.key``'s ``VARCHAR(60)`` would truncate;
* a **separation-of-duties pair held by a shipped role** (§1.4) — the point of
  preloading roles is to get this right by default, so unlike a tenant's own role this
  is refused rather than warned about;
* a ``.read`` permission in the catalogue that ``tenant_auditor`` neither holds nor
  explicitly withholds. That role's promise is "read everything, change nothing", and a
  new read key added in another service would otherwise quietly fall outside it.

Three deliberate departures from the doc's §4 lists, each recorded in that doc's
decision log:

**``tenant_admin`` does not hold ``user.impersonate``.** The doc writes ``user.*``.
Impersonation is the one permission that converts an org-administration role into every
other role: a tenant admin could impersonate the controller and close a period, which
defeats §1.4 entirely. Platform support holds it, time-bound and audited (§1.6).

**``company_admin`` holds ``price_plan.read`` and ``tax_rule.read``** alongside the
``manage`` keys the doc lists. Manage without read is not a workflow — the same omission
as the doc's missing ``credit_note.read``.

**``tenant_admin`` and ``company_admin`` hold the books-bootstrap keys**
(``accounting.finance.read``, ``accounting.finance.initialize``, ``period.read``,
``period.manage``). Creating a company and leaving it unable to post is not a finished
act, and the four keys are bounded: generate a year, open a FUTURE period, initialize
the authoritative setup. The user-approved 2026-10-30 opening policy additionally
gives ``tenant_admin`` native finance management and journal posting authority.
``company_admin`` retains bounded bootstrap. Closing (``period.close`` /
``period.reopen`` / ``period.lock``) stays separate.

**Purchase work has its own role, ``purchase_clerk``** (decision 2026-11-01,
docs/purchase-e2e-review.md D4). The untaxed account Purchase page, its posting and its
print read Accounting masters that no role holding ``vouchers.create`` could read:
``billing_clerk`` is the Sales role and stays one, and widening it would hand every
sales clerk the supplier directory and the right to post. ``purchase_clerk`` records,
submits and posts a supplier bill and prints it; it never approves one. The same
decision gives ``billing_approver`` the reads it needs to render the bill it approves,
and ``stock_operator`` (the company creator's role) the supplier name and printing.

**``platform_admin`` holds no permission over tenant business data** beyond
``tenant.read`` (§1.6). A cross-tenant read path is a breach waiting for one bug, so
support access is impersonation instead. The dedicated ``platform.tenant_access``
boundary manages only customer tenant-administrator accounts and their fixed system
assignment (the bounded exception in section 1.6, requested 2026-10-25).

No framework and no ORM here (CLAUDE.md §4): this module is a value catalogue, and the
seed that writes it is the only thing that knows about a session.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Final

from billing_platform.authz import SCOPE_HINTS
from billing_platform.permissions import (
    PERMISSIONS,
    assert_known_permission,
    separation_of_duties_conflicts,
)

#: ``role.key``'s shape, and its ``VARCHAR(60)`` width. Keys are **immutable once
#: shipped** (§6): assignments reference the role by id, but seeds, tests and support
#: runbooks all reference it by key, and a rename reads as a new role to every one of
#: them.
_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{2,59}$")

#: Read permissions ``tenant_auditor`` deliberately does **not** hold, so that the
#: completeness check below can tell "withheld on purpose" from "added and forgotten".
#: Only the platform surface: a tenant's auditor is not a platform actor, and
#: ``platform.tenant.read`` lists every tenant on the installation (§1.6).
READS_WITHHELD_FROM_AUDITOR: Final[frozenset[str]] = frozenset(
    {
        "platform.tenant.read",
        "platform.tenant_access.read",
        "platform.account.read",
        "platform.notification_provider.read",
        "platform.notification_recipient.read",
        "platform.notification_template.read",
        "platform.notification_route.read",
        "platform.notification_request.read",
        "platform.notification_delivery.read",
    }
)


@dataclass(frozen=True, slots=True)
class SystemRole:
    """One shipped role. ``permissions`` is the whole grant — roles are additive, so
    there is no inheritance between these and none is implied by their ordering."""

    key: str
    name: str
    description: str
    #: Which scope the assignment form should offer first. Guidance only: what a grant
    #: reaches is the assignment's own scope (docs/identity-schema.md §5.1).
    scope_hint: str
    permissions: frozenset[str]


SYSTEM_ROLES: Final[tuple[SystemRole, ...]] = (
    SystemRole(
        key="platform_admin",
        name="Platform Administrator",
        description="Manages tenants, plans and system configuration — not tenant data.",
        scope_hint="platform",
        permissions=frozenset(
            {
                "platform.tenant.create",
                "platform.tenant.read",
                "platform.tenant_access.read",
                "platform.tenant_access.manage",
                "platform.tenant.suspend",
                "platform.plan.manage",
                "platform.config.manage",
                "platform.account.read",
                "platform.account.review",
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
                "tenant.read",
            }
        ),
    ),
    SystemRole(
        key="platform_support",
        name="Platform Support",
        description="Read-only, plus time-bound audited impersonation. No money writes.",
        scope_hint="platform",
        permissions=frozenset(
            {
                "platform.tenant.read",
                "user.impersonate",
                "audit.read",
                "activity.read",
            }
        ),
    ),
    SystemRole(
        key="tenant_admin",
        name="Tenant Administrator",
        description=(
            "Org structure, people, configuration, reporting and native financial openings."
        ),
        scope_hint="tenant",
        permissions=frozenset(
            {
                "vouchers.read",
                "vouchers.type.manage",
                "vouchers.configuration.manage",
                "vouchers.configuration.publish",
                "vouchers.series.manage",
                "vouchers.template.manage",
                "vouchers.field.adopt",
                "vouchers.history.read",
                # Document layout is tenant-wide configuration: a shared house style
                # lives at tenant scope and every company inherits it
                # (docs/invoice-design.md §3.2).
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
                "tenant.read",
                "tenant.update",
                "tenant.subscription.manage",
                "company.create",
                "company.read",
                "company.update",
                "company.deactivate",
                # Setting a new company's books up is part of creating it: initialize its
                # authoritative `financial_setup`, generate a financial year and open a
                # FUTURE period. The 2026-10-30 user-approved opening policy adds
                # native finance/journal authority; fiscal closing stays separate.
                "accounting.finance.read",
                "accounting.finance.initialize",
                "accounting.finance.manage",
                "ledger.post_journal",
                "opening_balance.read",
                "opening_balance.manage",
                "opening_balance.initialize_zero",
                "accounting.export.read",
                "period.read",
                "period.manage",
                "period.post",
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
                "group.read",
                "group.manage",
                "role.read",
                "role.assign",
                "role.manage",
                # Permanent report administration needs the complete input read set.
                # Report/source/export jobs do not grant financial posting or approval.
                "report.read",
                "report.export",
                "report.definition.manage",
                "ledger.read",
                "accounting.head.read",
                "accounting.group.read",
                "accounting.account.read",
                "accounting.party.read",
                "accounting.setup.read",
                "custom_field.manage",
                "field_config.manage",
                "field_policy.manage",
                # `audit.read`, never `audit.read_security`: this role holds
                # `role.assign`, and the pair is a §1.4 conflict — change permissions,
                # then review your own change.
                "audit.read",
                "activity.read",
            }
        ),
    ),
    SystemRole(
        key="tenant_auditor",
        name="Tenant Auditor",
        description="Reads everything and changes nothing. For an accountant or auditor.",
        scope_hint="tenant",
        permissions=frozenset(
            {
                "accounting.batch.read",
                "accounting.stock.read",
                "accounting.serial.read",
                "vouchers.operation.read",
                "vouchers.read",
                "vouchers.counter.read",
                "vouchers.history.read",
                "vouchers.artifact.read",
                "vouchers.import.read",
                "accounting.finance.read",
                "accounting.credit.read",
                "accounting.charges.read",
                "period.read",
                "accounting.head.read",
                "accounting.group.read",
                "accounting.account.read",
                "accounting.party.read",
                "accounting.tax.read",
                "accounting.bank.read",
                "accounting.statement.read",
                "accounting.policy.read",
                "accounting.withholding.read",
                "accounting.setup.read",
                "accounting.mapping.read",
                "accounting.export.read",
                "accounting.history.read",
                "catalog.bulk.read",
                "catalog.release.read",
                "customer_pricing.read",
                "identifier_namespace.read",
                "identifier_type.read",
                "sales_channel.read",
                "warehouse.read",
                "warehouse_group.read",
                "warehouse_bin.read",
                "item_warehouse_policy.read",
                "tenant.read",
                "company.read",
                "department.read",
                "user.read",
                "group.read",
                "role.read",
                "item.read",
                "unit.read",
                "pack_type.read",
                "item_group.read",
                "category_scheme.read",
                "item_category.read",
                "product_type.read",
                "attribute_definition.read",
                "attribute_option.read",
                "attribute_set.read",
                "identifier_profile.read",
                "inventory_profile_template.read",
                "manufacturing_operation.read",
                "manufacturing_route.read",
                "bom.read",
                "promotion_stack_policy.read",
                "promotion_limit.read",
                "warranty_policy.read",
                "return_policy.read",
                "master_external_key.read",
                "master_alias.read",
                "handling_profile.read",
                "product_configuration.read",
                "brand.read",
                "brand_series.read",
                "manufacturer.read",
                "manufacturer_site.read",
                "brand_manufacturer.read",
                "price_plan.read",
                "purchase_price.read",
                "reference_cost.read",
                "tax_rule.read",
                "invoice.read",
                "credit_note.read",
                "ledger.read",
                "opening_balance.read",
                "payment.read",
                "integration.read",
                "report.read",
                "report.export",
                "audit.read",
                "audit.read_security",
                "audit.export",
                "activity.read",
                "design.template.read",
                "design.assignment.read",
                "design.asset.read",
                "design.component.read",
                # Which template version printed a given document is evidence an
                # auditor reads, never writes (docs/invoice-design.md §7).
                "design.render.read",
                "notification.provider.read",
                "notification.recipient.read",
                "notification.template.read",
                "notification.route.read",
                "notification.request.read",
                "notification.delivery.read",
            }
        ),
    ),
    SystemRole(
        key="company_admin",
        name="Company Administrator",
        description="One company's settings, people and catalogue.",
        scope_hint="company",
        permissions=frozenset(
            {
                "accounting.batch.read",
                "accounting.batch.manage",
                "accounting.stock.read",
                "accounting.stock.configure",
                "accounting.batch.hold",
                "accounting.serial.read",
                "accounting.serial.manage",
                "accounting.serial.hold",
                "vouchers.read",
                "vouchers.type.manage",
                "vouchers.configuration.manage",
                "vouchers.configuration.publish",
                "vouchers.series.manage",
                "vouchers.template.manage",
                "vouchers.field.adopt",
                "vouchers.history.read",
                # One company's own document layouts, and a test print of them
                # (docs/invoice-design.md §5).
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
                "accounting.head.read",
                "accounting.group.read",
                "accounting.account.read",
                "accounting.party.read",
                "accounting.tax.read",
                "accounting.bank.read",
                "accounting.statement.read",
                "accounting.policy.read",
                "accounting.withholding.read",
                "accounting.setup.read",
                "accounting.mapping.read",
                "accounting.export.read",
                "accounting.history.read",
                "accounting.group.manage",
                "accounting.account.manage",
                "accounting.party.manage",
                "accounting.tax.manage",
                "accounting.bank.manage",
                "accounting.statement.import",
                "accounting.statement.review",
                "accounting.bank_match.manage",
                "accounting.bank_session.finalize",
                "accounting.policy.manage",
                "accounting.withholding.manage",
                "accounting.setup.manage",
                "accounting.mapping.manage",
                "accounting.import.manage",
                "accounting.mapping.publish",
                # Creating a company is a **tenant-level** act: the route requires the
                # grant to reach the whole tenant (`identity/api/companies.py`), so this
                # key does nothing at the company scope this role is usually assigned at.
                # It is held so an administrator assigned tenant-wide can create one and
                # set its books up in a single flow (decision log 2026-10-21).
                "company.create",
                "company.read",
                "company.update",
                # Setting a new company's books up is part of creating it: initialize its
                # authoritative `financial_setup`, generate a financial year and open a
                # FUTURE period. Deliberately **not** `accounting.finance.manage`, which
                # also authorizes the opening-balance controls, nor `period.close` /
                # `period.reopen` / `period.lock` / `period.post*` — recording,
                # restating and closing stay with the controller (docs/roles-permissions.md
                # §1.4, decision log 2026-10-21).
                "accounting.finance.read",
                "accounting.finance.initialize",
                "period.read",
                "period.manage",
                # Not `company.visibility.manage`: unlisting a company is a tenant-owner
                # act, kept out of the hands of the admin of the company being unlisted
                # (docs/company.md §7).
                # Explicit first-time zero declaration only; never balance entry,
                # replacement, reopening or period closing (decision 2026-10-28).
                "opening_balance.initialize_zero",
                "company.tax_registration.manage",
                "company.statutory_id.manage",
                "company.licence.manage",
                "department.read",
                "department.manage",
                "user.read",
                "user.invite",
                "group.read",
                "group.manage",
                "role.read",
                "role.assign",
                "item.create",
                "unit.manage",
                "pack_type.manage",
                "item_group.manage",
                "item_group.move",
                "category_scheme.manage",
                "item_category.manage",
                "item_category.move",
                "product_type.manage",
                "brand.manage",
                "brand_series.manage",
                "manufacturer.manage",
                "manufacturer_site.manage",
                "brand_manufacturer.manage",
                "brand.move",
                "product_type.publish",
                "attribute_definition.manage",
                "attribute_option.manage",
                "attribute_set.manage",
                "attribute_set.publish",
                "identifier_profile.manage",
                "identifier_type.read",
                "identifier_type.manage",
                "identifier_namespace.read",
                "identifier_namespace.manage",
                "sales_channel.read",
                "sales_channel.manage",
                "inventory_profile_template.manage",
                "inventory_profile_template.publish",
                "manufacturing_operation.manage",
                "manufacturing_route.manage",
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
                "manufacturing_operation.publish",
                "manufacturing_route.publish",
                "warranty_policy.manage",
                "warranty_policy.publish",
                "return_policy.manage",
                "return_policy.publish",
                "master_alias.manage",
                "master_external_key.read",
                "master_external_key.manage",
                "handling_profile.manage",
                "handling_profile.publish",
                "product_configuration.manage",
                "product_configuration.publish",
                "product_configuration.adopt",
                "item.read",
                "unit.read",
                "pack_type.read",
                "item_group.read",
                "category_scheme.read",
                "item_category.read",
                "product_type.read",
                "attribute_definition.read",
                "attribute_option.read",
                "attribute_set.read",
                "identifier_profile.read",
                "inventory_profile_template.read",
                "manufacturing_operation.read",
                "manufacturing_route.read",
                "warranty_policy.read",
                "return_policy.read",
                "master_alias.read",
                "handling_profile.read",
                "product_configuration.read",
                "brand.read",
                "brand_series.read",
                "manufacturer.read",
                "manufacturer_site.read",
                "brand_manufacturer.read",
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
                "catalog.bulk.read",
                "catalog.bulk.manage",
                "catalog.bulk.commit",
                "catalog.release.read",
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
                "item.activate",
                "report.read",
                "audit.read",
                "activity.read",
            }
        ),
    ),
    SystemRole(
        key="salesperson",
        name="Salesperson",
        description="Prepares sales invoices and reads the sales catalogue within assigned scope.",
        scope_hint="company",
        permissions=frozenset(
            {
                "company.read",
                "item.read",
                "unit.read",
                "pack_type.read",
                "item_group.read",
                "category_scheme.read",
                "item_category.read",
                "product_type.read",
                "attribute_definition.read",
                "attribute_option.read",
                "attribute_set.read",
                "identifier_profile.read",
                "inventory_profile_template.read",
                "warranty_policy.read",
                "return_policy.read",
                "master_alias.read",
                "handling_profile.read",
                "product_configuration.read",
                "brand.read",
                "brand_series.read",
                "manufacturer.read",
                "manufacturer_site.read",
                "brand_manufacturer.read",
                "price_plan.read",
                "tax_rule.read",
                # Reads the location a sale would issue from. Which locations this
                # actor may actually see is its assignment scope, not this key
                # (docs/catalog-warehouses.md §7).
                "warehouse.read",
                # Reads the layout a sales document would print on; authoring one is
                # `design.template.manage`, which this role does not hold.
                "design.template.read",
                "invoice.create",
                "invoice.read",
                "invoice.update",
            }
        ),
    ),
    SystemRole(
        key="stock_operator",
        name="Stock Operator",
        description=(
            "Records stock and accounting entries within one company; "
            "cannot approve vouchers or close books."
        ),
        scope_hint="company",
        permissions=frozenset(
            {
                "company.read",
                "vouchers.read",
                "vouchers.create",
                "vouchers.import.read",
                "vouchers.import.manage",
                "vouchers.import.commit",
                "vouchers.edit",
                "vouchers.submit",
                "vouchers.issue",
                "vouchers.cancel",
                "vouchers.post",
                "vouchers.reverse",
                "vouchers.operation.read",
                "vouchers.operation.recover",
                "vouchers.history.read",
                # Printing what this role records (decision 2026-11-01): a posted bill
                # that cannot be printed is not a finished one. Both keys: the job is
                # created, then its protected download is read.
                "vouchers.artifact.create",
                "vouchers.artifact.read",
                "accounting.stock.read",
                "accounting.stock.post",
                "accounting.stock.reverse",
                "accounting.batch.read",
                "accounting.batch.manage",
                "accounting.serial.read",
                "accounting.serial.manage",
                "accounting.account.read",
                "accounting.group.read",
                "accounting.head.read",
                # The supplier is party data: Accounting reads the party to post against
                # a party account and to print its name ("Supplier details restricted"
                # without it). Deliberately NOT `accounting.credit.read` or
                # `accounting.policy.read`: this role cannot post a bill against a
                # supplier that has a credit or accounting policy, by design, because
                # the policy cannot be evaluated without reading it. `purchase_clerk`
                # holds both (docs/roles-permissions.md, decision 2026-11-01).
                "accounting.party.read",
                # Previewing and posting an invoice-type bill reads the tax defaults even
                # for an untaxed account bill, so without this key the company creator
                # cannot post their own Purchase (decision 2026-11-01).
                "accounting.tax.read",
                "accounting.setup.read",
                "accounting.finance.read",
                "ledger.read",
                "ledger.post_journal",
                "period.read",
                "period.post",
                "item.read",
                "unit.read",
                "pack_type.read",
                "item_group.read",
                "product_type.read",
                "identifier_profile.read",
                "inventory_profile_template.read",
                "product_configuration.read",
                "master_alias.read",
                "warehouse.read",
                "warehouse_bin.read",
                "item_warehouse_policy.read",
                "catalog.release.read",
            }
        ),
    ),
    SystemRole(
        key="purchase_clerk",
        name="Purchase Clerk",
        description=(
            "Records supplier bills, submits them and posts approved ones; "
            "cannot approve, change masters or close books. Its voucher and journal "
            "permissions are not limited to purchases, and where a voucher type needs "
            "no approval its own submit approves."
        ),
        scope_hint="company",
        # Every key below was traced to the route or domain check that refuses without
        # it (docs/purchase-e2e-review.md; test_purchase_roles.py pins the set and the
        # reason for each). Nothing is held "in case": `accounting.finance.read`,
        # `accounting.setup.read`, `report.read` and `item.read` are absent because the
        # untaxed account Purchase flow never calls anything that needs them.
        permissions=frozenset(
            {
                "company.read",
                "vouchers.read",
                "vouchers.create",
                # Also invoice-acceptance, which writes the accepted calculation hash.
                "vouchers.edit",
                "vouchers.submit",
                # A draft or submitted bill, and a posting execution still pending.
                "vouchers.cancel",
                "vouchers.post",
                "vouchers.history.read",
                # Inspect a posting and recover one that stopped, without a new identity.
                "vouchers.operation.read",
                "vouchers.operation.recover",
                # Print the bill: create the job, then read its protected download.
                "vouchers.artifact.create",
                "vouchers.artifact.read",
                # Bulk supplier-bill drafts, as the other recording role holds them. Import
                # never approves or posts (docs/voucher-import-plan.md).
                "vouchers.import.read",
                "vouchers.import.manage",
                "vouchers.import.commit",
                # The supplier lookup, its role check, and the party read the posting and
                # the print both make (the printed supplier name is party data).
                "accounting.party.read",
                # The payable and expense account lookups, and the calculation and print
                # re-reads under this actor.
                "accounting.account.read",
                # The expense account's group and head: the calculation checks the head's
                # nature, and the page verifies it before accepting the account.
                "accounting.group.read",
                "accounting.head.read",
                # The calculation, acceptance and posting of even an UNTAXED bill look up the
                # expense accounts' dated tax defaults, to prove each is NON_GST before
                # accepting it as untaxed. Refused for every actor without it, so no
                # shipped role could preview a Purchase before this key was added here.
                "accounting.tax.read",
                # Read only when the supplier has one on the posting date: its accounting
                # policy (terms, holds) and its credit policy. Without these a bill
                # against such a supplier is refused, and credit control fails closed.
                "accounting.policy.read",
                "accounting.credit.read",
                # Supplier advances: the open items a bill can be settled against and their
                # dated balances (the settlement panel). A plain bill posts without it.
                "ledger.read",
                # Posting authority the owner demands of the actor: a Purchase becomes a
                # journal. This is the same recording authority `stock_operator` holds.
                "ledger.post_journal",
                # The financial-year chip, and `assert_postable`'s OPEN-period check.
                "period.read",
                "period.post",
            }
        ),
    ),
    SystemRole(
        key="billing_clerk",
        name="Billing Clerk",
        description="Raises and posts invoices. Cannot approve its own work.",
        scope_hint="company",
        permissions=frozenset(
            {
                "vouchers.read",
                "vouchers.create",
                "vouchers.counter.operate",
                "vouchers.counter.close",
                "vouchers.edit",
                "vouchers.submit",
                "vouchers.issue",
                "vouchers.share",
                "vouchers.artifact.create",
                "vouchers.artifact.read",
                "vouchers.history.read",
                "vouchers.import.read",
                "vouchers.import.manage",
                "vouchers.import.commit",
                "invoice.create",
                "invoice.read",
                "invoice.update",
                "invoice.post",
                "credit_note.create",
                "item.read",
                "unit.read",
                "pack_type.read",
                "item_group.read",
                "category_scheme.read",
                "item_category.read",
                "product_type.read",
                "attribute_definition.read",
                "attribute_option.read",
                "attribute_set.read",
                "identifier_profile.read",
                "inventory_profile_template.read",
                "warranty_policy.read",
                "return_policy.read",
                "master_alias.read",
                "handling_profile.read",
                "product_configuration.read",
                "brand.read",
                "brand_series.read",
                "manufacturer.read",
                "manufacturer_site.read",
                "brand_manufacturer.read",
                "price_plan.read",
                "tax_rule.read",
                "warehouse.read",
                # Issuing a document prints it: this role reads the resolved layout and
                # records which template version produced the artifact
                # (docs/invoice-design.md §7). It cannot author or publish a layout.
                "design.template.read",
                "design.render.record",
                "design.render.read",
                "period.post",
                "ledger.read",
                "report.read",
                "activity.read",
            }
        ),
    ),
    SystemRole(
        key="billing_approver",
        name="Billing Approver",
        description="Approves what clerks raise. Cannot create.",
        scope_hint="company",
        permissions=frozenset(
            {
                "vouchers.read",
                "vouchers.counter.read",
                "vouchers.counter.supervise",
                "vouchers.counter.close",
                "vouchers.approve",
                "vouchers.reject",
                "vouchers.accept",
                "vouchers.decline",
                "vouchers.artifact.read",
                "vouchers.history.read",
                # Seeing what is being approved and where its posting stands. Still no
                # create, edit, submit or post: `vouchers.create` + `vouchers.approve`
                # is a §1.4 pair (decision 2026-11-01).
                "vouchers.operation.read",
                # The Purchase page renders the supplier and the accounts of a bill
                # through these reads; an approver that cannot see the supplier name or
                # the accounts is approving blind. Reads only, field policy still applies.
                "accounting.party.read",
                "accounting.account.read",
                "accounting.group.read",
                "accounting.head.read",
                "invoice.read",
                "invoice.approve",
                "invoice.cancel",
                "credit_note.read",
                "credit_note.approve",
                # Approving a document includes seeing the layout it will print on and
                # which version printed it; it authors neither.
                "design.template.read",
                "design.render.read",
                "ledger.read",
                "report.read",
            }
        ),
    ),
    SystemRole(
        key="accounts_clerk",
        name="Accounts Clerk",
        description="Receipts and allocation. Initiates refunds; does not approve them.",
        scope_hint="company",
        permissions=frozenset(
            {
                "accounting.finance.read",
                "accounting.credit.read",
                "accounting.charges.read",
                "period.read",
                "payment.read",
                "payment.record",
                "payment.allocate",
                "payment.refund",
                "invoice.read",
                "ledger.read",
                "period.post",
                "report.read",
                "activity.read",
            }
        ),
    ),
    SystemRole(
        key="controller",
        name="Controller",
        description="The accounting authority. Closes the books; records no transactions.",
        scope_hint="company",
        permissions=frozenset(
            {
                "vouchers.read",
                "vouchers.counter.read",
                "vouchers.counter.supervise",
                "vouchers.counter.close",
                "vouchers.approve",
                "vouchers.reject",
                "vouchers.cancel",
                "vouchers.expire",
                "vouchers.operation.read",
                "vouchers.operation.recover",
                "vouchers.export",
                "vouchers.artifact.read",
                "vouchers.history.read",
                "accounting.head.read",
                "accounting.group.read",
                "accounting.account.read",
                "accounting.party.read",
                "accounting.tax.read",
                "accounting.bank.read",
                "accounting.statement.read",
                "accounting.policy.read",
                "accounting.withholding.read",
                "accounting.setup.read",
                "accounting.mapping.read",
                "accounting.export.read",
                "accounting.history.read",
                "accounting.group.manage",
                "accounting.account.manage",
                "accounting.party.manage",
                "accounting.tax.manage",
                "accounting.bank.manage",
                "accounting.statement.import",
                "accounting.statement.review",
                "accounting.bank_match.manage",
                "accounting.bank_session.finalize",
                "accounting.policy.manage",
                "accounting.withholding.manage",
                "accounting.setup.manage",
                "accounting.mapping.manage",
                "accounting.import.manage",
                "accounting.mapping.publish",
                "accounting.finance.read",
                "accounting.credit.read",
                "accounting.charges.read",
                "accounting.finance.manage",
                "accounting.credit.manage",
                "accounting.credit.override_approve",
                "accounting.charges.manage",
                "accounting.charges.approve",
                "period.read",
                "period.manage",
                "period.close",
                "period.reopen",
                "period.post_adjustment",
                # Not `period.lock`: locking follows a statutory filing and is
                # irreversible (docs/fiscal-year.md §3). Assigned deliberately, to a
                # named individual, and holding it here would also pair with
                # `opening_balance.manage` as a §1.4 conflict.
                "opening_balance.read",
                "opening_balance.manage",
                "exchange_rate.manage",
                "ledger.read",
                "ledger.post_journal",
                "payment.refund_approve",
                "invoice.read",
                "design.template.read",
                "design.render.read",
                "report.read",
                "report.export",
                "audit.read",
            }
        ),
    ),
    SystemRole(
        key="viewer",
        name="Viewer",
        description="Read-only within its scope. Replaces the vaguer 'member'.",
        scope_hint="company",
        permissions=frozenset(
            {
                "vouchers.read",
                "accounting.finance.read",
                "accounting.credit.read",
                "accounting.charges.read",
                "period.read",
                "company.read",
                "department.read",
                "user.read",
                "item.read",
                "unit.read",
                "pack_type.read",
                "item_group.read",
                "category_scheme.read",
                "item_category.read",
                "product_type.read",
                "attribute_definition.read",
                "attribute_option.read",
                "attribute_set.read",
                "identifier_profile.read",
                "inventory_profile_template.read",
                "warranty_policy.read",
                "return_policy.read",
                "master_alias.read",
                "handling_profile.read",
                "product_configuration.read",
                "brand.read",
                "brand_series.read",
                "manufacturer.read",
                "manufacturer_site.read",
                "brand_manufacturer.read",
                "price_plan.read",
                "warehouse.read",
                "design.template.read",
                "invoice.read",
                "payment.read",
                "ledger.read",
                "report.read",
                "activity.read",
            }
        ),
    ),
    SystemRole(
        key="customer_portal",
        name="Customer Portal",
        description="A customer's own records only. Object scope does the narrowing.",
        scope_hint="company",
        #: Paired with `user_type = customer_portal_user`. "Own records" is **not** in
        #: these keys and cannot be: it is an object-level scope check on every request
        #: (CLAUDE.md §5.2), never the role alone.
        permissions=frozenset(
            {
                "invoice.read",
                "invoice.export",
                "payment.read",
                "payment.record",
            }
        ),
    ),
)

SYSTEM_ROLE_KEYS: Final[frozenset[str]] = frozenset(role.key for role in SYSTEM_ROLES)


def get(key: str) -> SystemRole:
    """One shipped role by key. ``KeyError`` for an unknown one, like a mapping."""
    for role in SYSTEM_ROLES:
        if role.key == key:
            return role
    raise KeyError(f"no system role with key {key!r}")


def read_permissions() -> frozenset[str]:
    """Every catalogue key whose final segment is ``read``.

    ``audit.read_security`` is deliberately excluded — it is a distinct authority over
    the security trail, not the read companion of a resource — which is why the check is
    on the final segment rather than a ``.read`` substring.
    """
    return frozenset(key for key in PERMISSIONS if key.rsplit(".", 1)[-1] == "read")


def _validate_catalogue(roles: tuple[SystemRole, ...] = SYSTEM_ROLES) -> None:
    """Boot checks. Each one is a failure mode that is invisible at runtime.

    Takes ``roles`` so the guards themselves are testable with a crafted bad catalogue —
    the real one is validated at import by the no-argument call below.
    """
    keys = [role.key for role in roles]
    repeated = sorted(key for key, count in Counter(keys).items() if count > 1)
    if repeated:
        raise ValueError(f"duplicate system role keys: {repeated}")

    for role in roles:
        if not _KEY_PATTERN.match(role.key):
            raise ValueError(f"malformed system role key: {role.key!r}")
        if role.scope_hint not in SCOPE_HINTS:
            raise ValueError(
                f"system role {role.key!r} has scope_hint {role.scope_hint!r}, "
                f"not one of {sorted(SCOPE_HINTS)}"
            )
        if not role.permissions:
            raise ValueError(f"system role {role.key!r} grants nothing")
        for permission in sorted(role.permissions):
            assert_known_permission(permission, named_by=f"system role {role.key!r}")

        conflicts = separation_of_duties_conflicts(role.permissions)
        if conflicts:
            pairs = ", ".join(f"{first} + {second}" for first, second in conflicts)
            raise ValueError(
                f"system role {role.key!r} combines duties that must stay separate: {pairs} "
                "(docs/roles-permissions.md §1.4)"
            )

    auditor_role = next((role for role in roles if role.key == "tenant_auditor"), None)
    if auditor_role is None:
        return
    auditor = auditor_role.permissions
    unclassified = sorted(read_permissions() - auditor - READS_WITHHELD_FROM_AUDITOR)
    if unclassified:
        raise ValueError(
            f"tenant_auditor neither holds nor withholds: {unclassified}. Add each to the "
            "role or to READS_WITHHELD_FROM_AUDITOR — 'read everything' has to mean it"
        )

    withheld_but_held = sorted(READS_WITHHELD_FROM_AUDITOR & auditor)
    if withheld_but_held:
        raise ValueError(f"tenant_auditor both holds and withholds: {withheld_but_held}")


_validate_catalogue()
