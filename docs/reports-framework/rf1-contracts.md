# RF1 typed registry and compatibility

The new domain contracts in `reports.domain.reporting` import only the standard library.
They define datasets with grains/join cardinality, versioned metrics, named typed views,
query budgets, result manifests and documents referencing result streams. Logical result
fingerprints are separate from exact row counts and file hashes. Decimal helpers reject
implicit rounding and storage overflow; undefined ratios return `None`.

The registry validates duplicate identities, missing handlers, unknown metrics/datasets,
metric cycles, unsafe fan-out joins, column currencies and ordering. Adding a registered
handler does not require editing the engine's dispatch logic. The initial 27 adapters call
the existing financial functions unchanged; they are the parity reference for RF4, not the
million-line execution path. Actual packaged source and parameter schemas are hashed.

## V1 / V2 matrix

| Contract | V1 | V2 |
|---|---|---|
| Existing runs, rows and CSV downloads | Preserved | New job lifecycle in RF2 |
| Source selection | Generation pinned | Same requirement |
| Parameters | Existing flat request | Per-definition schema; extra fields forbidden |
| Financial statements | Complete-company base amounts | Account/group/party filters absent from schema |
| Outstanding/advances/aging | Legacy date range | Explicit as-of date; retained coverage supplies the adapter's lower boundary |
| Invoice currency | Existing calculation semantics | Optional native document-currency selection; GL/base measures remain distinct |
| Bank session evidence | Account/session/currency/range | Same required inputs; no unrelated selectors |
| Discovery | Existing definitions | `/v2/companies/{company_id}/report-definitions` plus detail and parameter validation |
| Formats/admission | Legacy CSV | Capability flags stay disabled until execution/renderers are wired and verified |

Discovery and validation enforce current company and complete-source permissions. A field
read deny blocks the report; bank evidence requires its additional source permissions. Unknown
definitions return 404, invalid parameters 422. An actor context signed for a different request
company remains the existing 401 authentication failure; a valid company context with grants
for another company receives 403.

RF1 validation: 181 Reports tests passed, one broker test skipped in the general invocation;
domain coverage 92.21%, new domain contracts/registry 100%. The same 181 tests passed on
MySQL 9.6, with migration upgrade/downgrade and schema parity. Ruff and strict mypy passed.
OpenAPI and Reports TypeScript definitions regenerated; shared client typecheck and all eight
client tests passed. Existing v1 consumers continue to use their unchanged contract until RF7.
