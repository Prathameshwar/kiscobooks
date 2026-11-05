# Simple product serial input and opening

Requested 2026-11-04: review, plan and implement configured serial input in Simple
creation, preserving immediate activation and posting through one Save.

## Phases

1. Reuse native identifier requirements (Serial/IMEI, counts and slots), with one
   shared input validator for Catalog admission and Accounting registration.
   Expose protected requirements/field access in Simple creation options.
2. Capture one row per physical opening unit, either at product level or inside
   its batch. Derive the quantity from rows and reject mismatches, duplicates,
   invalid IMEI, disabled input and non-integer base units before creation.
3. Extend the resumable coordinator to register each physical unit with stable
   retry keys, then pass those identities into the existing opening/voucher flow.
   Keep native posting, tenant, audit, closed-period and reconciliation controls.
4. Add responsive UI, tests for serial-only and batch+serial flows, review money
   and permissions, regenerate contracts/clients and record results.

## Decisions

- Serial capture is enabled by the existing Goods inventory/identifier profile
  and company serial capability. Required tracking cannot be bypassed in the form.
  No new per-product serial switch or storage mode is needed.
- One row represents one unit; the profile determines Serial/IMEI columns and
  required identifier counts. Optional identifier slots can be left empty;
  any allowed slot can satisfy a minimum count smaller than the maximum.
- Serial-only products retain ordinary product prices. Batch+serial products
  retain batch prices and expiry. Serials do not introduce another selling-price
  dimension. Opening value remains purchase price times unit count.
- Combined batch+serial profiles require their batches; serials belong to their
  selected batch. Up to 200 opening units can be captured in one creation.
- Zero rows means no opening stock. Services have no serial input. Import and
  separate serial-management/voucher-entry screens are outside this change.
- No schema migration is needed: native StockUnit/identifiers and the retained
  creation request already provide the necessary storage.

## Delivered contract

`GET /simple-product-creations/options` includes `serial.enabled`, the protected
native `requirements`, and `serial_identifiers` field metadata. The stock step
appears for configured serial-only products as well as batch products.

Creation accepts `serials` on the product or on each `batches` row. Each entry has
`identifiers`, containing `identifier_type` (`SERIAL` or `IMEI`), `slot` and `value`.
The request's `opening_quantity` must equal its serial row count. Product-level
serials cannot be mixed with batch-level stock. The UI calculates this quantity
and keeps entered rows when moving between steps.

Admission reuses the native normalization, printable-length, slot/count and IMEI
checksum rules. Duplicate identifiers are rejected across all entered units and
batches. Accounting's read-only `POST /stock-tracking/serials/check-identifiers`
checks existing company-namespace identities before product creation; it requires
native serial read/manage authority and readable identifiers. Native registration
still owns uniqueness, including concurrent requests and item-scoped identities.

The retained coordinator registers each unit through Accounting with stable
per-unit command keys, associates it with its batch if present, and adds the
resulting `unit_ids` to the native product-opening manifest. One Save continues
through activation, voucher posting and opening finalization. Lost responses
reuse the same commands. The UI spaces serial steps and resumes temporary rate
limits within its save budget without creating another product request.

## Verification and review

- Catalog: two serial creation/retry cases, nine validation cases, and five
  zero-opening/batch-regression cases passed. These use native Catalog storage;
  cross-service owner calls in the coordinator tests use contract fixtures.
- Accounting: 27 native product-opening/tracking/source cases passed, including
  serial-only and batch-plus-serial posting, exact cost, replay and closed-period
  rejection. The new collision-check endpoint passed authorization, field denial,
  company-context and Unicode duplicate checks.
- UI: 50 serial, batch and ordinary Simple creation checks passed, including
  minimum IMEI count in an optional slot and rate-limit recovery. Browser checks
  covered both serial layouts at four widths in three themes (24 combinations).
- Shared validator/package version is 0.6.1 with consuming Python locks updated.
  Catalog/Accounting OpenAPI and generated API client 0.2.69 are synchronized.
- Scoped Ruff and strict mypy, console TypeScript, both owner OpenAPI checks and
  both generated-client checks passed. No database migration is required.
- Manual simplification and security review checked company/tenant scope, native
  field authority, bounded input/query sizes, Decimal costing, stable retry keys,
  native posting/audit ownership and closed-period enforcement. The slash-command
  review tools are unavailable in this environment; this was a manual review.
  No unresolved finding remains in this slice. Global repository coverage was
  not measured; validation was scoped to affected paths.

Decision 2026-11-04: expose existing serial requirements inline in Simple creation;
derive opening quantity from physical units and reuse native registration and
posting. Keep prices at product or batch level and keep required tracking enforced.
