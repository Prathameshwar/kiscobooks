# Catalog audit contract

Accepted as part of the seven-phase integration, 2026-09-17. The executable event registry
and generated `apis/catalog/contracts/audit-events.json` define exact routes, categories and
per-entity safe fields. This extends the existing delivery contract without changing legacy
signed bodies, schema version 1 or stored rows.

| Workflow | Cardinality and category |
|---|---|
| Units, classification, reusable profiles and mappings | Admin event per changed command row; hierarchy edges have their own events. Requirements, membership and conditions may be represented by the owning profile/revision marker. |
| Products, variants, unit bindings and configuration adoption | Admin event per explicitly changed aggregate member through existing command record helpers. |
| Configuration draft/publication | One admin parent receipt covers its changed draft/scope/children; child fields must be namespaced or represented by an aggregate marker, never attributed to a different entity's field key. |
| Pricing and commercial controls | Money event per explicit changed row, including drafts, publication and closure; this is configuration evidence, not a posted financial transaction. |
| Tax rules, rates, applicability and releases | Money event per explicit changed row. |
| Item activation and inventory profile | Admin events from the explicit activation commands; derived records retain existing owner coverage. |
| Bulk jobs | Admin event per job transition plus each executed native command event. Internal row outcomes are covered by the job. Preview rolls back tentative native effects and audit rows. |
| Index rebuilds | Admin for attributable user work; system for service cleanup/failure. Status/progress markers remain valid when a prior value is unknown. |
| Implemented warehouse commands | Admin events through the same classification/pricing record mechanisms; pending model-only workflows are not invented by this integration. |
| Bulk CSV/XLSX report download | One access event per authorized, successfully prepared response, including repeated downloads. Safe job ID, format and bounded row count only. Ticket issuance and routine reads emit no access event. |

Every event uses authoritative tenant/company and original/effective actor references. Request
correlation is validated and optional; a background job retains its persisted attribution and
must not fabricate an originating request ID. Command replay creates no additional mutation
events. Separate successful downloads are separate accesses. Existing local revisions remain.

Safe before/after evidence intersects an exact scalar vocabulary with the native entity's
registered fields. Decimal values are exact strings with applicable currency/unit context.
Names, free text, addresses, identifiers, arbitrary JSON and custom values remain markers.
Unknown prior values remain markers; creates may use null as the prior value. Snapshot values
must be captured before mutation/flush or passed from the command's existing before map.

Current Catalog field denies cover field names as well as values in Audit detail/export.
Missing policy context withholds field evidence; conditional historical denies are conservative.
Metadata/reasons cannot bypass field projection. Stored signed evidence and hashes are unchanged.
Catalog report metadata is limited to a bounded count and CSV/XLSX format. Composite parent
markers are withheld if the reader has denied child fields that the parent marker could reveal.

Authenticated payloads must satisfy Audit's existing column lengths and finite-JSON validation.
Oversized/non-finite payloads dead-letter before database work; genuine database outages retry.
Replay preserves original bytes, identity and timestamps. Consumer routes and Catalog policy
projection must be deployed before richer/new producers.

## Decision log

- 2026-09-17: reuse confirmed asynchronous delivery and existing Audit HTTP reads; no mutation
  makes a synchronous Audit call. Preserve marker compatibility and full event names.
- 2026-09-17: extend field protection before richer Catalog values. Explicit pricing/tax
  configuration evidence is money-category; ordinary master/activation/job work is admin.
- 2026-09-17: report access describes a prepared authorized response, not proof of file receipt;
  do not store report contents or download tokens in the audit trail.
