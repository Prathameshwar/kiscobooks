# Voucher import enhancement execution — 2026-10-23

Scope: API, database and generated API contracts. Vouchers owns the import and
creates ordinary **drafts only**. UI changes, posting, GOODS import and additional
inventory/detail sheets are outside this delivery. The existing eight kinds are
Purchase, Sales, Credit Note, Debit Note, Payment, Receipt, Contra and Journal.

## Architecture and rollout decision

The canonical `voucher_import_job`, row and effect identities are retained.
Shared parsing, spreadsheet rendering, signed downloads, template storage,
revision/attempt/result evidence mixins, continuation budgets and cleanup entry
point are reused from `billing-platform` 0.39.0. Voucher grouping, owner lookups,
dry-run calculation and native draft commands remain service-owned.

This refines the proposed integration in the [review](voucher-import-review-2026-10-23.md):
there is no second generic job mirroring the native job and no competing worker.
The generic master-import engine does not replace the voucher transaction boundary.
Each voucher's native receipt, effect, result and row checkpoint commit together;
owner HTTP calls remain outside voucher write transactions. Legacy in-flight jobs
capture revision evidence lazily before their next attempt/checkpoint. Successful
effects and native idempotency keys survive retry and correction.

Migrations **0086–0097** add a shared template snapshot and three voucher evidence
tables, extend job lifecycle/format/revision fields, backfill row error counts, add
retention/list indexes, and enforce scoped type, voucher, revision and job links.
Each revision has one DDL per direction. Apply migrations before the API release.
Downgrades must not be used to discard new TSV/EXPIRED data; the lifecycle CHECK
constraint intentionally refuses incompatible retained rows.

## Delivered phases

1. Correctness: field-read revocation masks source and monetary data; dated financial
   configuration receives posting context; custom definitions and normalization
   context are fingerprinted; expired jobs cannot continue; typed XLSX values are
   rejected when the template requires exact text. Original review probes became
   seven regression cases before repairs.
2. Shared execution: record/time budgets bound continuations; parsing/rendering run
   off the event loop; validation remains a dry run and commit uses native commands.
   Existing stage/validate/commit/run/report paths remain available.
3. Database: immutable source revisions and completed attempts/results; scoped foreign
   keys and unique keys; deferred source blobs; scalar list projections; indexed
   expiry/state/history traversal. An attempt cannot reference another job's revision.
4. Templates and transport: CSV, TSV and XLSX, retaining JSON compatibility. Snapshot
   requests specify document/posting dates and optional class. Snapshots include
   effective policy, permitted active custom definitions/choices and bounded class
   choices, with truncation metadata. Master codes resolve at Accounting during
   validation; templates do not enumerate entire party/account directories.
5. Correction/retry/history/downloads: append immutable input revisions, retry
   unfinished rows after validation, and preserve successful vouchers unchanged.
   Corrections must retain already-created logical keys and their original cells.
   Every new commit requires the new validation digest. History is cursor-paginated.
6. Two review passes: behavioral/security review and database/concurrency/retention
   review, followed by fixes and regression verification (evidence below).
7. Cleanup: bounded, company-scoped maintenance; expiry coordinates with job locks,
   invalidates pending review, ends active attempts and emits system audit evidence.
   Cleanup never deletes native vouchers or import effects.

## Additive API contract

All routes are under `/v1/companies/{company_id}` and enforce current signed authority.

| Route | Behavior |
|---|---|
| `POST /voucher-import-template-snapshots` | Create a private, idempotent configuration snapshot |
| `GET /voucher-import-template-snapshots/{id}` | Read after current authority/configuration checks |
| `GET /voucher-import-templates` | Download CSV/TSV/XLSX/JSON; optional document/posting dates and class |
| `POST /voucher-imports` | Stage; optional `template_id` binds checked snapshot parameters |
| `POST /voucher-imports/{id}/revisions` | Correct input using `expected_version`; immutable prior revision |
| `POST /voucher-imports/{id}/retry` | Revalidate unfinished work; preserves successful effects |
| `GET /voucher-imports/{id}/history/{attempts\|revisions}` | Paginated history |
| `GET /voucher-imports/{id}/attempts/{attempt_id}/results` | Immutable result evidence, current masking |
| `POST /voucher-imports/{id}/download-ticket` | Five-minute actor/job/version/options-bound ticket |
| `POST /voucher-imports/{id}/download` | SOURCE, NORMALIZED, CORRECTION or RESULT |

Downloads recheck ownership, permissions, field readability, ticket and job version.
They are private, `no-store` responses and produce access audit evidence. SOURCE
returns original bytes and their original extension. Other kinds support CSV,
TSV, XLSX and JSON. Results include status, draft ID, messages and source locations.
Normalized/correction files are suitable for re-upload; result files are reports.

Limits remain 8 MiB source, 500 vouchers/job, 200 lines/voucher, shared spreadsheet
record limits, and 20 vouchers per continuation. Each job allows at most 20 source
revisions and 100 attempts, bounding retained payload/result growth. A 35-second cooperative budget
stops between records; a single in-progress owner/database operation may finish
after that deadline. Cancellation retains already-created drafts.

## Retention and operator cleanup

Original bytes, normalized input snapshots and prepared input expire after seven
days, measured from job creation (correction does not extend retention). Template
payloads also expire after seven days. Validation/commit results remain available
for 365 days; after source expiry, RESULT downloads contain retained result summaries
without original input cells. Jobs, source hashes/revision identifiers, effects,
native drafts and business/audit evidence remain.

Schedule this command per tenant/company using the Vouchers database credential:

```powershell
uv run --project apis/vouchers python -m vouchers.tasks.import_cleanup --tenant <tenant-uuid> --company <company-uuid> --limit 50
```

`VOUCHERS_DATABASE_URL` is required. Repeat bounded invocations until all returned
counts are zero; run periodically even when there are no new uploads. The command
uses the guarded session factory, skips locked jobs, emits audit evidence and is
safe to repeat. It neither installs an operating-system schedule nor enumerates
other tenants. Uploads also run bounded opportunistic cleanup.

## Review fixes and verification

Pass one fixed snapshot disclosure through optional read-denied fields, propagation
of snapshot dates/class into staging/correction, and source line locations in reports.
Pass two fixed omission of header-only invalid vouchers from reports, result download
availability after source expiry, failure-checkpoint lock order, deterministic
snapshot choice ordering, attempt-to-job revision linkage, currency masking and
download audit classification. Legacy error counts are backfilled by migration.
Retention reads avoid loading expired input/result JSON before deletion; revision
and attempt caps bound per-job retention work.

The `/simplify` and `/security-review` commands are unavailable in this environment;
equivalent manual reviews covered duplication, ownership, field revocation,
idempotency, transactional effects, download authorization, bounds, cleanup and
audit data. No user data or production schema was used for verification.

| Verification | Result |
|---|---|
| Shared platform full suite | 1,125 passed; 93.85% branch-aware coverage (90% gate) |
| Initial import/isolation/schema acceptance | 84 passed |
| Native MySQL import/isolation/schema suite | 67 passed, including concurrent commits and cross-job revision rejection |
| Final native maintenance/review regressions | 8 passed; covers final retention caps and lean cleanup reads |
| Native migrations | Empty database to 0097; model/column/index/FK parity; downgrade to base and re-upgrade passed |
| Import query plans | Owner-scoped expiry, attempt, result and snapshot queries use indexed `ref` access on the disposable schema |
| Generated TypeScript client | Regeneration/check, type checking and 8 tests passed |
| Static checks | Ruff for changed import code/tests/tool and strict mypy for 9 voucher + 2 shared modules passed |
| Broad voucher regression/coverage run | 321 passed, 3 skipped; 94.45% domain coverage; one existing real-clock throttle test failed and was repaired as described below |
| Final affected-group rerun | 35 passed, 1 native-only case skipped on SQLite; the native concurrency case already passed on MySQL |

The broad run exposed a timing-sensitive assertion in
`test_phase2_review.test_http_write_throttle_and_body_bound`: filling a real-clock
rate window can cross its boundary before the HTTP assertion. The test now supplies
a controlled limiter clock, verifies rejection in the full window, then advances
one window and verifies acceptance. The entire affected test module plus final
import/cleanup regressions passed on rerun. Production throttling was unchanged.

Native owner responses were stubbed in API tests; no live Accounting posting or
RabbitMQ integration was required for this draft-import change. The temporary
MySQL instance was shut down after verification. Application database deployment
and installation of the operator schedule remain release actions.

## Decision log

- 2026-10-23: User authorized the reviewed API/database phases, uninterrupted delivery,
  final reviews and fixes. Retain native voucher job/effect identity and compose shared
  mechanisms rather than duplicate execution state. Preserve existing draft-only,
  owner-lookup, exact-text and import-size contracts. Keep seven-day source retention
  and add 365-day immutable attempt-result retention with summary downloads.
