# Reports framework: API/database usage

The existing Reports service owns the framework. It does not own or mutate Accounting's
books and does not require S3, Azure Blob or another cloud storage provider.

## API flow

Use the company-scoped v2 prefix `/reports/v2/companies/{company_id}` through the gateway
(omit `/reports` when calling the Reports service directly). Existing authentication,
company-step-up and server-side field/read permissions apply. Commands require an
`Idempotency-Key`; reuse that key when retrying the same request after a network error.

1. `GET /report-definitions` discovers permitted definitions, parameter schemas, views,
   enabled formats and export limits. `GET /report-definitions/{code}/field-set` supplies
   the same input/view metadata for clients. `POST /report-definitions/{code}/validate`
   validates typed parameters without creating a run.
2. `POST /report-generations` with `{"strategy":"FRESH"}` requests a verified source.
   `REFRESH` and `COMPACT` require `base_generation_id`; current owner/source compatibility
   is checked. Poll `GET /report-generations/{id}` until `READY`.
3. `POST /report-runs` with a discovered code, version, generation, parameters and `view`:

   ```json
   {
     "code": "ACCOUNT_LEDGER",
     "version": 4,
     "generation_id": "<ready generation UUID>",
     "parameters": {"date_from": "2026-04-01", "date_to": "2026-04-30"},
     "view": "default"
   }
   ```

4. Poll `GET /report-runs/{id}`. On `COMPLETE`, fetch `/rows?limit=50` and follow the signed
   `page.next_cursor`. History endpoints `/report-runs` and `/report-exports` also use
   bounded keyset pages. A run retains its definition, source, parameters and display facts.
5. `POST /report-runs/{id}/exports` with `{"format":"PDF","view":"default"}` creates an
   independent export job. Formats are `PDF`, `HTML`, `CSV`, `XLSX`; use advertised budgets.
   Export failures cannot invalidate the completed source run or other exports.
6. Poll `GET /report-exports/{id}`. Once complete, obtain `/download-token`, then request
   `/download?token=...`. Both calls require current authority; the grant expires in 120 s.
   Downloads stream from a private persistent folder with attachment/no-store headers.

Runs and exports support `POST /{resource}/{id}/cancel` and `/retry` for permitted states.
Retry is limited to failed jobs and a maximum of three attempts; cancelled/completed evidence
is not rewritten. Follow each row link's advertised `method`: GET `href` for frozen row detail, or POST
`{"token":"<signed token>"}` to its `href` for a next-level report. The child retains the
parent's source and display configuration. Journal links select the actual posting date;
summary links select their day/month range.

The current catalogue contains 27 implemented definitions with `default` and `compact` views.
Outstanding bills and advances also offer `party_balances`, separating debt, unapplied credit
and net debt by party/account/role/currency. That view performs a grouped calculation; request
a new run rather than exporting a detail run with incompatible columns. New business reports
require a typed, versioned definition/handler; the API never
accepts user SQL, arbitrary column names, user templates or executable calculations.

## Result search, filters and sorting

Discovery's `navigation` lists the search fields, typed filters and sortable fields for each
report. After a parent completes, submit an independently exportable selection:

```http
POST /report-runs/{parent_id}/queries
Idempotency-Key: <UUID>
Content-Type: application/json

{"q":"INV", "filters":{"row_kind":"ENTRY","date_from":"2026-04-01","debit_min":"0.0001"}, "sort":"-date,number"}
```

Poll the returned child and read its usual signed `/rows` pages. Search matches field prefixes
case-insensitively; filters are ANDed. Use exact UUID/text/boolean filters (`"true"`/`"false"`),
`_from`/`_to` for dates and `_min`/`_max` for numeric ranges. `-field` sorts descending;
at most three fields, with original ordinal breaking ties and nulls last. Unsupported fields
and invalid/reversed values fail with 422. Original balances stay unchanged; selected results
retain their parent evidence and exports carry "Selected rows". Capacity failures block output
instead of returning partial results. New selection requests require an installed definition
matching the completed parent; retained old reports remain readable/exportable.

See [the complete 27-report review](report-by-report-review.md) for concepts, changes,
resource limits and verification. API clients must refresh discovery after deployment rather
than cache older definition versions or drilldown mappings.

## Reusing exports in console report screens

Use `app/lib/report-exports.ts` rather than adding another format registry, status timer
or download URL builder. It is used by Day Book, FrameworkReports and balance continuity.

- `reportExportOptions` derives availability from discovery and the **complete** retained
  row count, registered view columns, calculation compatibility and document-part limits.
  `primaryExportFormats` keeps PDF, XLSX and CSV visible with reasons when unavailable.
- Submit the existing company-scoped `/report-runs/{id}/exports` command with the current
  view and an idempotency key. Keep that key after an uncertain submission; export does
  not call the report calculation again or collect browser pages.
- `trackReportExport(company, initialJob, signal, onUpdate)` polls sequentially and stops
  at every terminal state. Abort when the screen/company/job changes. Aborting tracking
  does not cancel the durable server job; use its existing cancel command for that.
  Terminal failure jobs are returned for review; transport errors reject for recovery.
  After a status-read failure, track the known job again instead of creating another export.
- `reportDownloadHref` points to the private streaming console route. That route obtains
  a fresh actor/company-bound grant, then streams without buffering the complete file.
  `canPreviewReportExport` permits inline preview only for a completed single PDF;
  packaged PDF/HTML results remain ZIP downloads.

PDF uses the frozen company display settings. Excel retains exact stored data, frozen
headers, filters and an About sheet; CSV uses UTF-8 BOM, ISO dates and exact decimals.
All formats inherit the source run's applied filters and all matching rows. Definition
budgets and current server permissions remain authoritative. See
[export delivery and verification](../report-export-delivery.md).

## Windows process configuration

Provision the service database using migrations through Reports `0036`; the Accounting source
snapshot additions are `0151`/`0152`. Preserve the separate service database boundaries.
Configure private environment files rather than placing secrets in command lines or source:

- Reports database/signing settings and `REPORTS_OWNERS` for signed Accounting source access.
- `REPORTS_AUTHORITY_SOURCES` for scoped, short-lived Identity permission proofs.
- `REPORTS_JOB_BROKER_URL` for the existing RabbitMQ service.
- An absolute private persistent `REPORTS_ARTIFACT_ROOT`, outside web-served folders, with
  access restricted to the service/operator account. Multiple hosts need the same durable
  shared folder. Keep database metadata and files in coordinated backups.
- Explicit admission switches: `REPORTS_FRAMEWORK_ENABLED`, `REPORTS_SOURCE_VERSIONS_ENABLED`,
  `REPORTS_NATIVE_QUERIES_ENABLED`, and `REPORTS_EXPORTS_ENABLED`. They default to false.
  Accounting's source snapshot switch and scoped credentials must also be configured.

From `apis/reports`, run the existing API/audit processes and these separately supervised
processes using the same private configuration. On Windows, each lane uses a single-process
Celery worker; start additional independently supervised workers only when required:

```powershell
.venv/Scripts/python.exe -m reports.tasks.source_worker --env-file <private-file>
.venv/Scripts/python.exe -m reports.tasks.job_dispatcher --env-file <private-file>
.venv/Scripts/python.exe -m reports.tasks.job_dispatcher --env-file <private-file> --worker short --pool solo --concurrency 1
.venv/Scripts/python.exe -m reports.tasks.job_dispatcher --env-file <private-file> --worker bulk --pool solo --concurrency 1
.venv/Scripts/python.exe -m reports.tasks.job_dispatcher --env-file <private-file> --worker render --pool solo --concurrency 1
```

Accounting's `accounting.tasks.reporting_snapshot` worker runs with its own environment.
The API readiness probe checks schema availability/version. Discovery checks local renderer
and artifact prerequisites before advertising exports. A ready API does not prove broker,
worker or source-owner availability; check those process logs and queue delivery separately.

## Retention, failures and rollback

Completed runs, source evidence and exports are retained indefinitely. The scoped
`reports.tasks.artifact_cleanup --tenant <UUID> --company <UUID>` command (with Reports
environment loaded) cleans abandoned temporary folders only. It does not delete published
objects or retained database evidence. Failed publication can leave a retained orphan object;
there is no automatic completed-object deletion policy.

After a worker restart or broker interruption, the dispatcher repairs pending/expired work.
Attempt fencing prevents late workers from publishing. Dependency failures have bounded
retries; permission or verification failures block output. Source gaps or failed reconciliation
require repairing the owner/source and requesting an appropriate new generation.

Calculation workers renew their leases and recheck authority while loading/calculating, before
the first output batch as well as during publication. Reference CPU calculations run in a
worker thread so the lease loop remains responsive. Cancellation/revocation prevents publication;
an in-flight calculation is joined before worker cleanup, within its process deadline.

Each Celery delivery runs in an expendable child process. The parent enforces the lane
deadline (SHORT 60 seconds, BULK the greater of calculation/export timeout plus 60 seconds,
RENDER 90 seconds), including
on Windows's `solo` pool. An independent child watchdog bounds stalled thread shutdown if
the parent is lost. Child processes use a 512 MiB memory limit; private configuration is
passed over stdin and child diagnostics are suppressed. A killed attempt stops renewing
its lease, allowing the dispatcher to recover it after expiry. Existing attempt fencing
prevents partial or late output from becoming visible.

Retained query identities include shared financial helpers and relevant runtime versions.
Preserve the original runtime/build for existing pinned-query runs across upgrades. If it is
unavailable, retrieval fails closed; request a new run without rewriting the old evidence.
Completed materialized rows and export files remain readable through their retained contracts.

To stop new work, disable admissions while retaining readers/workers needed for existing
results. Do not drop forward-created tables, reset source checkpoints, delete retained files
or route oversized jobs into the legacy reference engine as an automatic fallback.

## Operating bounds

Source/reference/materialized-result caps remain explicit configuration bounds. Calculations
reject unsupported values rather than silently truncate or round. Current financial calculation
validation retains the existing DECIMAL(19,4) amount boundary; the presentation adapters also
support exact wider aggregate strings up to DECIMAL(38,4). CSV retains canonical values; Excel
uses exact text above its safe numeric precision. PDF/HTML apply the run's frozen display rules.

Account summaries include every requested day/month for selected accounts and their groups,
including zero turnover with unchanged carry. The account/group period count is checked
before row allocation (100,000 rows by default; native execution uses its configured result
limit, including comparative rows). Outstanding-bill and advance exports include party,
role and debt/credit direction; their report amount is an unsigned magnitude.

Framework definitions with the new views use version 4 for ACCOUNT_SUMMARY, OUTSTANDING_BILLS
and ADVANCES, and version 3 for other codes. The v1 summary rule uses definition version 2.
Completed materialized results and
exports retain their original definitions and bytes. Request a new run for corrected output;
old pending jobs whose retained implementation is unavailable fail closed.
Omitting the framework definition version selects the latest registered version; an explicit
version must still be available. Clients that pin a version should refresh discovery on upgrade.

PDF is limited to 5,000 rows, 200,000 cells, 64 MiB, 200 pages and 60 seconds, with an isolated
Windows process memory cap. HTML is limited to 20,000 rows and 200,000 cells. CSV/XLSX use
configured row/byte/time budgets; XLSX splits at the native worksheet row limit.
Windows rendering has been exercised; Linux activation requires its own validation.
No load or soak testing is part of the final delivery scope.

## Bulk calculation and presentation packages

Discovery/field-set responses include `execution_limits` and `package_limits`. For native
ACCOUNT_SUMMARY, submit `"execution":"BULK"` to calculate one day/month at a time and publish
immutable batches of at most 200 rows. The default total limit is 1,000,000 rows, controlled by
`REPORTS_BULK_RESULT_LIMIT` (maximum 10,000,000), and the calculation deadline is controlled by
`REPORTS_BULK_TIMEOUT_SECONDS` (default 600, maximum 7200). Each period is independently bounded
to 100,000 result/aggregate rows. Other calculated report families retain their existing limits.
Recovery checks retained identity, period count, batch hashes and continuity before reusing
completed periods in a new fenced attempt. Output is visible only when the whole run completes.
Bulk rows are ordered by current/comparative period, then date and the period's canonical rows;
standard summaries retain their original account/group ordering.

For a completed run, submit an export such as:

```json
{"format":"PDF","view":"compact","delivery":"PACKAGE","part_rows":1000}
```

PACKAGE supports PDF/HTML and returns one private ZIP download containing document parts and
`manifest.json`. Every manifest entry records filename, first ordinal, row count, byte count
and SHA-256; source/definition/view identities accompany the complete row count. PDF defaults
to 1,000 rows per part, HTML to 10,000; optional `part_rows` can lower the size for wide/long
content and remains bounded by the renderer's row/cell limits. Per-part page/memory/time limits
still apply. Total rows/bytes/time use existing export configuration; `REPORTS_PACKAGE_MAX_PARTS`
defaults to 100 (maximum 1000). Large packages can therefore still exceed total or per-part
capacity and are rejected without publishing partial output. Choose CSV/XLSX or a shorter
selection when appropriate. HTTP capacity failures use `report_capacity_exceeded`; bulk worker
capacity failures use `REPORT_CAPACITY_EXCEEDED`. Exact pinned-query counts can be unknown at
admission, so the worker also enforces every bound while consuming rows.

The console restores the retained view/execution choice and offers document-parts delivery.
See [the extension decisions and verification](presentation-capacity.md). Completed old outputs
remain retained; old pending jobs require their original runtime/definitions. Admission defaults
remain disabled. Configure/apply additive migrations before deploying the new service.
# Inventory report extension

The catalogue now also contains ten stock reports. See the
[inventory implementation and API guide](inventory-implementation.md) for source requirements,
per-report inputs, migrations, two review passes and explicit performance bounds. Genuine
Accounting stock evidence is required; the existing unfinished stock-posting work is not
implicitly enabled by these definitions.
