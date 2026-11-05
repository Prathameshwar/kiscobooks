# Voucher custom-attribute review

**Date:** 2026-10-11. **Scope:** Backend voucher header and item-line custom fields; UI later.

The existing Identity definition API supports both `vouchers.voucher` and
`vouchers.voucher_item`. Identity's authenticated source contract projects typed definitions
to Vouchers. Vouchers validates all 12 supported types, stores values on immutable document
revisions, pins accepted definitions and presentation, and maintains searchable indexes,
unique claims and auxiliary sequences in the document transaction. Type policy limits which
definitions apply. Custom values remain descriptive; money, tax, stock, and job-work effects
use native typed fields.

## Completed phases

1. **Trace and reproduce.** A condition referencing another custom field failed even when
   both fields were readable, because write validation passed only native field names to
   the shared condition validator. Regression tests cover header and item-line values.
2. **Repair and expose metadata.** The validator now includes accepted, readable custom
   fields as condition inputs and still rejects a denied parent. A company-scoped
   `GET /v1/companies/{company_id}/vouchers/{id}/field-set` returns definition and
   presentation snapshots for the current or selected `revision_id`, grouped into header
   and line-keyed item fields. Live read policies filter both; a revision belonging to a
   different voucher is rejected. Existing type field-set remains for new entries. Both
   surfaces hide a dependent field when its condition references a read-denied parent;
   the type field-set also filters layouts and bound/required key lists accordingly.
   A deny on the voucher `lines` section hides item-field metadata altogether.
3. **Verify contracts.** Regenerated Vouchers OpenAPI and the typed client, exercised
   condition/deny and metadata tests, and ran affected service checks.

The API stores typed custom values in JSON and typed search indexes. It does not add
physical SQL columns per tenant or voucher type. Historical values and labels are pinned
by revision; current read denies still apply when metadata or values are returned.
Registered dynamic-select options come from the local active voucher-type, item and party
snapshots. This review does not add parent-specific filtering of those option sets; a
source-specific cascading contract is still needed before claiming that behavior.
