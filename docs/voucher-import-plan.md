# Voucher import plan — template, validate, import result

Status: **AGREED 2026-10-14; I0–I6 IMPLEMENTED 2026-10-14; P-D (eight important kinds)
IMPLEMENTED 2026-10-15** (see §11 and §12). Purchase, Sales, Credit/Debit Note, Payment,
Receipt, Contra and Journal; ACCOUNT/SERVICE lines; drafts only.

Bulk entry of vouchers from a downloaded template, with a full validation pass that changes
nothing, an explicit reviewed commit and a downloadable per-row result. It realises the
optional `voucher_import_job` / `voucher_import_row` candidates in
[table inventory](voucher-table-inventory.md) §6 and follows the Catalog bulk contract
([catalog-bulk-pricing](catalog-bulk-pricing.md) §2, [catalog-v15-api](catalog-v15-api.md)).
It is not historical migration (B45 stage 2), bank statement import (B43) or opening stock.

## 1. Principles

1. **An import is a batch of ordinary voucher commands.** Each voucher is written by the same
   `documents.write` path, invoice calculation and policy checks as the API/UI. Import never
   relaxes configuration, field policy, fiscal readiness, tax or permission rules
   ([voucher-data-model](voucher-data-model.md) §341: policy applies on import).
2. **Import creates drafts.** It never issues, numbers, approves or posts. Numbers are
   allocated on posting only (§6.6); posting stays a separate, individually authorised step.
3. **Validate changes nothing.** Validation runs native commands in a rolled-back transaction;
   no voucher, receipt, audit event or outbox row survives it.
4. **Commit applies exactly what was reviewed** — bound to job version and selection digest.
   Changed input, configuration, master versions or permissions require revalidation.
5. **One voucher = one change set = one transaction.** Header, lines, parties, references,
   invoice section, idempotency receipt, effect marker, audit event and outbox commit together.
   Retry or redelivery never creates a second draft.
6. **Masters are matched exactly, never created.** Display names do not identify anything.
7. **Totals are computed, not trusted.** Tax and totals come from native calculation; the file's
   supplier total is a control figure that must agree.

## 2. Workflow

```
Template ─▶ Upload (stage) ─▶ Validate (bounded steps, dry run) ─▶ Review results
   ─▶ Commit (bounded steps, one draft per voucher) ─▶ Import result + downloadable report
```

| Step | What the user gets |
|---|---|
| Template | CSV / XLSX / JSON for a chosen Purchase voucher type, generated from that type's current field-set, effective configuration and authorised custom fields; instructions and example rows |
| Upload | Job id (202). File is parsed, bounded and staged; raw bytes are private to the uploader |
| Validate | Per voucher: `VALID`, `WARNING`, `INVALID`, `BLOCKED`; per row/column errors; computed taxable/tax/total vs supplier total; counts; selection digest |
| Commit | Either all valid vouchers or an explicitly accepted valid subset (new digest). `on_error` STOP or CONTINUE_INDEPENDENT |
| Result | Per voucher `CREATED` (draft id) / `FAILED` / `NOT_SELECTED`; job `SUCCEEDED`, `PARTIAL`, `FAILED`, `CANCELLED`; report = original rows + status + error code/column/message + draft id |

## 3. Purchase template

Formats: **XLSX with two sheets** (`vouchers`, `lines`) and an `instructions` sheet; **flat CSV**
(one row per line, header columns repeated and required to agree within a voucher); **JSON**
(the native shape). Every sheet starts with the version marker row used by
`billing_platform.bulk_files` (`_voucher_schema_version,1`). Dates are ISO `YYYY-MM-DD`;
money/quantities are decimal text (no floats, no thousands separators); codes stay text.

### `vouchers` sheet — one row per voucher

| Column | Req. | Maps to |
|---|---|---|
| `import_key` | ✓ | Unique within the file; groups lines |
| `voucher_type_code` | ✓ | Purchase type → current published `type_revision_id` |
| `voucher_class_code` | | `class_id` |
| `document_date` | ✓ | `document_date` |
| `posting_date` | | `posting_date` (period checked; see §4 L5) |
| `supplier_code` / `supplier_gstin` | ✓ (one) | Accounting party (exact code, or GST_IN registration) → SUPPLIER party + version |
| `supplier_ledger_code` | | Chooses the party's SUPPLIER ledger when it has several → `party_account_id` + version |
| `supplier_invoice_number` | ✓ | `tax.supplier_invoice_number`, SUPPLIER_INVOICE reference, `bill_reference` |
| `supplier_invoice_date` | ✓ | `tax.supplier_invoice_date` |
| `due_date` | | `invoice.due_date` (defaults from supplier credit terms if configured) |
| `currency` | ✓ | `currency` |
| `exchange_rate` | | `invoice.exchange_rate` (required when currency ≠ company currency) |
| `place_of_supply` | | `tax.place_of_supply` (`IN-xx`) |
| `tax_profile` | ✓ | `tax.profile` |
| `supplier_declared_total` | ✓ | `supplier_declared_total` control figure |
| `supplier_difference_reason` | | Required when difference is within tolerance but non-zero |
| `narration` | | `narration` |
| `cf.<key>` | | Header custom fields of the type (only authorised, writable keys) |

### `lines` sheet — one row per supply line

| Column | Req. | Maps to |
|---|---|---|
| `import_key`, `line_no` | ✓ | Parent voucher; stable line order and `line_key` derivation |
| `supply_kind` | ✓ | `ACCOUNT` / `SERVICE` (first slice); `GOODS` per Q2 |
| `account_code` | ✓ for ACCOUNT/SERVICE | Purchase/expense ledger → `account_id` + version |
| `item_code`, `unit_code` | GOODS only | Catalog SKU / unit → `item_id`, `item_version`, `unit_id` |
| `quantity`, `billed_quantity` | GOODS only | `actual_quantity`, `billed_quantity` |
| `amount` | ✓ | `amount` (no unit rate for ACCOUNT/SERVICE lines) |
| `price_basis` | | `NET_EXCL_TAX` (default) / `GROSS_INCL_TAX`, if the policy allows |
| `discount_pct` / `discount_amount` | | One line DEDUCT component, only if purchase policy allows manual discounts |
| `description` | ✓ | `description` |

Item-line custom fields belong to goods item lines and wait for slice P-C.

Invoice-level charges (freight, packing), tenders/advance allocation and TDS are a later sheet
(slice P-B), not in the first template. A column that the type's field-set hides is still
accepted (layout is not authorisation); a column denied by field policy is rejected — the
template omits it.

## 4. Validation layers

| Layer | Checks | Failure |
|---|---|---|
| L1 File | Size/row/column/cell bounds (shared `bulk_files` limits), UTF-8, version marker, header exact, no formulas/macros/external links, no duplicate headers | Job `REJECTED`, nothing staged |
| L2 Row | Types, decimal lexical form and 4-dp scale, ISO dates, enums, required columns | Row `INVALID` with sheet/row/column/code |
| L3 Grouping | Unique `import_key`; every line has a header; CSV header values agree; ≤ 200 lines/voucher; one company and one type kind per job | Voucher `INVALID` |
| L4 Masters | Exact company-scoped code (or id/external key) for type, class, supplier, accounts, items, units; active and permitted; version pinned for commit | Voucher `INVALID` (`unknown_master`, `ambiguous_master`, `inactive_master`) |
| L5 Native | `documents.write` + invoice preview inside rolled-back txn: configuration/policy, field policy on changed-field set, custom-field validators, company features, tax-date contract, `assert_postable` readiness for `posting_date` | Voucher `INVALID` with native error codes |
| L6 Duplicates | Same supplier bill number + supplier bill date, plus the job's `duplicate_rule`: the supplier party (`DATE_NUMBER_PARTY`, default), the supplier ledger (`DATE_NUMBER_ACCOUNT`) or nothing (`DATE_NUMBER`). Checked within the file, against existing non-cancelled vouchers (including earlier jobs' drafts) and again at commit | `INVALID` (`duplicate_supplier_invoice`) |
| L7 Control | Computed total vs `supplier_declared_total` within `supplier_difference_limit`; currency/rate consistency | Outside limit `INVALID`; inside but non-zero `WARNING` needing a reason |

Errors expose safe codes and column names, never submitted values beyond the user's own
cell, internal identifiers or SQL. Dependants of an invalid row are `BLOCKED`.

## 5. API (company prefix `/v1/companies/{company_id}`)

All writes take `Idempotency-Key`, return 202 and `Idempotency-Replayed`; lists use signed
cursors (50/200) with lean `ListItem` schemas per [api-conventions](api-conventions.md).

| Method/path | Purpose |
|---|---|
| GET `/voucher-import-templates?voucher_type_id=&format=CSV\|XLSX\|JSON` | Authorised template for the type's current revision |
| POST `/voucher-imports` | Stage file (base64 CSV/XLSX) or JSON batch; mode `CREATE_ONLY` |
| GET `/voucher-imports`, `/voucher-imports/{id}` | Lean job list; job status, counts, digest, version |
| GET `/voucher-imports/{id}/vouchers`, `/vouchers/{key}` | Per-voucher result with computed totals and row errors |
| POST `/voucher-imports/{id}/validate` | (Re)validate selected or all unfinished vouchers |
| POST `/voucher-imports/{id}/commit` | `expected_version` + `selection_digest` + `on_error` |
| POST `/voucher-imports/{id}/cancel` | Stop future vouchers; created drafts remain |
| POST `/voucher-imports/{id}/run` | Advance a validating or committing job by one bounded step |
| GET `/voucher-imports/{id}/report-ticket?format=CSV\|XLSX` → `/report?token=` | Signed five-minute, actor/job/version-bound download (§5.14) |

## 6. Storage (Vouchers DB, one DDL per revision)

| Table | Grain | Notes |
|---|---|---|
| `voucher_import_job` | Job | Tenant/company, actor, kind, type revision, format, schema version, mode, on_error, status, version, digest, counts, expiry |
| `voucher_import_artifact` | Uploaded file / result report | Private bytes, hash, size, media type; purged after 7 days |
| `voucher_import_row` | Staged voucher (change set) | `import_key`, normalised input JSON, source rows, state, errors, computed totals, pinned master versions |
| `voucher_import_effect` | Committed voucher | Unique `(job_id, import_key)`; resulting `voucher_id`/revision; written in the voucher's transaction |

Duplicate detection reads `voucher_invoice_detail` through `ix_voucher_invoice_supplier_number`
and is repeated at commit under the company voucher lock (no separate unique claim). The job
column `duplicate_rule` (0082) records which rule the uploader chose.
Every table gets a cross-tenant isolation test.

## 7. Permissions

New catalogue keys `vouchers.import.read`, `vouchers.import.manage` (template, upload,
validate, cancel) and `vouchers.import.commit`. They supplement, never replace,
`vouchers.create` (and field policies), which the **original uploader** must still hold at
commit; the worker uses the actor's fresh authority per voucher, not a service credential.
Jobs and reports are private to the uploader and company; a tenant auditor gets read only.
Wrong-company job access → 403. Upload and commit are rate-limited (§5.13). Updates
[roles-permissions](roles-permissions.md) §2/§6, system roles and seeds.

## 8. Phases

Each phase ends green with the repo working; progress is reported per phase.

| Phase | Deliverable | Exit evidence |
|---|---|---|
| **I0** Decisions | Answers to §10; this doc moved to AGREED; tracker/todo rows | Decision log entry |
| **I1** Shared mechanism | Inventory Catalog `bulk_jobs/execution/reports/worker`; promote only service-neutral parts (job state machine, chunk checkpoint, digest, report rendering, artifact purge) to `libs/platform`; Catalog consumes them with its tests untouched; version bump + lockfiles | Catalog suites unchanged and green; platform coverage ≥ 90% |
| **I2** Schema | Four tables (§6) as separate revisions with models, Pydantic schemas, factories; permission keys, roles, seeds | Migrations up/down on MySQL; isolation tests; mypy/ruff clean |
| **I3** Template | Template generator from type revision + effective configuration + field policy + custom fields; CSV/XLSX/JSON; example rows | Template round-trips through the parser; denied fields absent; 401/403/wrong-company tests |
| **I4** Stage + validate | Upload endpoint, parser adapter, L1–L7 validation worker, results/list endpoints | Each error class has a fixture; validation leaves zero vouchers/audit rows; digest stable |
| **I5** Commit + result | Commit worker, effect/idempotency, STOP/CONTINUE_INDEPENDENT, cancel, resume after crash, report download | Crash after commit → one draft on retry; revoked permission after validate blocks commit; report sanitised against formula injection |
| **I6** Console UI | Vouchers MFE "Import" screen: pick type → download template → upload → validation table (filter by state, row errors) → commit confirmation → result + report; components in `@janso/ui` where shared; regenerated `clients/api-client` | Vitest/RTL for every state (pending/success/failure/401/403/422/500), permission-gated actions, non-`en` money/date formatting |
| **I7** Review | §5/§6 walk, `/simplify`, `/security-review`, tracker evidence, CLAUDE.md doc row | Findings reported, including "nothing" |

Follow-on slices (separate agreement): **P-B** purchase charges/components, TDS and advance
allocation; **P-C** goods lines once B24 lands; **P-D** Sales, Debit/Credit Note, Payment/Receipt
and Journal templates reusing the same engine with per-kind adapters.

## 9. Acceptance (VIM01–VIM18)

VIM01 template matches the type's current revision and omits read/write-denied fields ·
VIM02 template → filled → upload round-trips with no edits · VIM03 formula/macro/oversize
files rejected · VIM04 float-like and >4-dp values rejected · VIM05 unknown/ambiguous/inactive
master codes rejected, never created · VIM06 CSV header disagreement within a voucher rejected ·
VIM07 duplicate supplier invoice within file, against existing vouchers and across jobs ·
VIM08 supplier total outside tolerance invalid, inside needs reason · VIM09 validation creates
no voucher, receipt, audit or outbox row · VIM10 closed/unready period reported for `posting_date` ·
VIM11 stale digest/version or changed configuration requires revalidation · VIM12 permission
revoked after validation blocks commit · VIM13 crash/redelivery yields one draft per voucher ·
VIM14 STOP vs CONTINUE_INDEPENDENT outcomes and PARTIAL status · VIM15 cancel keeps created
drafts and reports them · VIM16 cross-tenant and wrong-company access to jobs/reports denied ·
VIM17 money fields returned as `Decimal`/decimal strings end to end · VIM18 report download
link expires and re-checks authority.

## 10. Decisions (formerly open questions)

- **Q1 Import outcome — drafts only.** No submit, approval, numbering or posting from import.
- **Q2 First-slice lines — ACCOUNT/SERVICE only.** GOODS waits for slice P-C (B24/C3).
- **Q3 Tax — native calculation.** The file carries only `supplier_declared_total` as a
  control figure checked against the policy's `supplier_difference_limit`.
- **Q4 Shared engine — reuse what is already shared.** `billing_platform.bulk`
  (`selection_digest`, reference ordering) and `billing_platform.bulk_files` (bounded
  CSV/XLSX reading, formula-safe CSV/XLSX writing) already hold the service-neutral parts.
  Vouchers consumes them; anything else is promoted only when a second copy would appear, so
  I1 shrinks to "consume, do not copy".
- **Q5 Master keys.** Accounting `party` and `account` codes are unique per
  `(tenant_id, company_id, code)` (`uq_party_0`, `uq_account_0`). Supplier is matched by exact
  party code, or by GSTIN as an alternative key; ledgers by exact account code.
- **Q6 Code resolution — owner lookup at validate.** Vouchers holds no code→id replica
  (`voucher_master_evidence` is keyed by `source_id`). The validation worker resolves exact
  codes through the owners' read APIs outside any money transaction, then pins id + version in
  the staged row. Commit reuses the pinned references, and the native write re-checks them
  exactly as for an API-entered draft.

## 11. Implementation record (2026-10-14)

| Phase | Delivered | Evidence |
|---|---|---|
| I1 | `billing_platform` 0.32.0: `bulk_files` takes a service marker (`_voucher_schema_version`) and writes multi-sheet workbooks (`xlsx_workbook`); three import permission keys. Every service/client lockfile relocked | Platform suite 1057 passed, 97.99% coverage; Catalog bulk suites unchanged |
| I2 | `voucher_import_job`, `voucher_import_artifact`, `voucher_import_row`, `voucher_import_effect` (0077–0080, one DDL each) and `ix_voucher_invoice_supplier_number` (0081). Effects are immutable. Roles: BillingClerk all three keys, TenantAuditor read | Isolation contract seeds every new table for two tenants; `tools/verify_mysql.py` |
| I3 | Template from the type's current revision, effective configuration, live field policy and header custom fields (CSV flat, XLSX `vouchers`/`lines`/`instructions`, JSON). A denied required field refuses the template; a denied optional field drops its column | `test_imports_api.py`, `test_imports_domain.py` |
| I4 | Stage (L1–L3 plus in-file duplicates), validation L2–L7, results and lists. Master codes resolve through the new signed Accounting route `POST /internal/v1/voucher-lookups/{tenant}/{company}` (snapshot credential, exact codes, no names) | Rolled-back dry run leaves no voucher or voucher audit event; Accounting `test_voucher_sources.py` |
| I5 | Commit (STOP / CONTINUE_INDEPENDENT, exclusions), per-voucher native create with key `voucher-import:{job}:{import_key}`, effect and row state in that transaction; cancel; signed report (CSV/XLSX, formula-safe) with `report_access` audit | Partial/blocked outcomes, stale master refusal, replay and revoked-permission tests |
| I6 | Console “Import purchase vouchers” on the vouchers page, proxy file passthrough, regenerated `clients/api-client` | Console suite 31 files / 354+ tests |

Deviations from the proposal, decided during implementation:

- **No background worker.** Validation and commit run in bounded steps of 20 vouchers inside
  authenticated requests (`validate`/`commit` run the first step, `run` continues). Native
  writes refuse a signed company context older than 60 s and need its finance, field-policy and
  delegated-authority content, which only the live gateway request carries. Running inside
  the uploader's request is what makes “the actor's fresh authority per voucher” true without
  a new Identity protocol. Jobs are therefore changed only by their uploader.
- **L7 uses the owner's payable.** Validation calls the Accounting invoice preview without the
  declared total and classifies the difference locally, so the result can name the exact
  `supplier_total_mismatch` or `difference_reason_required`. The draft keeps the declared
  total and reason; posting recalculates.
- **Duplicates** compare the bill number and bill date, plus the supplier party or ledger as
  the job's `duplicate_rule` selects, against live (non-cancelled, current-revision) vouchers.
  Commit repeats the check under the company voucher lock, so two jobs cannot both create the
  same bill. No new unique claim was needed.
- Missing template columns are treated as empty (required values are checked per row); unknown
  or policy-denied columns are refused. Expired uploads are blanked when the company next stages.
- The upload route alone accepts up to 12 MiB of request body; others keep 256 KiB. Upload,
  validate, commit and run share an import rate limit of 30 per minute per user.

Review (I7, 2026-10-14) — `/simplify`-style and security reviews of the change. Fixed, each
with a regression test:

- Accounting codes are collated case-insensitively. The lookup now matches by casefold; a
  differently cased code had previously been treated as an unrequested master (401) and
  stalled the job. Lookups are batched at the owner's 500-code bound. Owner outages, refusals
  and bad signatures become a retryable 409 with the rows left `STAGED`.
- Other users' jobs need `vouchers.operation.read`. Read-denied invoice content blanks the
  amounts and cells in rows, details and the report.
- Lock contention ("request is busy") during commit leaves the voucher selected for the next
  step instead of failing it (and, under STOP, blocking the rest). Cancel during commit
  recounts created and failed drafts.
- A column denied after upload is refused at validation (L1 `unknown_column`), never dropped.
  The template also omits read-denied fields.
- JSON uploads with non-text values return 422. Import keys are compared case-insensitively,
  matching the store, and may not contain `..`.
- Reports: plain negative decimals are no longer prefixed as formulas, and XML-invalid control
  characters are stripped from workbook cells (`billing_platform` 0.32.0).
- Purging an expired upload also blanks the staged cells. `run` checks permission before
  reading the job, and steps have their own rate limit (120 per minute). The console pages
  through every result before asking for review, keeps the object URL long enough to
  download, and can resume a working job.
- Quality: shared row query, `Counter` counts, one owner check (also used by the invoice
  preview), `Staged.from_stored`, `_admit`, and one format-to-media map.

Not changed: the quality review suggested folding `job_command` into `common.command` and
splitting `validate_step` into smaller functions. Both are behaviour-neutral and left for a
follow-up, to keep this change reviewable.

Remaining follow-ons: P-B (charges, TDS, advances), P-C (goods and item-line custom fields),
and the inventory, order, job-work and memorandum kinds (not planned yet). GSTIN lookup scans the
company's GST registrations, which have no registration-number index. Add one if registration
volumes grow.

## 12. P-D: the other important kinds (2026-10-15)

Each kind's check follows what identifies its document, from
[vouchers-plan](vouchers-plan.md) §2.1 and §3.4, not one shared pattern. "Error" rejects the
voucher; "warning" lets it through marked for review. Our own document numbers are allocated
on posting (CLAUDE.md §6.6), so they are never an import identity.

| Kind | What it records | Identity checked | Severity | Other import checks |
|---|---|---|---|---|
| Purchase | Supplier bill | Bill number + bill date (+ supplier or ledger, per job); same supplier and number in the financial year on another date | Error; warning (GST numbers are unique per supplier and year) | Supplier total vs payable |
| Sales | Our invoice | `source_reference` (source-system ID) once per company; without one, same customer ledger + date + line total | Error; warning | Customer ledger role; owner calculation |
| Credit Note | Return/reduction of our Sales invoice | Return reference per customer; returned amount per original line ≤ remaining (owner's posted claims + unposted drafts) | Error | Posted untaxed original without components; same ledger and currency; not before the original; adjusts the original bill up to its outstanding |
| Debit Note | Return/reduction of a supplier bill | As Credit Note, against the Purchase original | Error | As Credit Note |
| Payment | Money out | Our cheque leaf (bank ledger + number); transfer reference on the bank ledger; cash: same date, ledgers and amounts | Error; warning for cash | Bank/cash lines are credits with one tender; party lines tracked; settling a bill ≤ its outstanding (owner + unposted drafts) |
| Receipt | Money in | Received cheque (bank ledger + number + date + amount); transfer reference; cash signature | Error; warning for cash | Bank/cash lines are debits; settling a customer bill only |
| Contra | Own cash/bank transfer | Transfer reference or cheque on the bank ledger; otherwise signature | Error; warning | Only two different cash/bank ledgers |
| Journal | Accrual or correction | Same date, ledgers, sides and amounts | Warning only | No cash/bank ledger unless the type allows; no tenders |

Implementation:

- **Kind adapters.** `domain/import_kinds.py` maps each kind to its family. Invoice kinds use
  `domain/imports.py` (per-kind columns, with supplier/customer names in the file). Money kinds
  use `domain/import_money.py` (entry rows with side, tracking, bill and tender columns). Every
  kind keeps staging, the dry-run native write, results, commit and the report from the
  Purchase engine.
- **Probes** (`domain/import_checks.py`) are JSON facts stored with each validated row. They
  are checked against existing vouchers inside the dry run, across the job at the end of
  validation, and again at commit under the company voucher lock. Consumption probes
  (`entitlement`, `allocation`) record the owner's remaining amount. At commit the total,
  including this draft and the job's earlier drafts, must stay within it. Posting re-checks
  the owner's posted total.
- **Owner lookup** returns ledger facts (kind, party role, posting policy), open bills by ledger
  and reference with their remaining amount today, and original invoices with each line's
  remaining return entitlement. The entitlement helper is shared with posting
  (`claimed`, `committed_source`). A second lookup in each step asks for bills and originals
  once ledgers resolve.
- **Schema:** 0083 widens the job kind check; 0084 and 0085 index tender references and document
  references for duplicate lookups. The duplicate-rule choice stays Purchase-only (others → 422).
- Validation needs the invoice-calculation owner for invoice kinds only.
- Unposted drafts count against balances until they post or are cancelled. While a posting is in
  flight, the same amount can be counted by both the owner and the draft for a moment. The
  error is conservative (a valid voucher may be refused), never permissive.
- A field-policy deny on `references` drops the source and return references from the draft;
  such imports cannot be recognised again by reference, only by the warning signature (Sales).

Pre-publication review (2026-10-15): excluded `checked_at` from consumption comparison keys.
Rows validated at different instants now share the same original-line entitlement or bill
balance when checking cumulative amounts. The regression checks cover both returns and bill
allocations, with distinct validation timestamps in the domain collision test.

## Decision log

- 2026-10-23: Enhanced shared import mechanisms, immutable revisions/attempts/results,
  configuration snapshots, TSV, correction/retry, private downloads and retention.
  Native voucher jobs/effects remain canonical; see the
  [execution record](voucher-import-enhancement-execution.md) for API contracts,
  integration refinements, migration/retention decisions, reviews and verification.
- 2026-10-13: Plan proposed. Purchase first; drafts only; validation is a rolled-back dry run;
  one voucher per transaction; masters matched exactly; tax computed natively. Awaiting Q1–Q5.
- 2026-10-14: Agreed. Q1 drafts only, Q2 ACCOUNT/SERVICE, Q3 native tax + control total,
  Q4 reuse existing `libs/platform` bulk primitives, Q5 party/account codes (GSTIN alternative
  for supplier), Q6 owner lookup at validation with pinned versions.
- 2026-10-14: Implemented I0-I6. Bounded in-request steps replace the proposed worker; reasons
  and the other deviations are in section 11, followed by the review fixes.
- 2026-10-15: Duplicate rule changed from "supplier + number + financial year" to "number +
  bill date", with the supplier party (default) or supplier ledger optionally included. The
  uploader chooses per job (`duplicate_rule`, migration 0082); the rule is part of the stage
  idempotency request and the review digest.
- 2026-10-15: P-D implemented for Sales, Credit/Debit Note, Payment, Receipt, Contra and
  Journal, with per-kind identities (§12). Purchase also warns on the same supplier number in
  the financial year on another date.
