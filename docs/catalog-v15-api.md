# Catalog V1.5 bulk administration

Company prefix: `/v1/companies/{company_id}/bulk-jobs`. Shared mechanism version 0.21.0;
Catalog schema head 0116, 114 tables.

## API workflow

All writes require `Idempotency-Key`, return 202 and expose `Idempotency-Replayed`.
Job and record lists use signed cursors (50 default, 200 maximum), `state`, and `id`/`-id`
sorting. Uploads, previews and results are private to the original actor and company.

| Method/path after prefix | Purpose |
|---|---|
| GET `/templates?resource=unit_of_measure&action=CREATE&format=JSON` | Current authorized native schema; CSV/XLSX formats also available |
| POST empty path | Stage JSON, base64 CSV/XLSX, or a typed FILTER selection |
| GET empty path; GET `/{job_id}` | Lean jobs and current job metadata |
| GET `/{job_id}/records`; GET `/{job_id}/records/{record_id}` | Lean row results and protected before/after review |
| POST `/{job_id}/validate` | Freeze selected unfinished change-set keys, or all unfinished sets |
| POST `/{job_id}/commit` | Accept the exact reviewed digest and job version |
| POST `/{job_id}/cancel` | Stop future chunks; committed effects remain committed |
| POST `/{job_id}/revise` | Replace unfinished input while preserving sealed completed sets |
| GET `/{job_id}/report-ticket?format=CSV` | Actor/company/job/version-bound five-minute download path |
| GET `/{job_id}/report?format=CSV&token=...` | Reauthorize and download sanitized CSV/XLSX row results |

A minimal staged import:

```json
{
  "format": "JSON",
  "schema_version": 1,
  "mode": "CREATE_ONLY",
  "atomicity": "CHANGE_SET",
  "on_error": "STOP",
  "records": [{
    "key": "each", "change_set": "each", "resource": "unit_of_measure",
    "action": "CREATE",
    "data": {"code": "EA", "name": "Each", "symbol": "ea", "dimension": "COUNT",
             "decimal_places": 0, "quantity_increment": "1"}
  }]
}
```

Validate with `{"expected_version": 1}` using the actual returned version. Poll until READY,
inspect the records, then commit with the latest `expected_version` and `selection_digest`.
The worker executes native commands during preview inside a rolled-back transaction; no
preview domain changes, command receipts or audit events survive. Commit uses the same
native commands with fresh original-actor authorization and pinned dependencies.

## Inputs and supported commands

Modes are CREATE_ONLY, UPDATE_ONLY and UPSERT. AUTO resolves only exact company-scoped
UUID/code or an existing active external-system/key assignment. It never creates fuzzy masters.
Targets may use `{"record":"earlier-key","field":"id"}`; command data can use
`{"$ref":"earlier-key","field":"item_id"}`. Dependencies are topologically ordered and
must be included in the selected work or already committed by the same job.

An omitted update field remains unchanged. `clear_fields` explicitly supplies null and is
still checked by the native schema and field policies. Zero and false remain actual values.
Money and decimal quantities must be JSON strings; identifiers and decimals in XLSX must
be text cells. CSV uses the downloaded version marker and header. Native XLSX booleans are
supported. Formula cells, external workbook links, macros, encrypted/binary workbooks,
duplicate JSON properties and inexact floating JSON numbers are rejected.

The explicit adapter registry supports unit/pack, classification and commercial masters;
unit conversions and tax codes; product-type revisions; family/SKU changes and variants;
product groups/categories/manufacturers/attributes/units/barcodes; configuration publication
and adoption; product activation; company/SKU pricing definitions and tax definitions.
Download the resource/action template for its exact native input and required permissions.
Unknown resource/action pairs fail with 422.

Item-price ADJUST supports exact PERCENT, DELTA and SET on fixed or tiered prices, preserves
tier boundaries, and publishes dated history through native draft/publication. It requires
explicit currency, unit revision, quantity basis, price level, numeric revision, rounding,
effective dates. Recipes and gross purchase terms use explicit native
draft revisions. Purchase inputs and selection require purchase-price authority.

FILTER supports family status/kind/brand/type revision; SKU status/kind/family/base unit;
unit dimension/active state; and item-price series. Empty filters require `all_rows=true`.
Selection materializes IDs and versions once. Price levels for the same SKU share a change set.

## Engineering bounds and recovery

Decision 2026-10-30: product tax assignments, price drafts, published prices and
bulk price adjustments no longer collect or expose a free-text `source_reference`.
The retired input is rejected by the native schemas; publication still requires
current authority, reviewed versions, exact amounts and dated history.

- At most 2,000 rows and 8 MiB decoded upload; 100 native commands per change set.
  ADJUST counts as two commands. ATOMIC is bounded to 100 sets/1,000 native commands.
- Dependency preview is bounded to 1,000 rows. Review evidence is bounded to 256 KiB per
  record and 8 MiB per change set; XLSX expansion is bounded to 48 MiB and 128 package parts.
- Worker chunks have a default maximum of 25 seconds, shortened to fit the current proof
  expiry. A chunk timeout rolls back and durably blocks pending work with `chunk_timeout`.
  Split oversized sets and validate again; timeout is not a successful partial aggregate.
- Uploaded/private review data expires after seven days. Cleanup removes raw bytes, inputs,
  previews, dependency values and effect results while retaining effect identity and metadata.
- STOP halts after a failed set. CONTINUE_INDEPENDENT advances independent sets and marks
  dependent work BLOCKED. SUCCEEDED means every input record committed; subset completion
  remains PARTIAL. ATOMIC failures roll back all selected changes.
- A worker restart retries the durable checkpoint. Domain changes, stable effect identity,
  native idempotency receipts and audit/outbox commit together. Revisions cannot remove or
  alter completed sets; corrections to completed work require a new reviewed job.
- Identity lease renewal may advance the stream version only when a digest of all verified
  owner facts is unchanged. Changed facts or external Catalog generation/dependency drift
  require a new review. Every chunk still obtains fresh permission proofs.

Run `python -m catalog.tasks.bulk_worker` as a separate supervised process. Configure
`CATALOG_DATABASE_URL`, `CATALOG_ACTOR_SIGNING_SECRET`, the existing `CATALOG_IDENTITY_SOURCE`
object, and `CATALOG_SOURCE_SUBSCRIPTIONS` containing tenant/company pairs. Optional
`CATALOG_BULK_POLL_SECONDS` is 1?60 (default 2); `CATALOG_BULK_CHUNK_SECONDS` is 1?25
(default 25). The worker does not migrate or create production schemas at startup.
Monitor FAILED/PARTIAL jobs, blocked rows, source readiness, outbox backlog and cleanup.
Transient source/network/database failures retain the checkpoint for retry.

## Authority and release boundary

`catalog.bulk.read`, `.manage` and `.commit` supplement underlying native permissions; they
never grant master, product, purchase-price or tax authority. Company administrators receive
all three; the tenant auditor receives read only. Original-actor ownership still applies.
Current field read policies protect metadata, targets, previews, dependency values and exports;
current write policies remain enforced by ordinary handlers. Private columns are absent from
field metadata and API response models. Errors expose safe codes/field names, not submitted
values, internal exceptions or SQL. Downloads use no-store and nosniff.

These operations cannot create parties, stock, actual costs, postings or physical declarations.
Price adjustments execute the native commercial and dated-coverage checks during validation
and commit. A known blocking floor/ceiling or dependency gap becomes a `review_conflict`;
validation rolls back its trial changes and does not close or replace the existing price.
Commit rechecks those conditions and existing review/version guards before publication.
Customer/stock-dependent pricing still needs real Billing source contracts. Promotions,
warehouse extensions and optional BOM are outside the agreed V1 release. Real GST datasets
must retain reviewed notification evidence; synthetic test fixtures are not production rates.

## Decision log

- 2026-09-14: Native price readiness checks now protect bulk adjustments as well as individual
  publication; blocked adjustments preserve existing price history.
- 2026-09-13: Implemented the user-confirmed V1 scope using shared bounded parsing and
  transaction participation, six private job tables and ordinary Catalog commands.
- 2026-09-13: Separated semantic Identity fact changes from authenticated unchanged lease
  renewal so long jobs can progress without weakening fresh actor authorization.
- 2026-09-13: Added explicit review byte bounds and durable chunk timeout handling after
  security/recovery review; fixed SKU-kind selection and product-type parent resolution.


Category review correction (14 September 2026): code matching must identify exactly one row.
Because category codes are scheme-local, duplicate codes across schemes require an ID or
external key. Active-family `ASSIGN_CATEGORIES` uses the native dated category preview token
and all native current-authority, history and cardinality checks; it is not a draft-only bypass.
