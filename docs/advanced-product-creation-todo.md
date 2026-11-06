# Advanced product creation: implementation TODO

Updated 2026-11-05. This is the live execution and review record for
[the plan](advanced-product-creation-plan.md) and
[the Phase 0 UX contract](advanced-product-creation-ux.md).

**Gate:** Finish each phase's files, affected tests and review before starting
the next. The user's later instruction to proceed to the next phase when done
authorizes continuation after each review. Record evidence here as each phase
closes.

## Status

| Phase | State | Start authorization | Review/evidence |
|---|---|---|---|
| 0. Contract and UX | Complete; reviewed 2026-11-04 | User requested phase-wise start | See Phase 0 record below. |
| 1. Options and drafts | Complete; reviewed 2026-11-04 | User confirmed “ok proceed” | [Phase 1 record](advanced-product-creation-phase1.md); review below. |
| 2. Catalog aggregate | Complete; reviewed 2026-11-04 | User said “once done take the next phase” after Phase 1 | [Phase 2 record](advanced-product-creation-phase2.md); review below. |
| 3. Setup and activation | Complete; reviewed 2026-11-05 | User said to proceed and continue after review | [Phase 3 record](advanced-product-creation-phase3.md); review below. |
| 4. Opening orchestration | Complete; reviewed 2026-11-05 | User said to take the next phase when done | [Phase 4 record](advanced-product-creation-phase4.md); review below. |
| 5. UI shell and steps 1–2 | Complete; reviewed 2026-11-05 | User said to take the next phase when done | [Phase 5 record](advanced-product-creation-phase5.md); review below. |
| 6. UI steps 3–4 | In progress | User said to take the next phase when done | — |
| 7. Integration and release review | Pending | Pending after Phase 6 review | — |

## Phase 0 — contract and UX

- [x] Confirm one `/masters/items/new` route and the company-controlled
  Simple/Advanced creation card and form switch.
- [x] Define loading, failed read, denied permission, wrong-company and
  mid-draft mode-change behavior.
- [x] Define four step wireframes, copy, responsive/theme/focus behavior and
  truthful draft/submission/progress states.
- [x] Map each field group to native owner, applicability, permission boundary
  and validation; mark reference and cross-owner decisions for implementation.
- [x] Review documentation against `CLAUDE.md` security/correctness rules and
  verify relative links and formatting. See review record below.

**Phase 0 review record — 2026-11-04:** The reviewed change is documentation
only: the plan, this TODO and the UX contract. No application code, schema,
database, generated client or runtime configuration was changed. Security
review: the entry and direct route deny by default when mode or permission
cannot be verified; server/native owners retain company, object, field, tax,
money and posting authority; submitted intents require stable idempotency and
truthful partial-result status. Correctness review: the proposed entry uses
`product_family_sku_enabled` rather than `variants_mode`; exact decimal money
and quantity, source revisions, one-SKU Advanced profiles and optional opening
are specified. No blocking Phase 0 finding. The existing Simple-only direct
route, missing Advanced creation action and failed-read Simple fallback are
**implementation gaps**, tracked for Phase 5/7. Native SKU command
bounds, draft retention/actor scope and opening owner contracts remain
implementation decisions, listed below. Documentation link/whitespace checks
are recorded in the phase report to the user; no runtime tests apply to docs.

## Phase 1 — options and drafts

- [x] Decide and record draft expiry/deletion, actor resume scope, draft
  bounds and option source/version policy in the plan decision log. Phase 2
  finalizes the aggregate submit bound.
- [x] Add Catalog options/field metadata and permission-aware, company-scoped
  Product Type, category and price choices. Accounting/Vouchers opening options
  follow their native contract in Phase 4.
- [x] Add server-backed draft save/read/update/delete/resume with version
  conflict handling; include model, one-DDL-per-revision migration, schema,
  API test fixture and generated client together.
- [x] Test two-tenant/wrong-company denial, actor/field denial, stale source,
  saved draft recovery and current mode change.
- [x] Review security/correctness and document findings; ask for Phase 2
  confirmation after the review.

**Phase 1 review record — 2026-11-04:** Options use verified Advanced mode,
effective Catalog configuration, native field sets and protected references.
Drafts are actor/company scoped, bounded, versioned, and deny a now-protected
field on save or read. The same transaction emits marker-only audit events;
there is no product, price, stock or Voucher effect. Revision `0222` has one
`CREATE TABLE` and a nonempty-draft downgrade guard. Local Catalog was backed
up to a private file outside the repository, restored into an isolated schema,
upgraded `0221→0222`, and compared with the model (zero differences). The
rehearsal schema was removed. Local Catalog is at `0222` with zero metadata
differences; the other seven database heads match their current scripts.
Focused Catalog regression/migration/audit suite: **13 passed, 2 skipped**
(native dedicated-port tests skipped because that optional server is not
configured; the local native rehearsal above ran). Ruff and strict mypy on
changed Python files, exported OpenAPI/audit contract checks, generated Catalog
client check, Catalog declaration compilation, Console typecheck and API client
runtime tests passed. Full API client typecheck has an unrelated existing
Accounting failure in `tests/accounting-types.ts` (`AccountCreate` is absent
from the concurrently modified Accounting declaration); no Accounting file was
changed for this phase. No blocking Phase 1 security/correctness finding.

## Phase 2 — Catalog aggregate

- [x] Add bounded Product Profile + explicit SKU creation and native validation
  in one Catalog transaction; reuse existing product authoring paths.
- [x] Retain exact command body/hash and idempotency key with safe status
  recovery; align models, migrations, schemas, factories and client.
- [x] Test duplicate SKU/signature, invalid field and Type rules, rollback,
  replay, wrong-company and MySQL behavior.
- [x] Review security/correctness and document findings; ask for Phase 3
  confirmation after the review.

**Phase 2 review record — 2026-11-04:** Definition submit requires verified
Advanced mode and current mode/policy/configuration/business-date versions.
The strict command caps canonical JSON at 64 KiB and explicit SKUs at 64;
duplicate codes are rejected before mutation. Native Catalog creation validates
published Type, unit, brand/series, custom-field and field-write rules; native
attribute/variant handlers validate required axes, options and canonical SKU
signatures. First SKU is the default slot, with no automatic Cartesian SKU
generation. One Catalog transaction persists family, SKUs, declarations,
variant keys, immutable submission receipt, native audit changes and a
marker-only creation audit event. Rejected later SKUs roll it all back.
Idempotent replay returns the same receipt and rechecks current read/write
permission. Receipt status is initiating-actor and company scoped. The stored
request is canonical validated JSON, not raw HTTP bytes. It has no price, tax,
stock or Voucher effect in this phase.

Revision `0223` adds one `CREATE TABLE` and guards downgrade when submitted
receipts exist. A private local Catalog backup was restored into an isolated
MySQL schema; the upgrade, two native definition scenarios, nonempty downgrade
guard and model comparison passed with zero differences. The isolated schema
was removed. Local Catalog is now at `0223`, matching model/script with zero
metadata differences; all eight local database heads match current scripts.
Focused regression, migration and audit suite: **25
passed, 1 skipped**; the optional dedicated Docker MySQL test was skipped, and
the local native rehearsal above was run. Ruff, strict mypy, OpenAPI/audit
export checks, generated Catalog client check, Catalog declaration compilation
and Console typecheck passed. The final definition-focused run, including the
mode-change assertion, passed **5 tests**. Review of `CLAUDE.md` §§5–6 found
no blocking security or correctness issue. Phase 3 remains gated on user
confirmation.
The full API-client typecheck retains the unrelated Accounting declaration
error documented in Phase 1 (`AccountCreate` missing from
`tests/accounting-types.ts`); the Catalog-only declaration check passed.

## Phase 3 — setup and activation

- [x] Apply eligible tax, published profiles, units, purchase reference and
  named selling prices per SKU through native Catalog authority.
- [x] Expose per-SKU readiness and activation blockers with field/step paths.
- [x] Test required levels, price/tax exactness, missing/changed references,
  permission boundaries and recovery from partial publication.
- [x] Review security/correctness and document findings; continue to Phase 4
  under the user's latest instruction.

**Phase 3 review record — 2026-11-05:** Native per-SKU setup, exact reference
cost and MRP declarations, tax bindings, price drafts/publication and activation
use Catalog's existing dated, permission and field policies. The first SKU owns
shared Profile setup; another draft SKU can continue after the Profile becomes
active. Each SKU's progress, audit markers and native rows commit together.
The two-SKU regression retains the successful first setup when the second
fails, then resumes the second. A priced SKU retains exact decimal values and
one price after publication replay. Changed tax references roll back all setup
rows; denied purchase-reference authority produces no write. Readiness returns
field/step paths and an incomplete Service SKU cannot activate. Native Catalog
activation and authoring regressions passed **28 tests**; activation edge and
Advanced SKU tests passed **10 tests**. Ruff and strict mypy passed for the
changed source. OpenAPI, audit contract and generated Catalog client checks
passed before Phase 4 additions. No schema change was needed; Catalog remains
at revision `0223`. No blocking Phase 3 finding.

## Phase 4 — opening orchestration

- [x] Resolve and record native location, batch-price and serial/IMEI owner
  contracts before writing cross-owner commands.
- [x] Add optional per-SKU native opening preflight and retained owner receipts;
  keep remote calls outside money transactions.
- [x] Test exact value, quantity/identifier reconciliation, closed period,
  replay, uncertain response and partial posted-opening recovery.
- [x] Review security/correctness and document findings; continue to Phase 5
  under the user's latest instruction.

**Phase 4 review record — 2026-11-05:** Native owner contracts are recorded in
the Phase 4 document. The Advanced opening decision checks an active SKU,
effective books-begin base unit, stock profile, identifier and Accounting field
authority before saving. It retains one command key per owner step and never
calls Accounting or Vouchers inside a Catalog transaction. A lost response
keeps the same pending key; a definite rejection can be retried. Only Voucher
posting plus Accounting reconciliation marks `POSTED`. Explicit active
warehouses work even without a default. An earlier posted SKU receipt survives
a later SKU's skipped opening. Final focused Advanced and Simple opening tests:
**6 passed**; broader Advanced, Simple batch and serial run: **16 passed**.
Ruff, strict mypy, OpenAPI, audit and generated Catalog client checks passed.
Revision `0223` already contains the progress and lease fields, so there is no
Phase 4 schema change. Live cross-service rehearsal remains a Phase 7 gate;
no blocking Phase 4 finding.

## Phase 5 — UI shell and steps 1–2

- [x] Add verified mode-selected directory creation card and same-route
  Simple/Advanced launch; cover loading, denied and failed mode states.
- [x] Build in-shell four-step layout, product styles in `@janso/ui`, draft
  navigation, Profile step and explicit SKU builder.
- [x] Test direct URL, Simple regression, mode change, keyboard/focus, all
  themes and desktop/phone layouts.
- [x] Review security/correctness and document findings; ask for Phase 6
  confirmation after the review.

**Phase 5 review record — 2026-11-05:** See the [Phase 5 report](advanced-product-creation-phase5.md).
The route and card use verified current-company mode; failed or denied reads
cannot mount either creation form. First two steps collect Profile, explicit
SKUs, configured categories/manufacturer and alternate units; later steps
remain incomplete until Phase 6. Drafts retain versioned private transport
state and uncertain saves retain a command key. New entry, draft, policy and
wizard tests passed **12**; Product Mode, retired-route and classification
page tests passed **31**; Simple/classification UI and policy passed **80**.
The real-browser Profile layout passed 4 widths × 3 themes. Console typecheck
passed. No Phase 5 native write effect or schema change. No blocking Phase 5
security/correctness finding; the user's continuation instruction authorizes
Phase 6.

## Phase 6 — UI steps 3–4

**Continuation review — 2026-11-05:** The existing four-step UI was ahead of this
tracker but had not passed Phase 6 acceptance. The current change adds a dated
base-unit binding, per-SKU native quantity/price suggestions, barcode capture,
batch named sale prices, books-begin opening-date options, exact serial-count
validation, expanded review, linked field errors, and receipt-aware recovery.
The Catalog options schema, OpenAPI and client were updated together. Two
security/correctness review passes found and fixed the base-unit/alternate
binding limit, immutable completed-step edits, stale opening choices, and
books-begin date trap. See [the continuation review](advanced-product-creation-phase6-review.md).

Phase 6 remains **in progress**: a native whole-draft preview, readable published policy terms, and owner
carrying-value preview are still missing. The affected pytest and Console
Vitest suites cannot run in this workspace because `pytest_asyncio`, pnpm and
the workspace `node_modules` are unavailable; the offline npm cache also
lacks required packages. The integration and release gates remain pending.

**Final end-to-end review, 2026-11-05:** The route, draft, definition, per-SKU
setup, price publication, activation, opening decision and retained owner
receipts were traced again. The review fixed a recovery path that could create
a duplicate definition after losing its session receipt; recovery now checks a
fresh server status. The final review now shows named batch selling prices.
The options schema/client now accept published `BOTH` Product Types. Static
TypeScript library and syntax checks, Python compilation, OpenAPI parsing and
diff checks pass. Catalog pytest still cannot start without `pytest_asyncio`;
Console Vitest/typecheck and browser checks remain unavailable without pnpm
and workspace dependencies. Phase 6 and 7 remain open, so this is not a
release-ready or fully verified end-to-end result.

**Product creation reliability follow-up, 2026-11-06:** Simple creation now
retries the two temporary stock posting conflicts on its initial save and
later advances using the same request/key. Advanced creation retries them on
definition, setup, publication, activation, opening preflight and opening
advance; a retained opening can continue beyond the former 12-call limit for
up to ten minutes. The UI shows the wait and preserves the saved intent if the
bounded wait expires. Focused Console tests: 53 passed across four files;
Console typecheck passed. Catalog owner transport already classifies the
stock definition fence as uncertain and retains its command. At that
follow-up, Catalog integration tests were not run; the VM deployment venv has
no pytest and its offline dev dependency cache is incomplete. A local Python
3.12 venv was found and used for the later tests below. This follow-up is not
evidence for the remaining Phase 6/7 acceptance matrix.

**Simple creation price correction, 2026-11-06:** A zero Purchase price is
invalid under the native purchase price rule. Simple Goods and batch forms now
reject it before creating a product; the Catalog input contract rejects it for
all callers. A saved creation that receives the exact pricing policy/Identity
source conflict retries its current step with refreshed owner evidence. The
Catalog regression verifies source conflicts during native create and price
publication resolve to one product with the expected published prices. The
affected Catalog creation suites passed 23 tests; focused changed-path tests
passed again after the final regression update. The affected Console suites
passed 80 tests and Console typecheck passed. Catalog Ruff, schema mypy,
OpenAPI export check and generated Catalog client check passed. The global
client typecheck remains red on an unrelated missing Accounting `AccountCreate`
type. This evidence does not complete the Advanced Phase 6/7 matrix.

- [ ] Build native-option Business setup, optional Opening, editable Review,
  whole-draft errors, immutable Submit and verified progress/recovery views.
- [ ] Test configuration matrix, error focus, denied field, changed source,
  exact command retry and partial/uncertain completion wording.
- [ ] Review security/correctness and document findings; ask for Phase 7
  confirmation after the review.

## Phase 7 — integration and release review

- [ ] Align OpenAPI/generated client and every changed consumer; run affected
  backend, UI, lint and type gates.
- [ ] Rehearse native schema migrations with backup; verify DB/model/script
  heads and downgrade review where applicable.
- [ ] Run the plan's Service/Goods/variant, tax/price, batch/serial, permission,
  replay and partial-result scenario matrix, including all responsive widths
  and three themes.
- [ ] Complete `CLAUDE.md` sections 5–6 review, simplify/security review for
  changed auth, tenant, money and audit paths, record findings, and request any
  separate release/publish authorization if needed.

## Owner decisions

1. Selectable opening warehouse and batch-price owner contracts are recorded
   in [Phase 4](advanced-product-creation-phase4.md). The current UI captures
   named batch sale prices and preserves the chosen warehouse ID.
2. Native SKU activation currently has no manufacturing/BOM prerequisite in
   `product_requirements.py`; show manufacturing as a named follow-up where
   relevant. A future Product Type rule requiring a BOM needs its own native
   readiness and authoring contract before it becomes a wizard field.

Do not hide these behind client defaults. Resolve each in its owning phase and
update the plan decision log and this tracker together.
