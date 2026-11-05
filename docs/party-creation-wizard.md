# Party and supplier creation wizard

## Agreed scope

Four freely navigable steps: identity; optional default address and contact;
optional tax registration and notes; optional opening balance. Create is available on every step and
validates the complete draft. Existing edit screens retain their native lifecycle.
General account creation excludes Party; contextual party-ledger creation remains.

## Delivery phases

1. Add a strict, company-scoped idempotent Accounting aggregate command reusing
   existing master validation, field policy, locking, audit and lifecycle. Create
   an active party, supplier role when requested, optional address with active
   default billing/shipping uses, optional contact with active general use, and
   optional dated tax registration. Roll back everything on any failure. No model
   or database changes.
2. Add the three-step Console wizard using native metadata and shared components,
   with optional-section toggles, permission gating, whole-draft validation,
   guarded navigation and safe retry. Correct general account kind choices.
3. Verify native rollback/replay/defaults and UI navigation/validation/failures;
   regenerate OpenAPI/SDK, run type/static checks, and review security and UX.

## API and lifecycle

`POST /v1/companies/{company_id}/parties/create-with-details` accepts the existing
party identity fields and optional `role`, `address`, `contact`,
`tax_registration`, and `opening`. Nested records cannot supply a party ID. The server assigns
all owners, activates status-based records, and creates default BILLING/SHIPPING
address uses and a default GENERAL contact use. Tax registrations keep their
native effective-date validation. The response is the protected active PartyDetail.

The edit APIs (`PATCH`, `activate`, `deactivate`) are unchanged. The plain identity-only
`POST /parties` **no longer exists** (2026-11-02, PL-D01): this command and the ready
customer/supplier import are the only ways a party is created. The Console creation screen
uses the aggregate command; payment/credit policies remain explicit related configuration
after creation.

**Mandatory ledger (2026-11-02, supersedes the optional ledger of 2026-11-01).** Every party
has a role and every role has its ledger account; the command takes no "without a ledger"
form. `role` is required, and the same transaction creates the ACTIVE party, its ACTIVE role
and its ACTIVE PARTY account (it needs `accounting.account.manage` and `.read` as well as the
party and role rights). The account role is the party role's (`CUSTOMER`, `SUPPLIER`), except
that `BROKER` and `OTHER` share the account role `OTHER`, the only one the account table has
for them. The group is the company's system Sundry Debtors (customer) or Sundry Creditors
(everything else) unless a usable `group_id` is given; if the default group is missing or
inactive the command is refused (`ledger.group_id`) rather than guessing. The body's
`ledger` (`code`, `name`, `group_id`, `currency_mode`, `currency`) now carries *choices only*
and may be left out; the code defaults to the party code and the name to the party name. Any
failure rolls back the party, role, ledger, audit rows and idempotency claim together, and a
replay yields the same party with no second ledger. See
[party-ledger-mandatory-plan](party-ledger-mandatory-plan.md) for the rule, role activation,
the one-account-per-role guard and the repair of older data. Related:
`POST /accounts/create-active` creates and activates a general account in one atomic
request (used for the bill's "create expense account"). General account creation excludes
PARTY; an existing-party ledger context retains it, but a second live account for the same
party and account role is refused. No tables, migrations, seeds or permission keys changed.

## Verification and review

- 343 Console tests passed across 13 relevant suites before the final validation
  routing improvement; 77 focused regressions passed afterward, including returning
  to the native error's owning step with the draft retained.
- 33 Accounting regression tests passed (masters, native configuration, imports
  and initial aggregate coverage). The expanded six-test aggregate suite checks
  active defaults, exact replay, revoked permission, protected fields, invalid tax,
  forbidden child ownership, rollback, identity-only creation and changed-body
  idempotency rejection.
- Ruff, strict mypy (176 Accounting source files), Console TypeScript, exported
  OpenAPI and generated Accounting SDK checks passed. SDK version is 0.2.35.
- Live tenant3 verification in the isolated Catalog enrollment verification company
  created a supplier from step 2. Native readback confirmed its active role, active
  default billing/shipping address uses, active default general contact and dated
  GST registration. Exact replay returned the same party, and Suppliers listed it
  immediately. No balances or financial documents were created.
- All three steps were checked at desktop/mobile widths in light/dark/ledger
  themes (18 combinations), with no horizontal overflow or browser errors.
- Final live invalid-contact verification confirmed a native 422 returns the UI
  from step 1 to step 2, preserves the draft, clears the error after correction,
  and leaves no partial party/default records. Settled desktop/mobile screens
  were visually reviewed after this correction.
- Manual simplify/security review (the slash commands are not installed): existing
  native mutation/validation mechanisms reused; shared CSS/components only;
  verified actor/company context and native scope checks retained; nested owners
  server-assigned; native field policies checked during create/activation and
  replay; one company lock, transaction and idempotency receipt; audit/notification
  snapshots remain atomic through existing outbox writers. No unresolved findings.

Private synthetic fixture IDs/screenshots and test reports are under the ignored
`.tools/extension-masters/party-wizard-*` paths. No credentials or personal customer
data are included in this document.

## Database, model and script synchronization review (2026-10-27)

The read-only `dbs/verify_sync.py` check passed for all eight live services:
Identity 0088, Audit 0003, Catalog 0208, Notification 0116, Accounting 0167,
Vouchers 0097, Reports 0038 and Design 0008. Every database matches its migration
head, model tables/columns/indexes/constraints, and configured readiness head;
every Alembic check exited successfully. No database migration or data repair was
needed.

Regenerated the Accounting master matrix after the shared input-schema extraction
changed required-field ordering. Accounting and Catalog field/audit contracts,
OpenAPI exports and generated SDKs pass their freshness checks. Corrected the
Accounting Alembic configuration comment to name ACCOUNTING_DATABASE_URL.

The verifier initially reported Catalog's promotion comparable constraint as
different: MySQL had rewritten NOT(A AND B) into NOT(A) OR NOT(B). Added narrowly
scoped boolean-negation normalization and failing-first regression coverage for
both De Morgan forms, changed operands/connectives, and preservation of numeric
double negation. All eight verifier tests pass, followed by the successful full
live verification. The check remains read-only and still detects real differences.
Manual correctness/security review found no remaining issues.

Private live reports: `.tools/extension-masters/party-wizard-sync/*-summary.json`.
