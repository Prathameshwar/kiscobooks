# Shared master import framework

Approved scope: API and database only. Accounting owns customers/suppliers and
their child masters; Catalog owns goods/services and prices. Existing import APIs
remain compatible. No cross-service SQL, business rules or UI in the framework.

Follow-up decision (2026-11-04): attempt downloads select their original revision
and recheck its authority. Retained result enrichment requires an exact input
match, so a corrected row cannot rewrite a prior failed report. Generated XLSX
columns use Text formatting for new entries as well as existing cells, preserving
business codes and exact decimal text. See [the review record](simple-product-import-review.md).

## Delivery phases

1. Shared contracts, bounded CSV/TSV/XLSX transport and adapter boundary.
2. Service-local persistence and reversible, single-DDL migrations.
3. Configuration snapshots, templates, active options and original file retention.
4. Rollback-only native validation with immutable attempts and field issues.
5. Reviewed commit, aggregate isolation, dependency handling and safe retries.
6. Signed downloads, reports, original/normalized inputs and history.
7. Accounting and Catalog adapters, generated contracts and verification.
8. Two review/fix passes, then bounded retention cleanup and final verification.

## Execution contract

The first release bounds a job to 200 commands (Accounting's existing native
batch capacity), 100 commands per aggregate and 8 MiB across source files. This
keeps validation and execution inside the existing 30-second command boundary.
Parsing/rendering run off the event loop. Operations are request-driven; clients
receive the completed bounded attempt, with durable history and idempotent replay.
There is no new background worker credential store. Expanding capacity requires
the leased worker/renewed-authority protocol, not increasing these limits alone.

2026-11-04: opt-in independent-row adapters can process one group per request,
retaining VALIDATING / IMPORTING progress and immutable attempt results. Simple
product creation uses this mode with a 60-second per-row request ceiling and
fresh gateway authority on every continuation. Native creation receipts execute
outside import transactions and are checkpointed as PENDING until complete;
admission alone never increments completed_count. Other adapters keep their
existing transaction and request limits.

Every source row has a logical key and aggregate key. Explicit references use
`{"$ref":"key","field":"id"}`; ordering is determined by the shared graph.
CSV and TSV use the same columns and version marker as XLSX. Complex values use
exact JSON text; decimals and identifiers are text. Legacy .xls is not accepted.
An empty update cell omits the field; `_clear_fields` explicitly clears it.

Templates snapshot the effective schema/configuration and authorized options.
Layout visibility does not grant or deny API fields. Active options are guidance;
native commands always recheck applicability. Business/configuration changes
between validation and commit require revalidation. Successful aggregates cannot
be edited or removed by a revision or executed again by retry.

Validation invokes normal commands in a transaction/savepoint that is rolled back
before validation results are persisted. Preview identifiers never become target
identifiers. Commit stores business writes, native receipts, aggregate effects,
results and audit/outbox evidence in one transaction. Attempts remain immutable.

Original bytes, template snapshots and normalized revisions expire after 30 days;
detailed row/attempt history is retained for 365 days. Job summaries, revision
hashes, effects and audit remain available under existing retention rules.
Cleanup erases payloads, not business effects, and skips locked jobs.
Accepted input awaiting admission and pending owner-command history survive their
normal cleanup deadlines so recovery remains possible. Download deadlines and
current native permissions still apply.
Downloads require current company/object/field authority and short-lived signed
tickets; exact originals cannot be selectively redacted.

## Decisions

- 2026-10-23: user approved phased implementation and two reviews with fixes;
  cleanup is the last delivery phase. Shared mechanism is installed in each owner
  database; old Catalog bulk jobs and Accounting JSON imports are not rewritten.
- Initial capacity is deliberately 200 commands with bounded request execution;
  the existing larger Catalog worker remains available through its existing API.

## Verification record

The shared implementation is in `libs/platform` version 0.38.0. Both owner APIs
install the same routes, engine, file adapters and table models. Domain adapters
invoke the existing native command services, permissions and audit transactions.
All seven consuming service lockfiles are synchronized.

### Delivered API

Each owner exposes the following below `/v1/companies/{company_id}` through its
existing service routing. Definitions are `parties` in Accounting and `products`
and `prices` in Catalog. Templates can narrow the resource and applicable
customer/supplier role or goods/service kind.

| Endpoint | Purpose |
|---|---|
| `GET /import-definitions` | Available definitions, formats and capacity |
| `POST /import-templates` | Snapshot authorized fields, configuration and options |
| `GET /import-templates/{id}` | Retrieve snapshot JSON or CSV/TSV/XLSX template |
| `POST /import-jobs` | Stage immutable source files and normalized revision |
| `GET /import-jobs` | Actor-owned, company-scoped history with signed cursors |
| `GET /import-jobs/{id}` | State, revision, counts and review digest |
| `POST /import-jobs/{id}/validate` | Native dry run with business writes rolled back |
| `POST /import-jobs/{id}/commit` | Execute the reviewed version and digest |
| `POST /import-jobs/{id}/revisions` | Stage corrected files while preserving successful groups |
| `POST /import-jobs/{id}/retry` | Revalidate remaining groups before a new reviewed commit |
| `POST /import-jobs/{id}/cancel` | Cancel further execution |
| `GET /import-jobs/{id}/records` | Paginated row status/results |
| `GET /import-jobs/{id}/history/{kind}` | Attempts, revisions or artifacts |
| `GET /import-jobs/{id}/attempts/{attempt_id}/issues` | Paginated messages and field issues |
| `POST /import-jobs/{id}/download-ticket` | Issue actor/company/version-bound 5-minute ticket |
| `POST /import-jobs/{id}/download` | Exact source, normalized input, result or correction file |

Mutations require `Idempotency-Key`; job mutations also require `expected_version`.
Commit requires the latest successful validation's `review_digest`. Staging uses
JSON containing one or more named base64 files, bounded to 8 MiB combined decoded
content and a 13 MiB HTTP body. CREATE_ONLY, UPDATE_ONLY and UPSERT use native
matching rules. Atomicity is either the whole job or each related change set;
error policy is STOP or CONTINUE_INDEPENDENT.

XLSX templates contain Records, Import_Instructions, Import_Fields and
Import_Options sheets. The parser only imports the record sheets; metadata sheets
remain subject to workbook security checks. CSV/TSV templates use the same version
marker and controls; their companion JSON snapshot supplies field instructions
and active options. Option lists are bounded and expose truncation/lookup metadata.
Nested native structures use exact JSON; spreadsheet formulas are never evaluated.

Result files include source locations, logical row keys, status, failure codes and
messages. Both validation and commit attempts can be downloaded. Correction files
retain successful prerequisite rows so they can be uploaded as a new revision
without executing those successful groups again.

### Database and cleanup

Accounting migrations 0157–0167 and Catalog migrations 0181–0191 install eleven
tables per owner database: template snapshots, jobs, revisions, change sets,
records, dependencies, attempts, effects, results, issues and artifacts. Each
revision has one CREATE DDL and a matching DROP downgrade. Foreign keys and unique
keys include tenant/company scope; history uses indexed keyset queries. Private
source BLOBs are deferred and loaded only for authorized downloads.

The final cleanup phase provides owner-scoped maintenance commands, run from the
respective service directory with its normal DATABASE_URL environment variable:

```powershell
uv run python -m accounting.tasks.import_cleanup --tenant <uuid> --company <uuid> --limit 50
uv run python -m catalog.tasks.import_cleanup --tenant <uuid> --company <uuid> --limit 50
```

The maintenance scheduler should invoke the matching service command for each
tenant/company and repeat bounded sweeps while counters remain nonzero. There is
no public cleanup endpoint. Each sweep locks eligible jobs, uses strict scoped
ORM writes, invalidates expired reviews and emits system-category cleanup audit
events. Repeated sweeps are safe. At 30 days payloads become SQL NULL; at 365 days
detailed history is deleted in foreign-key order. Business masters, successful
effect keys, native command receipts and audit/outbox evidence are retained.

### Review and fixes

1. Authorization and lifecycle review: fixed saved-template access and idempotent
   template replay after permission revocation. Current authority is rechecked
   against the saved schema/options. Regression tests cover both paths, company
   boundaries, original-source download revocation, validation rollback, retry
   deduplication and stale configuration rejection.
2. Configuration, transport and persistence review: fixed serialization of
   effective custom-field definitions, excluded denied custom-field metadata,
   retained the old Catalog typed-cell export contract and clarified migration
   nullability for schema checks. Regression tests exercise configured templates,
   exact fixed-price draft/publication and multi-file customer/supplier creation.

Final cleanup verification additionally caught guarded-session bulk DML rejection;
cleanup now loads scoped rows and flushes deletions in FK order. A failing
regression was reproduced before the fix. Cleanup audit contract categories and
binary download OpenAPI content types were also corrected with regression checks.
Shared typed-cell parsing replaces the duplicate Catalog implementation.

The repository-requested `/simplify` and `/security-review` commands were not
available in this session. Both review passes were performed manually against
CLAUDE.md security/correctness invariants; no slash-command execution is claimed.

### Validation evidence

Final verification on 2026-10-23:

| Check | Result |
|---|---|
| Full shared library suite | 1,120 passed; 92.27% coverage (90% floor) |
| Shared HTTP and strict-session cleanup regression rerun | 5 passed |
| Accounting imports and existing workflows | 12 passed |
| Accounting import tests on native MySQL | 8 passed; native setup/concurrent idempotency and full downgrade/upgrade passed |
| Catalog imports, old CSV/XLSX transports, audit contracts and migrations | 29 passed, 1 Docker-only migration check skipped |
| Catalog native MySQL verifier | 7 workflows, model parity, retention cleanup and head→0131→head roundtrip passed |
| Accounting audit regression suite | 6 passed, 1 large-decimal SQLite case skipped (requires native MySQL) |
| Generated TypeScript client | Typecheck passed; 8 tests passed |
| Shared import modules and service adapters | Ruff and strict mypy passed |

The skipped Docker migration test is covered by the independent native MySQL
roundtrip above. The optional large-decimal audit case remains skipped in the
SQLite audit run; native import pricing tests separately verified decimal price
draft/publication. A focused two-module coverage run initially reported 87.26%
despite all 34 tests passing; the final complete shared suite passes its required
coverage floor. Earlier review regressions and native cleanup failures were fixed
and rerun successfully.

OpenAPI, Accounting/Catalog TypeScript declarations and audit event matrices are
regenerated. Test databases were disposable and the temporary MySQL server was
stopped after verification. These checks do not deploy migrations to an existing
application database.

The product Console integration is delivered separately; see
[product-import-ui-delivery.md](product-import-ui-delivery.md) for scope, UI/native
verification and review findings. Party/supplier Console integration is also delivered;
see [party-import-ui-delivery.md](party-import-ui-delivery.md). Both use the same Console
workflow, transport/file mechanics and owner-native validation/commands.

Ready customer and supplier rows also accept optional opening-balance columns, held for the
company opening and never posted; see [party-opening-balance-import.md](party-opening-balance-import.md).
