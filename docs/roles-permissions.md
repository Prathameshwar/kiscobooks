# Permission Catalogue & System Roles

**Status:** Implemented — catalogue in `libs/platform`, roles in `identity/domain/system_roles.py`, seed in `seeds/roles/`
**Date:** 2026-09-03
**Master:** `identity` · **Seeded by:** `seeds/roles/` (Phase 5)
**Related:** [org-model.md](org-model.md) §2.3, §5 · [fiscal-year.md](fiscal-year.md) §3 · [audit.md](audit.md) §5.1 · [custom-fields.md](custom-fields.md) §9 · [field-permissions.md](field-permissions.md)

Consolidates the permission keys defined piecemeal across the other docs, and defines the preloaded system roles.

Decision 2026-10-28, explicitly confirmed by the user: Company Administrator also
receives `opening_balance.initialize_zero`. It permits an explicit first-time
zero-opening declaration at the authoritative books begin date after that period
is opened. The native company lock, current setup version and field policies
apply. Any historical opening (including voided/reversed records), journal,
physical posting, first posting or prepared/committed money intent prevents this
action. The request accepts only a reason and expected setup version. It cannot
supply accounts, amounts, bills, dates or replacements; it grants no opening
entry, void/reopen, approval, journal recording or period-closing authority.
The controller's existing broader workflows remain available. This is an
explicit confirmation in Company readiness, never an automatic zero assumption.

---

## 1. Principles

### 1.1 A role is a permission set. Scope is separate.

Do **not** create `billing_clerk_company_a` and `billing_clerk_company_b`. That is **one** role assigned at two company scopes ([org-model.md](org-model.md) §2.3).

**Create a new role only when the permission set genuinely differs.** This is what keeps the role list from growing to fifty entries nobody can audit.

### 1.2 System roles are read-only

`role.tenant_id = SCOPE_ALL` marks a system role. Tenants **cannot edit them** — an upgrade that adds a permission to a shipped role must not be silently reverted by a tenant's edit, and we must be able to rely on a role's contents.

`tenant_id` is `NOT NULL` and a system role carries the all-zero UUID sentinel rather than `NULL` ([identity-db-plan.md](identity-db-plan.md) §2): MariaDB treats `NULL`s inside a `UNIQUE` index as distinct, so with a nullable column `billing_clerk` could be shipped any number of times. `is_system` is **derived** from that column, never stored — a stored flag can disagree with `tenant_id`, and `is_system = false` on a platform-wide row is a role every tenant may edit.

"Customising" a system role means **cloning it into a tenant role**, then editing the copy. The UI should make that the obvious path.

### 1.3 `user_type` is not a role

`user_type = platform_admin` decides which application surface a principal sees. The `platform_admin` **role** decides what they may do. Both exist, and neither substitutes for the other ([org-model.md](org-model.md) §3.1). A platform admin needs the user_type *and* the role assignment.

### 1.4 Separation of duties

The point of preloading roles is to get this right by default. These pairs must **not** be held by one role out of the box:

| Must not combine | Why |
|---|---|
| `invoice.create` + `invoice.approve` | Self-approval defeats the control entirely |
| `invoice.post` + `period.close` | The person recording transactions must not decide when the books shut |
| `payment.refund` + `payment.refund_approve` | Money leaving the business on one signature |
| `role.assign` + `audit.read_security` | Change permissions, then review your own change |
| `opening_balance.manage` + `period.lock` | Restate the prior year and seal it in one action |

There is deliberately **no audit-management permission in the catalogue**, which is why the fourth row names `audit.read_security` rather than "`audit.*` management": the audit trail is immutable by database grant, not by convention ([audit.md](audit.md) §4.1), and retention runs as a privileged job outside the permission model. The half of the rule the catalogue can express is independence of review.

A tenant may deliberately combine these in a custom role — small businesses often must. The UI should **warn** on the combination, and the combination itself should be an `admin`-category audit event. A **system** role holding a pair is the opposite case and fails the boot (§7, resolved).

### 1.5 Privilege escalation guards

Non-negotiable, enforced in `identity`:

1. **You cannot assign a role containing a permission you do not hold.** Without this, `role.assign` is equivalent to every permission in the system. Measured at the scope of the assignment, so a clerk who holds `invoice.post` in company A cannot pass it on in company B.
2. **You cannot modify your own role assignments.** Not your own, not via a group you belong to. Checked before anything else, so the answer never depends on what the actor holds.
3. **You cannot assign at a scope broader than your own.** A company admin cannot grant anything at tenant scope — nor on another company, which breadth alone would not catch.
4. Every assignment change is a `security`-category audit event ([audit.md](audit.md) §3).

Company-creator bootstrap exception (approved 2026-10-27): a successful
tenant-authorised company creation atomically assigns its creator the fixed,
installation-owned `company_admin` role at the new company's scope. Company,
assignment and security outbox evidence commit together; unavailable/inactive
system roles abort creation. The client cannot choose a role, subject or broader
scope. This grants no tenant-wide business authority and does not change ordinary
self-assignment or held-permission guards. A bounded maintenance correction for a
legacy company must verify the exact active company's original creator and tenant,
require current tenant-level `company.create`, preserve revoked/expired/scheduled
assignments, and emit the same security evidence. See
[company-owner-access.md](company-owner-access.md).

Stock workflow extension, approved 2026-10-28: the same creation transaction also
grants the fixed `stock_operator` role to the original creator at this company's
scope. Both installed role permission sets must match the code catalogue exactly.
Both grants are audited atomically; missing roles abort creation, and existing
revoked, expired or scheduled assignments are preserved. The role provides native
stock draft/post/reverse and required Catalog/Accounting reads, `period.post` and
`ledger.post_journal`. The latter also permits accounting journal recording; this
is company-scoped recording authority, not merely configuration. It grants no
voucher approval, period close/reopen/lock, role administration or tenant-wide
business authority. Company Administrator remains the setup role. Administrators
can assign the Stock Operator role to other users only through the existing scope,
held-permission and self-assignment guards. The authorisation applies to future
company creation and the user-approved bounded legacy creator correction.

Opening-stock API decision, 2026-10-28: Stock Operator also holds the existing
`vouchers.import.read`, `vouchers.import.manage` and `vouchers.import.commit`
permissions to prepare durable opening drafts. Native draft/type/field checks
still apply, and import does not approve or post a voucher. This adds no
`accounting.finance.manage` or voucher approval: nonzero cutover registration,
replacement, adoption and finalization remain financial-controller actions.

All three apply to **revocation** as well as granting. Revoking is de-escalation for the subject and escalation for nobody, but revoking the controller's role the evening before a close is an outage on one API call, so the authority required is the same in both directions.

Guard 1 also applies one step earlier, when a tenant **composes** a role out of the catalogue: a role may not be built from a permission its author does not hold. Implemented in `identity/domain/authorization.py`; there is no `system=True` bypass. The fixed tenant and company bootstrap exceptions use separate bounded call sites, not ordinary role-composition or assignment APIs.

**The guards follow the effective grant, not the endpoint** (corrected 2026-10-22, after
the [access-control review](access-control-review.md)). Three paths change what someone
may do without being an assignment call, and each now runs the same three guards:

- **Editing a role that is assigned.** `PATCH /v1/roles/{id}` replaces a permission set
  that live grants resolve through, so it is checked against every active, unexpired
  assignment of that role — scheduled ones included — over the union of the old and new
  key sets, so a *removal* cannot bypass the checks either. The practical consequence is
  that **`role.manage` alone edits only an unassigned role**: editing one that is in use
  additionally requires `role.assign` at each affected assignment's scope, and refuses an
  assignment to the editor or to a group they belong to. Role metadata — name,
  description, `scope_hint` — stays editable with `role.manage` alone.
- **Group membership and group lifecycle**, where a group carries role assignments or
  field policies ([field-permissions](field-permissions.md) §13).
- **Assigning, revoking or regranting a role that carries field policies**, for the same
  reason.

An unassigned role remains a composition-only operation. Policy and assignment scans are
bounded at 1,000 rows and report a validation failure above it, which is a processing
bound rather than a quota on how many a tenant may hold.

### 1.6 Platform admins do not get blanket tenant data access

Tenant-administrator access decision (2026-10-25, user requested): configured platform operators use the dedicated `/v1/platform/access` boundary with `platform.tenant_access.read` and `.manage`. It lists a lean customer-tenant selector and only direct user assignments of the installation-owned `tenant_admin` system role at tenant scope. It can invite administrators, edit display names, suspend/restore accounts, revoke/restore that fixed assignment and resend invitations. It cannot promote an existing ordinary user, edit arbitrary roles or grant ordinary `user.*` / `role.*` authority to platform admins. The operating workspace is excluded. Closed tenants are read-only; removing the last effective active administrator is refused. Writes require fresh verified authentication, optimistic timestamps, idempotent receipts, tenant locking and transactional tenant/platform audits. Verified invitation acceptance still controls activation. This bounded exception to the held-permission delegation guard in section 1.5 leaves ordinary tenant/company guards mandatory. The role and permission catalogue are read-only in this UI. The default platform-admin seed receives both keys; tenant auditors and platform support do not receive them.

A cross-tenant read path is a breach waiting for one bug. `platform_admin` manages tenants, plans, and system configuration — **not their business data**.

Support access to tenant data is via **time-bound, audited impersonation** (`user.impersonate`), which records `on_behalf_of_user_id` on every resulting audit row ([audit.md](audit.md) §3). The tenant can see who entered their data and when. A permanent cross-tenant grant cannot offer that.

The console's **My access** self-read shows the signed-in person's scoped grants
and effective permissions without administrative directory authority. Users,
roles, assignments and catalogue navigation depend on actual live grants, never
an administrator label. The company people projection and invitation workflow
are described in [org-model](org-model.md#22-users-attach-to-the-tenant-not-the-company).

Assignment creation now offers `POST /v1/role-assignments/check`: a non-mutating
preview that uses the same lifecycle, scope, held-permission, group/self and field
delegation checks as the grant. The final grant repeats every check. A successful
preview is not a token or a persisted authorization decision (2026-10-24).

Platform administrative history uses the operator's operating tenant and exact
Identity event families under existing tenant-scoped `platform.account.read`,
`platform.tenant.read` and `platform.config.manage` grants. It requires configured
operator verification and live grants at the gateway. It grants no tenant business
audit access, general audit permission, export or impersonated platform authority.
See [Audit platform history](audit.md#511-platform-administrative-history).

---

## 2. Permission catalogue

Keys are `resource.action`, defined **in code** as a fixed catalogue — never rows an admin can invent ([org-model.md](org-model.md) §5.3). Keys are immutable once shipped; they appear in assignments.

**Platform**
```
platform.tenant.create      platform.tenant.read      platform.tenant.suspend
platform.tenant_access.read            platform.tenant_access.manage
platform.account.read       platform.account.review
platform.plan.manage        platform.config.manage
```

**Tenant & org** — `identity`
```
tenant.read                 tenant.update             tenant.subscription.manage
company.create              company.read              company.update            company.deactivate
company.tax_registration.manage       company.statutory_id.manage
company.licence.manage                company.visibility.manage
department.read             department.manage
user.invite                 user.read                 user.update               user.deactivate
user.impersonate
group.read                  group.manage
role.read                   role.assign               role.manage
custom_field.manage         field_config.manage       field_policy.manage
```

`field_config.manage` and `field_policy.manage` are deliberately separate keys. `field_config.manage` is **form layout** — show/hide, order, label, requiredness — an administrative task, grantable at company scope. `field_policy.manage` is **field access control**, tenant scope only, and a `security`-category audit event. Granting the first must never imply the second ([identity-schema.md](identity-schema.md) §6.2).

**Catalog**
```
catalog.bulk.read   catalog.bulk.manage   catalog.bulk.commit
unit.read        unit.manage
pack_type.read   pack_type.manage
item_group.read  item_group.manage  item_group.move
category_scheme.read  category_scheme.manage
item_category.read  item_category.manage  item_category.move
product_type.read  product_type.manage  product_type.publish
attribute_definition.read  attribute_definition.manage
attribute_option.read  attribute_option.manage
attribute_set.read  attribute_set.manage  attribute_set.publish
identifier_profile.read  identifier_profile.manage
inventory_profile_template.read  inventory_profile_template.manage  inventory_profile_template.publish
warranty_policy.read  warranty_policy.manage  warranty_policy.publish
return_policy.read  return_policy.manage  return_policy.publish
handling_profile.read  handling_profile.manage  handling_profile.publish
manufacturing_operation.read  manufacturing_operation.manage  manufacturing_operation.publish
manufacturing_route.read  manufacturing_route.manage  manufacturing_route.publish
promotion_limit.read  promotion_limit.manage  promotion_limit.publish
master_alias.read  master_alias.manage
master_external_key.read  master_external_key.manage
brand.read  brand.manage  brand.move
brand_series.read  brand_series.manage
manufacturer.read  manufacturer.manage
manufacturer_site.read  manufacturer_site.manage
brand_manufacturer.read  brand_manufacturer.manage
item.create   item.read   item.update   item.deactivate   item.activate
product_configuration.read   product_configuration.manage
product_configuration.publish   product_configuration.adopt
price_plan.read            price_plan.manage
price_plan.publish         price_plan.override
purchase_price.read        purchase_price.manage
reference_cost.read        reference_cost.manage
tax_rule.read              tax_rule.manage              tax_rule.publish
warehouse.read   warehouse.manage   warehouse.publish   warehouse.deactivate
warehouse_group.read  warehouse_group.manage  warehouse_group.move
warehouse_bin.read  warehouse_bin.manage
item_warehouse_policy.read  item_warehouse_policy.manage
catalog.release.read
```

The stock-location keys govern **definitions**, never a stock movement, which is Billing's
([catalog-warehouses.md](catalog-warehouses.md)). `warehouse.publish` publishes an operation-policy
revision; `warehouse.deactivate` is separate from `.manage` because deactivation is fenced behind a
consumer acknowledgement and is the one location action that can strand stock. There is no write key
for acknowledgement: a consumer's activation evidence arrives as source-only ingestion, so no client
can claim its own policy is enforced. `item_warehouse_policy.manage` covers per-SKU location
allowlists and per-location replenishment targets together — the same definition, the same role, and
no separation-of-duties reason to split them.

**Billing**
```
invoice.create   invoice.read   invoice.update   invoice.post
invoice.approve  invoice.cancel invoice.export
credit_note.create          credit_note.read          credit_note.post          credit_note.approve
ledger.read                 ledger.post_journal
opening_balance.read        opening_balance.manage
exchange_rate.manage
period.post                 period.post_adjustment
period.close                period.reopen             period.lock
```

**Payments**
```
payment.read     payment.record   payment.allocate
payment.refund   payment.refund_approve
integration.read integration.manage
```

**Reports**
```
report.read      report.export    report.definition.manage
```

**Audit**
```
audit.read       audit.read_security       audit.export      activity.read
```

**Design** — document layout, the entities in [invoice-design.md](invoice-design.md)
```
design.template.read        design.template.manage       design.template.publish
design.assignment.read      design.assignment.manage
design.asset.read           design.asset.manage
design.component.read       design.component.manage
design.render.read          design.render.record
```

`manage` and `publish` are separate for the same reason `vouchers.configuration.manage`
and `.publish` are: the act that makes a draft the layout every future document renders
from is its own grant. `design.render.record` writes print evidence, so it belongs to
whoever *issues* documents — a billing clerk holds it, a designer does not. Authoring a
tenant-wide house style needs the same key at **tenant** scope; a company-scoped grant
reaches only that company's designs (invoice-design.md §3.2).

**Notification** — the entities in [notification.md](notification.md)
```
notification.provider.read      notification.provider.manage
notification.recipient.read     notification.consent.manage       notification.suppression.manage
notification.template.read      notification.template.manage
notification.route.read         notification.route.manage
notification.request.read       notification.delivery.read        notification.delivery.retry
```

`notification` has no synchronous send API — send commands arrive over RabbitMQ ([tech-stack.md](tech-stack.md) §7) — so there is no `notification.send` key. What these grant is configuration and operational visibility: reading a delivery attempt, retrying a failed one, managing consent and suppression.

Services extend their own namespace. Additions are code changes, reviewed like any other.

---

## 3. Your list, mapped

| You suggested | Recommendation |
|---|---|
| platform admin | ✅ `platform_admin` — with §1.6's constraint: no tenant data access |
| tenant admin | ✅ `tenant_admin` |
| company admin | ✅ `company_admin` |
| member | ⚠️ Rename **`viewer`**. "Member" says who someone is, not what they may do — that is what `membership` records |
| billing user | ⚠️ **Split** into `billing_clerk` and `billing_approver` (§1.4). One role that creates and approves its own invoices is not a control |
| account user | ⚠️ **Split** into `accounts_clerk` and `controller`. Recording payments and closing periods are different authorities |
| guest | ❌ **Drop.** Too vague to grant safely. Replaced by `customer_portal` (sees only their own invoices) and `external_auditor` (read-only, time-bound) |

---

## 4. System roles — v1 seed set

Fourteen roles (the 2026-11-01 Purchase decision adds `purchase_clerk`; `stock_operator`,
added 2026-10-28, is listed below). The catalogue is
`identity/domain/system_roles.py`, which lists every key **literally** — no wildcards,
because two readers would expand `audit.*` differently — and validates itself at import,
so a key absent from §2, a duplicate role key, a §1.4 pair or an unclassified `.read`
permission fails the boot.

### Platform scope

**`platform_admin`** — manages the platform, not the data.
```
platform.*  ·  tenant.read
```

**`platform_support`** — read-only plus audited impersonation. No money writes.
```
platform.tenant.read  ·  user.impersonate  ·  audit.read  ·  activity.read
```

### Tenant scope

**`tenant_admin`** — org structure, people, configuration, complete-company reporting and native financial opening administration.
```
tenant.read  tenant.update  tenant.subscription.manage
company.*  (including visibility.manage)  ·  department.read  department.manage
user.invite  user.read  user.update  user.deactivate  ·  group.read  group.manage
role.read  role.assign  role.manage
custom_field.manage  ·  field_config.manage  ·  field_policy.manage
audit.read  ·  activity.read
```

Permanent report administration (decision 2026-10-29) also includes
`report.read`, `report.export`, `report.definition.manage` and the complete input
read set: `ledger.read`, `accounting.head.read`, `accounting.group.read`,
`accounting.account.read`, `accounting.party.read`, `accounting.setup.read`,
`accounting.finance.read` and `period.read`. Source refresh, calculation and
private exports are reporting operations. The subsequent opening policy below adds
native finance/journal posting authority. Voucher approval/posting, period
closing/reopening, impersonation and security-audit self-review remain separate.

Permanent opening administration (user-approved decision 2026-10-30) additionally
includes `accounting.finance.manage`, `ledger.post_journal`, `period.post`,
`accounting.export.read`, `opening_balance.read`, `opening_balance.manage` and
`opening_balance.initialize_zero`. The native opening workflow uses these existing
keys for capture, imports, journal posting, corrections and exports. They also
authorize native finance management and direct journal operations; this is not an
opening-only permission family. Fiscal status, company scope, field denies,
first-posted invariants, audit and idempotency remain enforced by the owner.
`company_admin` keeps its bounded bootstrap policy. No close, reopen, lock,
adjustment, voucher approval/post, impersonation or security-audit grant is added.
Existing and future assignments use the same canonical role and the fixed-catalogue
update workflow described below; no per-user QA grant is required.

Existing installations apply the shipped catalogue through the fresh configured
platform operator's `/v1/platform/system-roles` preview and `/reconcile` command.
The command requires both preview fingerprints, a reason and an idempotency key;
it invokes the fixed seed and records an actor-referenced transactional audit event.
Custom roles and all assignments are preserved. Ordinary role composition and
self-access guards remain unchanged; broad permission-cache updates follow the
documented TTL. This is a permanent system-role update for existing and future tenants.

**Not** `user.impersonate`, though §2's `user.*` would include it. Impersonation is the one permission that converts an org-administration role into every other role: a tenant admin could impersonate the controller and close a period, defeating §1.4 entirely. `platform_support` holds it instead, time-bound and audited (§1.6).

**Not** `audit.read_security` either — this role holds `role.assign`, and the pair is the §1.4 conflict above.

**`tenant_auditor`** — read everything, change nothing. The role you give an accountant or an internal auditor.
```
every *.read key in §2 except platform.tenant.read and platform.account.read  ·  report.export
audit.read  audit.read_security  audit.export
```

"Every `.read` key" is enforced: the catalogue check fails boot on a read permission this role neither holds nor withholds. `platform.tenant.read` and `platform.account.read` are withheld because a tenant auditor cannot inspect other tenants or the installation's registration queue (§1.6).

### Company scope

**`company_admin`** — one company's settings and people.
```
company.read  company.update  ·  department.read  department.manage
company.tax_registration.manage  company.statutory_id.manage  company.licence.manage
user.read  user.invite  ·  group.read  group.manage  ·  role.read  role.assign
item.*  ·  price_plan.read  price_plan.manage  price_plan.publish  price_plan.override
purchase_price.read  purchase_price.manage  reference_cost.read  reference_cost.manage
tax_rule.read  tax_rule.manage  tax_rule.publish  item.activate
report.read  ·  audit.read  ·  activity.read
```

The `.read` companions of the `manage` keys are granted explicitly: manage without read is not a workflow, the same omission as the missing `credit_note.read`.

**Not** `company.visibility.manage` — unlisting a company is a tenant-owner act, deliberately kept out of the hands of the admin of the company being unlisted ([company.md](company.md) §7).

Catalogue seed correction (2026-10-27): Company Administrator also receives the
existing `identifier_type.read/manage`, `identifier_namespace.read/manage` and
`sales_channel.read/manage` keys. These company-owned masters were omitted from
the shipped role. Tenant Auditor already has their read keys; no other role gains
write authority. Accounting charge operations remain with the existing accounting
roles. Re-run the idempotent role seed on deployment; no schema migration is needed.

**`salesperson`** ? prepares sales invoices and reads catalogue data within the assigned scope.
```
company.read
item.read  unit.read  pack_type.read  item_group.read  category_scheme.read  item_category.read
price_plan.read  tax_rule.read
invoice.create  invoice.read  invoice.update
```

Company scope is the suggested assignment. Assign explicitly; installation only creates the
role and its permission bindings. The role has no invoice posting/approval/cancellation/export,
credit-note, payment, ledger, reporting, role-management, or master-data write permissions.
The existing assignment guards require the assigner to hold every granted permission at the
target scope. Extra responsibilities require an additional or cloned tenant role.

This is a permission bundle, not a new sales workflow. Billing must enforce draft-only edits
and native pricing/discount rules when its invoice endpoints are implemented. There is no
customer API or `customer.read` key in the current catalogue, and no salesperson-to-customer
assignment model; customer-specific access remains pending that implementation. The role does
not imply access only to the salesperson's own invoices: assignment scope is company/department.

**`stock_operator`** — records stock and accounting entries within one company. Cannot approve vouchers or close books. Granted to the company's creator with `company_admin` (§1.5, [company-owner-access](company-owner-access.md)).
```
vouchers.read  create  edit  submit  issue  cancel  post  reverse  history.read
vouchers.operation.read  operation.recover  ·  vouchers.import.read  import.manage  import.commit
vouchers.artifact.create  vouchers.artifact.read              (2026-11-01: print what it records)
accounting.stock.read  stock.post  stock.reverse  ·  batch.read  batch.manage  ·  serial.read  serial.manage
accounting.account.read  group.read  head.read  setup.read  finance.read
accounting.party.read  accounting.tax.read                    (2026-11-01: the supplier is party data; previewing a bill reads tax defaults)
ledger.read  ledger.post_journal  ·  period.read  period.post  ·  company.read
item.read  unit.read  pack_type.read  item_group.read  product_type.read  identifier_profile.read
inventory_profile_template.read  product_configuration.read  master_alias.read
warehouse.read  warehouse_bin.read  item_warehouse_policy.read  catalog.release.read
```

**`purchase_clerk`** — records supplier bills, submits them and posts approved ones. Cannot approve, change masters or close books. Added 2026-11-01 ([purchase-e2e-review](purchase-e2e-review.md) D4).
```
company.read
vouchers.read  create  edit  submit  cancel  post  history.read  operation.read  operation.recover
vouchers.artifact.create  vouchers.artifact.read  ·  vouchers.import.read  import.manage  import.commit
accounting.party.read  account.read  group.read  head.read  tax.read  policy.read  credit.read
ledger.read  ledger.post_journal  ·  period.read  period.post
```

Every key was traced to the route or domain check that refuses without it, and the set is pinned
by `identity/tests/test_purchase_roles.py`. Why the non-obvious ones are there: `accounting.party.read`
is the supplier (the lookup, the posting's party-account check and the printed name);
`accounting.group.read` and `head.read` are the expense account's group and head, which the calculation
reads; `accounting.tax.read` is demanded of every actor by the calculation of even an *untaxed* bill (it
proves each expense account's dated tax default is non-GST), so no role could preview a Purchase before
it was granted here; `accounting.policy.read` and `credit.read` are read only when the supplier has an
accounting policy or a credit policy on the posting date; `ledger.read` covers supplier advances (open items
and their balances), `ledger.post_journal` and `period.post` are the posting authority the owner and
`assert_postable` demand of the actor; `period.read` is the financial-year chip. **Absent on purpose:**
`vouchers.approve` / `reject` (`vouchers.create` + `vouchers.approve` is a §1.4 pair), `vouchers.reverse`
and `issue` (Purchase reversal is not implemented; a bill has no issue step), every `.manage` key,
`accounting.finance.*`, `accounting.setup.read`, `report.read`, `item.read` and `design.*` (print layout
is resolved service to service, never as the actor), and every `period.close` / `reopen` / `lock` /
`post_adjustment` / `manage` key. Goods and taxed Purchases are out of scope (D8) and will need item and
tax-registration reads when they are built. It is **not** granted automatically to anyone, including the
company creator; an administrator assigns it, at company scope, through the ordinary guards.

**`billing_clerk`** — raises and posts invoices. Cannot approve its own work, cannot close periods. It is the **Sales** role and deliberately stays one: it holds none of the Accounting master reads or `vouchers.post`, so Purchase work goes to `purchase_clerk` (2026-11-01).
```
invoice.create  invoice.read  invoice.update  invoice.post
credit_note.create  ·  item.read  price_plan.read  tax_rule.read
period.post  ·  ledger.read  ·  report.read  ·  activity.read
```

**`billing_approver`** — approves what clerks raise. Cannot create.
```
invoice.read  invoice.approve  invoice.cancel
credit_note.read  credit_note.approve  ·  ledger.read  ·  report.read
vouchers.operation.read                                       (2026-11-01)
accounting.party.read  account.read  group.read  head.read    (2026-11-01: render the bill it approves)
```

**`accounts_clerk`** — receipts and allocation. Refunds are initiated here, approved elsewhere.
```
payment.read  payment.record  payment.allocate  payment.refund
invoice.read  ·  ledger.read  ·  period.post  ·  report.read  ·  activity.read
```

**`controller`** — the accounting authority. Closes the books; does not record transactions.
```
period.close  period.reopen  period.post_adjustment
opening_balance.read  opening_balance.manage  ·  exchange_rate.manage
ledger.read  ledger.post_journal  ·  payment.refund_approve
invoice.read  ·  report.read  report.export  ·  audit.read
```

`period.lock` is **not** granted to `controller` by default — locking follows a statutory filing and is irreversible ([fiscal-year.md](fiscal-year.md) §3). Assign it deliberately, to a named individual.

**`viewer`** — read-only within its scope. Replaces "member".
```
company.read  department.read  user.read  item.read  price_plan.read
invoice.read  payment.read  ledger.read  report.read  activity.read
```

### Special principals

**`customer_portal`** — paired with `user_type = customer_portal_user`. Sees only its own records; enforced by object-scope checks (CLAUDE.md §5.2), never by the role alone.
```
invoice.read  invoice.export  payment.read  payment.record
```

"Own" is deliberately absent from the keys and cannot be expressed in one: it is an object-level scope check on every request. Seeded like the other system roles (§7, resolved) — a portal user with no role would be a second authorization path with no catalogue behind it.

---

## 5. Add when needed

Not seeded in v1 — create when the requirement is real, so the initial list stays reviewable.

| Role | When |
|---|---|
| `tenant_config_admin` | If configuration authority should be split out of `tenant_admin` — recommended once more than a handful of users exist |
| `payments_operator` | When gateway reconciliation and refund operations outgrow `accounts_clerk` |
| `external_auditor` | Year-end audit. Read-only + `audit.read`, time-bound via `role_assignment.valid_to` ([org-model.md](org-model.md) §4.5) |
| `platform_auditor` | Cross-tenant audit reading, separate from `platform_admin` |
| `reports_analyst` | `report.definition.manage` without transactional access |
| `api_integration` | Per-integration service accounts. Narrow by design — one per integration, never a shared "API user" |

---

## 6. Seeding

- Seeds live in `seeds/`, versioned, **never in migrations** (CLAUDE.md §2).
- Idempotent and re-runnable: seeding is `upsert by (tenant_id = SCOPE_ALL, key)`.
- A role withdrawn from the catalogue is **deactivated, never deleted** — assignments reference it (CLAUDE.md invariant 12). A permission withdrawn from a shipped role *is* deleted: `role_permission` carries no lifecycle switch, and a deactivated row would keep occupying the unique key and silently refuse the re-grant. What changed lives in the audit trail.
- **Role keys are immutable.** `name` and `description` may change; `key` never, because assignments reference it.
- The permission catalogue is asserted at startup: a permission referenced by a seeded role but absent from the code catalogue is a **boot failure**, not a warning. Silent drift here means a role that grants nothing.
- Adding a permission to a shipped system role is a deliberate, noted change — it widens access for every tenant at once.
- Apply a catalogue change with `apis\identity\.venv\Scripts\python.exe -m seeds.roles --dry-run`, then without `--dry-run`, run **from the repository root** with `IDENTITY_DATABASE_URL` set to the intended database (the Identity virtual environment's interpreter; `seeds` is a root package). It is a read-then-write upsert, so it is safe to repeat. Operators can instead use the platform's `/v1/platform/system-roles` preview and `/reconcile`. A change to `company_admin` or `stock_operator` must be applied before company creation is used again: creation refuses (409) while the installed grants differ from the catalogue.
- Every tenant gets one `tenant_admin` at creation. That fixed bootstrap and the company-creator bootstrap in §1.5 use bounded system policy and must be audited; ordinary role assignment never bypasses the escalation guards.

---

## 7. Open questions

- [ ] Should `tenant_admin` be able to grant `period.lock`, or is that platform-gated? Leaning platform-gated given it is irreversible
- [ ] Does `viewer` see money amounts, or is a `viewer_no_amounts` variant needed? Cheaper as a field policy read-deny ([field-permissions.md](field-permissions.md) §8) than a second role
- [ ] Approval thresholds — is `billing_approver` a flat grant, or amount-banded? Amount bands need approval-workflow machinery, not more roles
- [ ] Default role for a newly invited user with none specified — `viewer`, or no role at all? Leaning no role, since a default grant is a silent grant

**Resolved 2026-09-03**

- [x] *Does `customer_portal` belong in this catalogue at all?* **Yes, seeded like the other system roles.** A separate authorization path would be a second resolver with no catalogue behind it, and "own records only" is an object-scope check either way — so the path that already enforces object scope is the one to use.
- [x] *Should SoD violations be blocked for system roles and merely warned for tenant roles?* **Yes, exactly that.** A shipped role holding a §1.4 pair fails the boot: the point of preloading roles is to get separation right by default, and there is no situation in which every tenant on the installation needs the combination. A tenant's own role returns the conflicts to the caller to warn on and record as an `admin`-category audit event, because a small business often has one person who must hold both and refusing outright would leave them unable to operate.


### Catalog unit and packaging permission extension (2026-09-11)

`unit.read` / `unit.manage` govern unit definitions, conversions and unit tax-code mappings.
`pack_type.read` / `pack_type.manage` govern packaging type definitions. All require the
company scope and current field policy; tax assignment/calculation remains separate.
Company Administrator receives management, and roles already reading items receive these
read permissions. The role seed reads the same code catalogue; no user assignment is created.

Catalog classification decision (2026-09-11): item groups and categories use separate resource permissions; Identity user-group permissions never grant Catalog access. Reparenting requires `.move` and current company scope. CompanyAdmin has these commands; existing Catalog reader roles receive the new reads through the Identity system-role seed.


### Salesperson system role (2026-09-11)

Added the company-scoped `salesperson` default with 12 existing permission keys for sales
invoice preparation and catalogue reads. There are now 12 system roles. No new permission
keys or automatic user assignments are introduced. Installation/reseeding creates this role
and its bindings idempotently; existing role IDs and grants are preserved. Customer-specific
access and invoice lifecycle/pricing enforcement depend on their owning APIs as described above.

Decision 2026-09-12: commercial Catalog masters add product_type, brand, brand_series,
manufacturer, manufacturer_site and brand_manufacturer read/manage keys, plus brand.move
and product_type.publish. Company administrators receive their management/publication keys;
the five system roles already granted classification reads receive these corresponding reads.
Tenant auditors retain complete business-read coverage. Role seeds remain the same idempotent
mechanism; Catalog does not acquire party-master permissions. Shared catalogue version 0.10.0.

Decision 2026-09-12 (C6.03): native attribute definitions/options and reusable sets have
separate read/manage permissions; publishing sets requires attribute_set.publish. Existing
Catalog reader roles gain these three reads, CompanyAdmin gains management/publication.
The Salesperson role now has 21 preparation/read permissions and no new mutation authority.
No user assignments are created. Shared catalogue version 0.11.0.

Decision 2026-09-12: C6.06 adds scoped identifier/inventory/warranty/return/handling profile
permissions. Identifier requirements are immutable at creation; the other four profiles have
separate publication permissions. Existing five Catalog reader roles gain these reads;
CompanyAdmin gains management/publication. Definitions do not authorize physical stock,
claims or return execution. Shared 0.12.0 carries the complete C6.06 permission vocabulary.


Decision 2026-09-12 (C6.07): master aliases and external keys have separate read/manage
permissions and also require the target master's current company-scoped authority. Existing
Catalog reader roles gain alias reads; integration source keys are restricted to CompanyAdmin and TenantAuditor by default. TenantAdmin retains its existing
organization-administration boundary without Catalog grants. CompanyAdmin gains both mapping management keys.
TenantAuditor remains read-only. Salesperson gains alias reads only (27 keys total). The same
idempotent role seed upgrades existing installations without assigning roles to users. Shared
0.16.0 adds this vocabulary while preserving the intervening 0.15.0 source/auth changes.

Decision 2026-09-12 (Catalog draft products): existing item.create/read/update govern product_family and item routes. Each entity still has independent native/custom field policy. Referenced type/unit/brand/series validation requires their existing read permissions. No new permission or role grant is introduced by this increment.

Decision 2026-09-12 (V1.3 pricing): shared 0.19.0 adds price_plan.publish/override,
purchase_price.read/manage and reference_cost.read/manage. CompanyAdmin receives all six;
TenantAuditor receives the two new reads. Other roles retain existing permissions, including
Salesperson's ordinary sale-price read without purchase, estimate or override authority.
Purchase resources also require ordinary price-plan authority; cost-derived evaluation
requires readable authoritative reference-cost fields. Publication additionally requires
price_plan.publish, including dated references, policy and numeric definitions. Native/custom
field denies and current authority apply on previews, resolution, replay and list filtering.

Decision 2026-09-13 (V1.4): shared 0.20.0 adds `tax_rule.publish` and `item.activate` to company administration. Activation also checks product update/adoption authority and readable dependencies. Auditor/business roles gain no new writes.


### Catalog V1.5 role decision (2026-09-13)

The fixed catalogue adds `catalog.bulk.read`, `catalog.bulk.manage` and `catalog.bulk.commit`.
The company administrator receives all three. The tenant auditor receives read only, subject
to the same original-actor job ownership and current company/field checks. Bulk permissions
supplement every underlying native action permission; they do not bypass product activation,
publication, purchase-price or field restrictions. Workers obtain fresh server-issued proofs
for the original actor before each bounded chunk; uploaded grants are never trusted.

### Accounting master permission catalogue (documented 2026-09-14)

These native keys already exist in the shared code catalogue. This records their current
meaning and seeded grants; it does not add permissions or widen any role.

| Keys | Authority |
|---|---|
| `accounting.head.read`, `accounting.head.manage` | Fixed account classifications; no ordinary head mutation route |
| `accounting.group.read`, `accounting.group.manage` | Account hierarchy and classification |
| `accounting.account.read`, `accounting.account.manage` | Posting account identities, aliases and external keys |
| `accounting.party.read`, `accounting.party.manage` | Parties, roles, addresses, contacts and commercial classifications |
| `accounting.batch.read`, `accounting.batch.manage`, `accounting.batch.hold` | Physical batch identities, controlled date corrections and independent hold/release authority; no quantity/value posting |
| `accounting.serial.read`, `accounting.serial.manage`, `accounting.serial.hold` | Serialized units and configured identifiers, registration lifecycle and independent hold/release authority; no quantity/value posting |
| `accounting.stock.read`, `accounting.stock.configure` | Stock evidence reads and stock account/policy configuration; neither authorizes posting |
| `accounting.stock.post`, `accounting.stock.reverse` | Independent stock execution and reversal authority under the posting owner's current readiness and period checks |
| `opening_balance.initialize_zero` | Explicit zero-opening declaration where the owner supports it; ordinary master editing does not grant this action |
| `accounting.tax.read`, `accounting.tax.manage` | Tax profiles, party registrations/identifiers and registration-address links |
| `accounting.bank.read`, `accounting.bank.manage` | Account bank profiles and party beneficiaries |
| `accounting.policy.read`, `accounting.policy.manage` | Payment terms, schedules and party accounting/credit policies |
| `accounting.setup.read`, `accounting.setup.manage` | Initialization and template installation |
| `accounting.mapping.read`, `accounting.mapping.manage`, `accounting.mapping.publish` | Posting mappings and draft publication |
| `accounting.import.manage` | Transactional imports, additionally requiring each underlying action |
| `accounting.export.read` | Protected exports, additionally requiring resource read |
| `accounting.history.read` | Protected revision metadata, additionally requiring resource read |

Every resource action checks company scope and current field policy. Head classifications
remain fixed and setup owns their initialization. TenantAuditor has all 11 Accounting read
keys. CompanyAdmin and Controller additionally have the eight applicable master manage
keys (excluding head.manage), import.manage and mapping.publish. TenantAdmin retains its
organization-administration boundary. These grants come from Identity's existing system-role
definitions and the idempotent `seeds/roles` entry point; reseeding does not assign users.

Decision 2026-09-14: Identity can author Accounting native field policies using its existing
field-policy endpoint. This requires tenant-scoped `field_policy.manage`, corresponding
Accounting resource authority at the target scope, and existing delegation restrictions.
Neither CompanyAdmin nor Controller gains field-policy administration through this repair.
Layout configuration still requires tenant-scoped `field_config.manage`.

## Accounting finance increment - 2026-09-15

`accounting.finance.read` reads authoritative financial setup;
`accounting.finance.manage` initializes it from signed Identity facts. `period.read`
reads fiscal years and periods; `period.manage` generates monthly years and activates
FUTURE periods. Controller receives all four; Accounts Clerk, Viewer and Tenant Auditor
receive the two read permissions. Existing `period.close`, `period.reopen`,
`period.post`, `period.post_adjustment` and deliberately assigned `period.lock` retain
their separate duties. No master-management permission authorizes financial posting.


Accounting credit and overdue charge permission additions (2026-09-15):

| Permission | Authority |
|---|---|
| `accounting.credit.read` | Credit decisions, reservations and override history |
| `accounting.credit.manage` | Reserve, release, renew and request a credit override |
| `accounting.credit.override_approve` | Approve/reject an override as a different actor |
| `accounting.charges.read` | Policies, calculations, assessments and verified tax evidence |
| `accounting.charges.manage` | Create/close policies, assess/reject, ingest tax evidence and post approved charges |
| `accounting.charges.approve` | Approve, waive or reverse charges; approval/waiver requires a different actor |

All keys are company scoped. Controller receives these operational permissions;
Accounting read roles receive the new read keys. Tenant/company administrators continue to
resolve their catalogue-based grants. These keys do not grant journal posting or period
permissions implicitly; those checks still apply to money movement. Opening controls use
`accounting.finance.manage`. No new UI is included in this increment.

### Accounting withholding masters (2026-10-05)

| Permission | Authority |
|---|---|
| `accounting.withholding.read` | TDS/TCS sections, dated rates, party withholding profiles, lower/nil deduction certificates and the read-only withholding preview |
| `accounting.withholding.manage` | Create and maintain those masters; writes also need the company's `tds` or `tcs` feature |

Both keys are company scoped. TenantAuditor receives read. CompanyAdmin and Controller receive
read and manage, which matches how they hold the other tax masters. No other role is widened. The
preview is a calculation that does not persist anything. It grants no journal posting, period or
settlement authority. Certificate reads are audited as sensitive reads. The `seeds/roles` entry
point reconciles these grants without assigning users.

Decision 2026-10-05: withholding masters get their own key family instead of reusing
`accounting.tax.*`. Withholding rates and certificates carry statutory evidence and are
maintained by a different desk from GST registrations. A separate family lets a tenant grant one
without the other.


### Vouchers foundation authorities (2026-10-10)

Company-scoped keys are listed below. They never imply executable accounting,
stock or statutory profiles. Those capabilities remain gated independently.

| Keys | Scope |
|---|---|
| `vouchers.read`, `vouchers.history.read`, `vouchers.export` | Current/revision reads, transition history, permission-filtered exports |
| `vouchers.create`, `vouchers.edit`, `vouchers.submit` | Draft creation, new immutable revisions and submission |
| `vouchers.approve`, `vouchers.reject` | Separate approval decisions against the submitted revision |
| `vouchers.issue`, `vouchers.cancel` | Non-statutory issue identity; cancellation of unissued documents and issued non-posting orders |
| `vouchers.share` | Opt-in external send request for a final voucher; also requires voucher read access and field visibility |
| `vouchers.accept`, `vouchers.decline`, `vouchers.expire` | Issued non-posting order/quotation/requisition decisions and validity expiry |
| `vouchers.post`, `vouchers.reverse` | Reserved financial execution permissions; C0 endpoints reject execution |
| `vouchers.type.manage`, `vouchers.configuration.manage`, `vouchers.configuration.publish` | Typed administration, restrictive bindings and publication |
| `vouchers.series.manage`, `vouchers.template.manage` | Issue series and immutable templates |
| `vouchers.artifact.create`, `vouchers.artifact.read` | Asynchronous rendering and live-authority protected downloads |
| `vouchers.operation.read`, `vouchers.operation.recover` | Durable work inspection and recovery without a new source identity |
| `vouchers.field.adopt` | Explicit compatible custom-definition adoption and derived index/claim rebuild |
| `vouchers.counter.operate`, `vouchers.counter.close` | Assigned cashier opens a drawer, records linked cash events and closes a balanced session |
| `vouchers.counter.read`, `vouchers.counter.supervise` | Read all drawer sessions; independently close or approve a variance with a reason |
| `vouchers.import.read`, `vouchers.import.manage`, `vouchers.import.commit` | Bulk voucher import jobs: read results, download templates/stage/validate/cancel, and create the reviewed drafts |

Separation of duties adds `vouchers.create` / `vouchers.approve`. Clerk roles create,
edit, submit and issue; approvers approve/reject. Company/tenant administrators manage
configuration; controllers inspect and recover operations. Viewers and auditors receive
read-only voucher authorities. Runtime self-approval is denied by default independently
of role conflict reporting. Identity's native system-role definitions are authoritative.

Decision: retain legacy invoice/payment keys for existing clients; new voucher routes
require voucher keys and never translate a legacy grant into posting authority.

Decision 2026-10-13: counter drawer access has dedicated keys and a company-owned
counter-to-user roster. `vouchers.create` and `vouchers.read` do not authorize drawer
cash access. Cashiers need an active assignment to the specific counter; a separate
supervisor can close a revoked cashier's shift with a reason, and the cashier cannot
approve their own variance. Tenant auditors may read all drawer sessions within their
role scope. Company and tenant administrators manage the roster through the existing
configuration authority but receive no implicit cash-operation permission.

Decision 2026-10-14: bulk voucher import has its own key family
([voucher-import-plan](voucher-import-plan.md) §7). The keys supplement `vouchers.create` and
field policy; they never replace them. Template, stage and validate require
`vouchers.import.manage` and `vouchers.create`. Commit requires `vouchers.import.commit` and
`vouchers.create`, checked again for every draft with the uploader's current signed authority.
Jobs change only for their uploader. Reading another user's jobs and results additionally
requires `vouchers.operation.read` (durable-work inspection), so TenantAuditor and Controller can
review them and clerks cannot see colleagues' jobs. The uploaded cells and the report stay with
the uploader, and a read-deny on voucher invoice content blanks the amounts in import results
and reports as well. BillingClerk receives all three keys and TenantAuditor receives read. No
other role is widened.

Decision 2026-10-22: tenant/company administrators receive the bounded company
bootstrap keys `accounting.finance.read`, `accounting.finance.initialize`,
`period.read` and `period.manage`. Initialization also accepts the existing broader
`accounting.finance.manage` grant for compatibility. Opening-balance changes,
posting and period close/reopen/lock remained withheld from administrator roles
under that decision. The user-approved 2026-10-30 Tenant Administrator opening
policy above supersedes the opening/posting restriction for `tenant_admin` only;
period closing remains withheld.
`company_admin` carries `company.create`, effective only when assigned at tenant
scope; company-scoped assignments cannot create another company. This bootstrap
permission correction is implemented; the other company-context Part 2 APIs remain
deferred. Replay rechecks authority and grants no opening-balance access.

Decision 2026-10-23: bounded books bootstrap also initializes its required Accounting
company record and five fixed account heads. `accounting.finance.read` plus either
`accounting.finance.initialize` or `accounting.finance.manage` may invoke only this
initialization command using current signed company facts. It grants no template
installation, master list/CRUD, opening-balance, posting, close, reopen or lock access.
Existing setup read/manage authority continues to work. Idempotent replay rechecks
the current scope and authority. Company/year management reuses existing period keys.

Decision 2026-10-26 (user requested company defaults): initialization now includes the
unchanged fixed business chart v3: five heads, 28 groups and 12 starter accounts. This
supersedes the five-head-only initialization above. The bounded finance grant can create
these fixed defaults in the same transaction and honors field denies; it still cannot
select arbitrary templates, install registration-specific tax accounts, list/edit masters,
change balances, post or close periods. Existing authored/installed charts are preserved.
No permission keys or system role grants change. Catalog setup uses existing tenant-wide
product-group, warehouse and price-plan read/manage grants, with explicit hand-offs when absent.

Decision 2026-10-22: platform administrative history reuses the three existing
platform permissions above. The signed history purpose marker is minted only after
configured-operator verification and live grant resolution. Audit separately gates
each exact event/entity family inside the operating tenant; company and department
evidence stays excluded. No permission catalogue or role seed changes are required.

Decision 2026-10-22: changing permission keys on an assigned custom role is an
assignment change for every active, unexpired user/group assignment, including
future-dated assignments. Apply the existing self/group, held-permission and
actual-scope guards to the old/new permission union before replacing keys. Role
metadata stays separately editable. Group membership/lifecycle and role
assignment/lifecycle must also check the field-policy access they introduce or
remove. Security audit differences retain safe permission keys, conflict warnings
and policy state; no general financial-role delegation exception is authorized.
See [access-control-fixes](access-control-fixes.md) for regression evidence and
the pending fresh-tenant provisioning decision.

Decision 2026-10-22: Console permission gates use concrete permission keys, matching
the server catalogue. Valid scoped `role.read` and `role.assign` grants may expose
the access directory and its controls; Identity still filters by actual scope.
Business permissions and tenant-wide `role.manage` are not flattened from narrower
grants. The account-type label is distinct from assigned-role authority.

Decision 2026-10-22 (review pass): the guard that fires on an assigned-role edit is
`role.assign` at each affected assignment's scope, so **`role.manage` alone edits only
an unassigned role**. Stated in §1.5 rather than left to a guard's error message,
because roles are data and a tenant may compose a role-designer role without
`role.assign`. A group-level change — a removal or a lifecycle toggle — names the
**group** as the assignment subject; the earlier placeholder was the `SCOPE_ALL`
sentinel, which the assignment change rejects, so such operations answered 422 on any
group holding an active assignment. Row-bound overflows on the policy and assignment
scans report a validation failure, not a permission denial. Field-policy conditions are
audited as changed-field markers, never stored values.


### Notification API ownership amendment (2026-10-22)

Platform notification keys retain three segments, for example
`platform.notification_provider.read`, `platform.notification_provider.manage`,
`platform.notification_template.read`, `platform.notification_template.manage`,
`platform.notification_route.read`, `platform.notification_route.manage`,
`platform.notification_request.read`, `platform.notification_delivery.read` and
`platform.notification_delivery.retry`. Corresponding recipient, consent and
suppression keys are also explicit catalogue entries. The platform administrator
role holds these keys; configured-operator proof is additionally mandatory. They
apply only to platform notification space, never customer business history.

`notification.attachment.scan` and its platform counterpart are reserved for an
authorized scanner integration, not template managers or default administrators.

Decision log: platform notification authority is separate from tenant `notification.*`
authority. New platform read keys are intentionally withheld from tenant auditors.

### Document layout authorities (2026-10-25)

Eleven `design.*` keys enter the catalogue (§2) for the `design` service
([invoice-design.md](invoice-design.md) §5.3). The grants in
`identity/domain/system_roles.py`:

| Role | Holds |
|---|---|
| `tenant_admin` | every `design.*` read, `manage` and `publish` key, plus `design.render.read`. A shared house style lives at tenant scope |
| `company_admin` | the same set for its own company, plus `design.render.record` for a test print |
| `tenant_auditor` | all five `design.*` read keys — including `design.render.read`, because which version printed a document is evidence |
| `billing_clerk` | `design.template.read`, `design.render.record`, `design.render.read`. Issuing a document prints it; the clerk authors no layout |
| `salesperson` | `design.template.read` |
| `billing_approver`, `controller` | `design.template.read`, `design.render.read` |
| `viewer` | `design.template.read` |
| `platform_admin`, `platform_support`, `accounts_clerk`, `customer_portal` | none. Layout is tenant business configuration (§1.6), and a customer never reads a template |

No `design.*` pair is a separation-of-duties conflict: a layout moves no money. The
`manage`/`publish` split is a change-control boundary, not §1.4 — a tenant may legitimately
grant one role both, which is why it is not listed in `SEGREGATED_DUTIES`.

Decision log: the interim implementation gated every design route — reads included — on
`vouchers.template.manage`. Reusing another service's key made one grant mean two things
and made revocation imprecise; dedicated keys replace it.

Decision 2026-10-27: manufacturing-operation definitions use dedicated `.read`, `.manage` and
`.publish` permissions. Company administrators receive all three within their assigned company;
tenant auditors receive read only. Other shipped roles, including platform roles and tenant setup
administrators, receive no implicit operation access. These permissions author definitions only and
never enable manufacturing, stock or financial execution. The normal role seed remains authoritative.


Decision 2026-10-27: sequential manufacturing-route definitions use dedicated `.read`, `.manage`
and `.publish` keys, with the same company-administrator / read-only tenant-auditor allocation
as operations. Publication also requires operation read authority and native child-field authority;
retirement preserves immutable step content. No operational manufacturing authority is inferred.

Decision 2026-10-27: BOM definitions use `bom.read`, `bom.manage`, `bom.publish` and
`bom.assign`. Company administrators receive all four within existing assignment scopes; tenant
auditors receive read. Platform and tenant setup roles receive no implicit business authority.
The `bom_definitions` capability requires inventory and defaults off; history stays readable
after disablement. No permission grants production, stock reservation or financial execution.

Decision 2026-10-27: promotion stacking policies have dedicated `.read`, `.manage` and `.publish`
keys. Company administrators receive all three in their existing company assignments; tenant
auditors receive read. Draft groups and explicit pairs use those same owner keys with native field
checks. Publication creates immutable definitions and grants no sale, hold or redemption authority.

Decision 2026-10-27: promotion limit definitions use dedicated `promotion_limit.read`,
`promotion_limit.manage` and `promotion_limit.publish` keys. These authorize definition
authoring and immutable publication; they do not authorize quota consumption, holds or
redemption. The explicit permission catalogue regression includes all three keys.

Decision 2026-10-27: a gateway request naming a company transports tenant grants
and only that company's company/department grants. Permission sets, validity dates,
group identities, support attribution and step-up checks retain their existing
meaning. Other-company assignments remain in the session actor, but do not grow
that request's signed header. The 24KB context limit and noncompany behavior remain
unchanged. This prevents ordinary new-company creation from exhausting the gateway
envelope as a creator accumulates scoped Company Administrator assignments.

### Purchase roles (decision 2026-11-01)

Reason: the end-to-end review of the untaxed account Purchase ([purchase-e2e-review](purchase-e2e-review.md),
D4) found that no shipped role could do the work. `stock_operator`, the only `vouchers.post` holder, could not
read the supplier (party data) or print; `billing_clerk` is the Sales role and could not read the Accounting
masters the page loads; `billing_approver` could not render the bill it approves; the controller approves and
reads but cannot record. The owner delegated the design ("proceed with what is best fit"; QuickBooks'
vendors-and-expenses user and Tally's data-entry versus owner security levels were the reference): least
privilege, separation of duties intact. No permission key was added to the catalogue, so §2 is unchanged.

| Role | Change |
|---|---|
| `purchase_clerk` | **New**, `scope_hint = company`. Records, submits, cancels and posts supplier bills, prints them, recovers a stopped posting; the 26 keys and the reason for each are in §4. Never approves; holds no `.manage`, `finance`, `setup`, `report` or `design` key and no period-closing key |
| `billing_approver` | Adds `accounting.party.read`, `account.read`, `group.read`, `head.read` and `vouchers.operation.read`. Reads only: still no create, edit, submit or post, so `vouchers.create` + `vouchers.approve` is not held by any shipped role |
| `stock_operator` | Adds `accounting.party.read`, `accounting.tax.read`, `vouchers.artifact.create` and `vouchers.artifact.read`, so the company creator can post an account Purchase (the preview reads tax defaults even for an untaxed bill), see a supplier's name and print what they record. **Not** `accounting.credit.read` and **not** any approval key: approval and period closing stay separate ([company-owner-access](company-owner-access.md)) |
| `billing_clerk` | Unchanged. It stays the Sales role; widening it would give every sales clerk the supplier directory and posting |

**Credit and policy reads are a precondition of posting, by design.** Posting a bill against a supplier that
has a credit policy, or an accounting policy (terms, holds), on the posting date needs `accounting.credit.read`
and `accounting.policy.read`: the control cannot be evaluated without reading its data, so it fails closed
instead of posting. A supplier with neither is assessed as unlimited and needs neither. `purchase_clerk`
holds both; `stock_operator` holds neither, so the creator's role cannot post a bill against such a supplier.
`accounting.tax.read` is a further precondition of every Purchase calculation, including an untaxed one,
so both `purchase_clerk` and `stock_operator` hold it (the company creator could not otherwise post their own
bill). It is broader than the one lookup the flow needs: the same key also reads party tax registrations,
identifiers and registration addresses (business identifiers, not personal data under CLAUDE.md §5.10).
Narrowing it means Accounting reading the account's tax default under service authority, or a narrower key:
open, owner decision. `stock_operator` still holds neither `policy.read` nor `credit.read`, so the creator's
role cannot post a bill against a supplier that has a credit or accounting policy.

**Credit reads only once credit limits are on (2026-11-03, owner direction "no unnecessary blockers").** With
the company's `credit_limits` feature off, a credit assessment can only ALLOW, so posting skips it and asks for
no credit read, for customers as well as suppliers: the company creator can post a credit Sale, a customer
refund or a Journal debiting a customer. Party holds and bill-wise rules are still enforced. Once the feature
is on, the rules above apply unchanged (a customer is always assessed; a supplier when a policy covers the
date). No role or permission key changed.

**What `purchase_clerk` is, plainly.** The voucher permissions (`create`, `edit`, `submit`, `cancel`, `post`,
`import.*`) are not scoped to a voucher kind, and `ledger.post_journal` plus `period.post` also guard
Accounting's manual-journal API (`POST /journals`, post, void, reversal), which has no approval step. So the
role can raise and post any voucher kind the company has switched execution on for, and journals, in an open
period. `stock_operator` already had this reach. Where a voucher type needs no approval (`approval_required`
false, the company default without the `approval_workflow` feature), the role's own `submit` approves, so one
person can create, submit and post. Money execution is off by default, so this is latent. Before it is
switched on for payments, receipts, journals or contras, either turn `approval_workflow` on, or add a
kind-scoped voucher permission, or have Accounting accept voucher-originated journals under service authority.
`ledger.read` is held for supplier advances and exposes journals, lines, open items and allocations.

Separation of duties: `purchase_clerk` and `billing_approver` are each clean alone, so they can be assigned to
different people; a tenant role composed from both returns the `vouchers.create` + `vouchers.approve` pair to
the caller for the usual warning and `admin`-category audit event (§1.4). There is no per-user union check;
the warning machinery works on one role's composition.

Existing installations apply this through the fixed-catalogue update described under `tenant_admin` (§4): the
operator's `/v1/platform/system-roles` preview and `/reconcile`, or `seeds.roles` (§6). The seed inserts the
new role and the missing grants, never touches role ids or assignments, and a second run changes nothing. It
needs no schema migration. **Apply it before, or with, deploying this catalogue:** company creation compares
the installed `stock_operator` grants with the code catalogue and answers 409 ("synchronize system role
permissions before creating a company") until they match. Permission-cache effects follow the documented TTL.
