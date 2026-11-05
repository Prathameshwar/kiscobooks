# Party and supplier import delivery

## Phases

1. Reuse the delivered product import workflow and shared CSS/components through
   an owner-specific configuration: Accounting transport, permissions, templates,
   navigation, row destinations and terminology. Keep product behaviour covered.
2. Add a native ready-to-use party-with-role import command. A new supplier or
   customer creates/activates its party and role in the same native aggregate.
   Validation rolls back all effects; failures retain no partial party/role and
   retries reuse the existing import effect/receipt mechanism. Existing low-level
   party/child templates remain available for explicit operations.
3. Enable party/supplier list links with scoped native import authority, then
   verify native validation/commit/replay/rollback, UI recovery/history/downloads,
   scoped routes, responsive themes and the real tenant3 flows. Review twice and
   fix findings before confirming completion.

## Decisions

- 2026-10-27: User requested party/supplier import using existing styles. Share
  the existing workflow rather than copying a second editor. Accounting retains
  ownership of its business rules, setup lock, field authority, audit and writes.
- The native `supplier` and `customer` import resources are import convenience commands,
  not another party table or role model. It uses the ordinary party/role lifecycle
  commands with independent current authorization and one aggregate transaction.
  It supports CREATE_ONLY; identity updates use the existing native party resource.
- Accounting's import API requires `accounting.import.manage` even for its history.
  The UI must reflect that existing rule and not infer read authority from Catalog
  bulk permissions or a displayed administrator role.
- No new database storage is needed. Public import DTOs remain shared; owner-native
  templates expose the configured schema. No credentials or sources are tracked.

## Delivered UI and native behaviour

`/accounting/parties/import` and `/accounting/suppliers/import` are enabled from
their list headers. Both use the extracted MasterImport workflow, the existing
shared styles/controls, cursor-paged history/results, private downloads and the
same upload limits/review/recovery behaviour as product import. ProductImport is
now a thin product-profile wrapper over that workflow; its existing path is kept.
No per-page stylesheet or duplicated import editor was introduced.

Party import now opens on the ready customer resource; plain party rows can only update, activate or deactivate (2026-11-02, PL-D01), and the ready rows always create the ledger account too. Plain rows used to retain their ordinary draft
lifecycle. Supplier import defaults to the ready `supplier` resource: one flat row
of party identity fields creates an active identity and active SUPPLIER role.
The party page also offers ready customers/suppliers and existing related-record
templates. Ready resources are create-only. Role and policy templates honor their
selected CUSTOMER/SUPPLIER role; the supplier entry point restricts these choices
to SUPPLIER and does not offer ready-customer creation.

Accounting checks `accounting.import.manage` even for summaries. The Console also
requires company-scoped party read access. Without party management it shows
retained summaries and withholds detailed requests/download controls, matching
Accounting's stricter native readable-resource contract. Field and child-resource
authority remain native checks. Catalog permissions and administrator labels do
not grant Accounting access. Native source/attempt/revision downloads stay private.

## Reviews and fixes

1. Workflow review: added atomic ready customer/supplier commands and regression
   tests for dry-run rollback, native activation, replay and denied role activation.
   Fixed supplier policy templates advertising CUSTOMER as well as SUPPLIER despite
   an explicit supplier role parameter. The new native convenience commands reuse
   current authorization, setup lock, business validation, audit and normal lifecycle.
2. UI/permission review: verified product compatibility after extraction, exact
   Accounting request recovery, cross-service allowlist rejection, correct related
   record destinations and import return links. Fixed detailed party-history and
   download controls being offered after party management is removed. Reviewed
   fully loaded desktop/mobile pages in all themes; native party-only and supplier
   lifecycles are accurately distinguished.

Manual simplify/security reviews walked the repository security/correctness rules;
no remaining issue was found in this scope. Dedicated slash-command review tools
were not available, so no automated `/simplify` or `/security-review` is claimed.

## Verification

- 188 focused frontend tests passed across party/supplier import UI, scoped pages,
  strict Accounting proxy, product import/file/proxy/page compatibility, product
  experience, party directories and Accounting pages.
- Native Accounting import suite: 12 passed, including CSV/TSV/XLSX, original and
  result downloads, corrections, scope/permission revocation, customer/supplier
  child aggregates, ready aliases, replay, atomic rollback and role-limited policies.
- Ruff, strict mypy, TypeScript and Accounting OpenAPI freshness passed. The native
  service was reloaded through its owned launcher; readiness returned HTTP 200.
- Real tenant3 supplier flow in the isolated verification company: CSV template,
  missing legal-name validation/message, no retained identity after invalid or ready
  validation, private error report, corrected revision, reviewed commit, active
  party and active SUPPLIER role. The supplier appeared in the ordinary Suppliers
  directory. Reload and scoped history retained the completed import without a
  duplicate commit action.
- Real tenant3 party flow: configured identity template, upload, validate and reviewed
  commit; exactly one party was created with the normal DRAFT identity lifecycle.
- 36 visual combinations covered supplier new/invalid/completed/history and party
  new/completed, in light/dark/ledger at 1440/390 widths, without document/main
  overflow or browser runtime errors. Final screenshots wait for loaded forms and
  tables before capture; the 30 non-invalid combinations were rechecked after the
  native end-to-end run. Desktop/mobile screenshots were inspected directly.

The ready commands change no public DTOs or SQLAlchemy models and require no
migration. Template schemas remain owner-native dynamic snapshots of existing
PartyCreate/role commands. OpenAPI is unchanged and existing generated import
contracts remain valid. Live staging/validation/commit exercised the existing
Accounting MySQL tables. Test business identities and evidence stay in the isolated
verification company / ignored `.tools/extension-masters` files. No financial
documents or balances were posted; no identity-provider users were created.

## Optional opening balances (2026-10-31)

Ready customer and supplier rows accept optional `opening_*` columns: a debit or credit balance
(`DR`/`CR`/`TO_RECEIVE`/`TO_PAY`), amount, currency and one dated bill. The import creates the
party's ledger account and holds the balance for the company opening; it posts nothing and
saves no declaration. The template, validation, held-balance storage, worksheet panel and
limits are in [party-opening-balance-import](party-opening-balance-import.md). Identity-only
`party` rows are unchanged.
