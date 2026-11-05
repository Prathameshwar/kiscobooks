# Voucher import API and database review

Implementation follow-up: [execution record](voucher-import-enhancement-execution.md).
The findings below describe the pre-enhancement baseline.

Review date: 2026-10-23. Scope: existing voucher imports, their native draft boundary,
database models/migrations, tests, and integration with the shared master import
framework. This is a review and proposed implementation sequence; application code
and database schemas were not changed during the review.

## Current implementation

The Vouchers API owns `/v1/companies/{company_id}/voucher-import-templates` and
`/voucher-imports`. Supported kinds are Purchase, Sales, Credit Note, Debit Note,
Payment, Receipt, Contra and Journal. Invoice imports support ACCOUNT/SERVICE
supplies; GOODS is explicitly deferred. Standard profiles are supported, plus
ADVANCE for Payment/Receipt. Imports create drafts only.

CSV, XLSX and JSON inputs are supported. A job holds at most 500 vouchers, each
with at most 200 lines, subject to the 8 MiB input and shared spreadsheet bounds.
The shared spreadsheet reader has a 2,000-record total bound; the per-voucher and
per-job maxima therefore cannot all be reached simultaneously in a spreadsheet.
Validation/commit advance in authenticated steps of 20 vouchers. There is no
background import worker. `/run` resumes a working job.

Four service-local tables store jobs, original artifacts, mutable staged voucher
rows and immutable effects. Migrations 0077–0080 created these tables; 0081 added
the supplier invoice lookup index, 0082 the duplicate rule, and 0083 widened kinds.

Existing strengths worth preserving:

- Native `documents.write` and configuration/master/field validation are reused.
- Validation writes are rolled back; effects and native draft receipts commit
  together for each voucher. Drafts are never automatically numbered or posted.
- Commit takes an expected version and selection digest; successful effects have
  unique job/key identities. Replaying a successful command does not create a
  second draft.
- Owner lookup/calculation calls occur outside local write transactions.
- Company/tenant boundaries, current signed authority, signed report tickets,
  file bounds, formula rejection and private-response headers already exist.
- Kind-specific duplicate, bill allocation and return entitlement checks are
  more specialized than the shared master-import engine and must be retained.

## Confirmed defects

### P1: Individual read-denied custom fields remain visible in staged data

`tasks/imports.py:1468` only checks a fixed set of broad content fields.
`row_view` then returns the uploader's complete `source_input`. It does not apply
the native per-custom-field read mask. A `custom_field:cf_secret` read deny added
after staging still allows `/voucher-imports/{id}/vouchers/A` to return its value.

Reproduced through the API with an adopted custom definition and signed field
policy. Apply current field policy to every submitted native/custom cell, including
conditional policy, on detail and downloads. Exact source downloads must refuse
access if any contained field is now denied; they cannot be selectively redacted.

### P1: Dated financial configuration can disable import templates

`shape_for` calls `effective(... date=today)` without `posting_date` or class
(`tasks/imports.py:126`). `validate_step` repeats the same early lookup at line
930. A published/bound schema-v2 financial policy requires posting date
(`tasks/configuration.py:143`). A valid Payment type consequently returns 409
while requesting a template. The current template query has no way to supply the
missing context. Staging also calls `shape_for`, so changing input format does not
avoid the issue.

Reproduced with a published financial configuration and Payment template request.
Templates need explicit document date, posting date and optional class context;
each voucher still needs its own effective-date validation during import.

### P1: Expiry is not enforced by continuation, and cleanup can break it

`transition` checks expiry at line 486, but `validate_step`, `commit_step` and the
per-voucher mutation do not. An already COMMITTING job can pass its expiry and
create the next draft through `/run`.

Two cases were reproduced using a two-voucher job and one-voucher steps:

1. Expire the job after the first draft: `/run` creates the second draft.
2. Also expire its artifact and stage another job: opportunistic cleanup clears
   `prepared_input`, but leaves the old job COMMITTING; `/run` raises `KeyError`
   when `create_draft` reads `prepared['content']`.

Enforce expiry and payload availability under the mutation lock. Coordinate
cleanup with running work, invalidate reviews, and give expired jobs an explicit
terminal state. Never erase data still being used by a valid active step.

### P1: Custom-definition changes are absent from the review fingerprint

Validation retains the authored body and policy configuration hash, but not the
complete effective custom-definition snapshot or normalized content. Commit
compares only `revision.configuration_hash` at line 1372. That hash contains
voucher policy/type/company configuration; custom definitions are separately
resolved by the native write.

Reproduced: validate a voucher; publish a new custom field with a default; commit
using the original digest. Commit succeeds and stores the new default, even
though it was absent during validation. This violates the documented requirement
to revalidate configuration changes.

Pin effective custom definitions and relevant normalization inputs in the review
fingerprint. Reject meaningful drift before creating effects. Explicitly distinguish
values allocated at commit, such as auxiliary sequences, from reviewed content.

### P2: Recoverable failures cannot be retried within their original job

`transition` accepts validation only for STAGED/READY jobs (line 490), and
`reset_validation` refuses FAILED rows (line 450). A stale-master failure moves the
job to FAILED/PARTIAL; refreshing that master does not provide an in-place retry.
`/run` only advances VALIDATING/COMMITTING jobs. There is no revision/correction API.

Reproduced by changing a supplier version between validation and commit, then
restoring matching owner/evidence versions: `/validate` still returns 409. A new
upload has a new job/idempotency identity; duplicate checks are only warnings for
some kinds, so uploading a complete partially successful file is not an equivalent
safe retry. Preserve successful effects and revalidate only unfinished vouchers
under the original logical import lineage.

### P2: XLSX cell type is discarded before voucher parsing

The shared reader preserves `Cell.kind`; `tasks/imports.py:189` converts cells to
plain strings. Numeric spreadsheet identifiers are therefore accepted even though
the template specifies text cells. A workbook containing numeric `account_code`
123 was decoded and parsed as the text code `123` without an issue.

Retain cell type through normalization and reject numeric identifier/decimal/date
cells according to the declared template contract. This prevents silent acceptance
of codes or high-precision values already altered by spreadsheet formatting.

## API and persistence gaps

| Area | Current gap | Required enhancement |
|---|---|---|
| TSV | Absent from schemas, transport and DB format check | Add TSV through shared parsing/rendering and a matching reversible constraint migration |
| Templates | No persisted template ID/config snapshot; static kind columns and examples; no active option snapshot | Persist effective schema/date/class/definition fingerprints and authorized option references |
| History | Revalidation overwrites row errors/prepared input/totals | Immutable input revisions, attempts, per-attempt results/issues and explicit source links |
| Downloads | Only a summary CSV/XLSX report; original bytes are stored but no source-download API | Source, normalized input, correction and attempt-specific validation/import report downloads |
| Result content | Report includes selected header fields, status/messages and draft ID; not the original line data | Trace each source row/column to its voucher, attempt, outcome and resulting draft |
| Retry | No correction revision or retry API | Revalidate unfinished vouchers, preserve successful parent/effect identities, then require a new review digest |
| Cleanup | Runs only during another stage request; fixed seven-day expiry; no cleanup audit call; no scheduled owner-scoped sweep | Bounded maintenance command/scheduler integration, explicit retention policy, locking and audited expiry/purge |
| List queries | `row_page` selects complete ORM rows, including source/prepared JSON and errors, to return a lean list | Select only list columns and stored/derived error count; defer private payloads |
| Indexing | Artifact expiry has no dedicated scope/expiry index; filtered job history has only the actor/id index | Add indexes for actual cleanup and state-filtered history query shapes; verify native query plans |
| Relationships | Job type/revision and effect revision IDs lack some scoped relational checks | Add same-company type/revision links and ensure effect revision belongs to the referenced voucher; retain immutable effects |
| API contracts | Template/report OpenAPI success content omits supported XLSX media type | Regenerate complete binary response contracts and typed clients |
| Request work | Parsing/template/report rendering is synchronous; steps are count-bounded, not elapsed-time bounded | Reuse bounded off-loop file processing and stop/checkpoint before request authority/time budgets expire |

The cleanup policy must be reconciled explicitly: voucher import currently uses
seven days; the new master framework uses 30-day payloads and 365-day detailed
history. Preserve a documented owner policy rather than silently changing it.

## Shared framework integration

Implementation belongs in the **Vouchers API and Vouchers database**. Accounting
remains the owner of its lookup/calculation/posting capabilities; it must not own
voucher import job storage.

Reuse the common file transports, snapshots, revisions, attempts, effects,
downloads, pagination, retention mechanisms and API vocabulary from
`billing_platform.import_*`. Keep voucher grouping, draft construction, duplicate
rules, bill/return probes, native permissions and money rules in Vouchers.

The shared engine is not currently a drop-in replacement: it has a 200-command
request bound and a transaction-scoped attempt, while Vouchers supports 500
vouchers, remote preflight calls, 20-voucher resumable steps and one committed
transaction per voucher. Extend the common execution contract with explicit
preflight/checkpoint hooks and adapter-specific bounded capacities. Do not put
owner HTTP calls inside the shared database transaction or increase master-import
limits as a side effect. Preserve existing operator/auditor access rules.

Use one canonical workflow for new imports. Keep old API paths as compatibility
adapters and retain existing jobs/effects as historical evidence during rollout;
do not let old and new engines execute the same job independently. Shared tables
are instantiated in the Vouchers database with service-owned migrations. Retain
voucher-specific typed linkage/probe evidence where the generic schema is not
sufficient.

## Proposed implementation sequence

1. **Correctness repairs:** field masking, dated configuration context, complete
   review fingerprints, expiry/cleanup coordination and typed XLSX cells. Turn
   each review reproduction into a failing regression before applying the fix.
2. **Shared execution integration:** voucher preflight and bounded continuation,
   per-voucher transaction/effect semantics, compatibility routing and a concrete
   transition plan for existing jobs. Preserve draft-only operation.
3. **Database foundation:** snapshots, immutable revisions/attempts/results,
   voucher links/effects, scoped constraints and query indexes. One DDL per
   reversible migration; model parity and native upgrade/downgrade tests.
4. **Transport/templates:** CSV/TSV/XLSX plus existing JSON compatibility;
   date/class-aware schemas, authorized active options and source-row grouping.
   Support the existing eight kinds first. Keep GOODS and additional detail
   sheets as separately specified domain enhancements after these gates pass.
5. **Review/retry/download APIs:** retain stage/validate/commit/run; add revisions,
   retry, immutable attempt history and typed download tickets for source,
   normalized, correction and validation/import results. Successful vouchers must
   never execute again because another voucher was corrected.
6. **Acceptance and two reviews:** all eight kinds; rollback; tenant/company and
   field revocation; configuration drift; duplicate/over-consumption races;
   concurrent continuation/cancel/retry; crash recovery; decimal fidelity; client
   contract checks and MySQL migration/query-plan verification. Fix each review.
7. **Cleanup last:** operator maintenance entry point, retention/index checks,
   safe expiry during work, audit evidence and payload/history purge; preserve
   imported drafts, effect identities and business/audit history.

## Verification evidence and limits

- Existing six import test modules: **42 passed** in 45.40 seconds.
- Seven additional review reproductions: **7 confirmed**, covering six findings
  (expiry has both continuation and purge variants). These probes assert existing
  defective behavior; their passing does not mean the defects are fixed.
- Probes are retained locally in `.tools/test_voucher_import_review.py`; run logs
  are `.tools/voucher-import-review-tests.log` and
  `.tools/voucher-import-review-probes.log`.
- Tests used isolated SQLite fixtures and stubbed owner responses. This review
  inspected native migrations and constraints but did not rerun MySQL concurrency,
  owner-service end-to-end calls or migration roundtrips. Those remain explicit
  implementation acceptance gates.
- Application code and production data were not modified. UI is outside this review.
