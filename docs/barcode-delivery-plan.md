# Barcode delivery plan

Status: implemented and reviewed (2026-10-12). Catalog owns product-code identity;
Vouchers continues to own financial documents. A scan resolves to protected Catalog facts
before a voucher is composed; no synchronous Catalog call occurs in a money transaction.

## Phase 1 — safe identity lifecycle

- Allow a permitted operator to add or retire a barcode on an ACTIVE item without opening
  structural item edits. Preserve company ownership, idempotency, audit, and row versions.
- Keep an ACTIVE item valid under REQUIRED barcode configuration when retiring a code.
- Ensure a bound code refers to an effective fixed-ratio unit and cannot silently change
  pack quantity when that binding is revised, even after retirement. Retired codes retain
  ownership and require a new binding for a different pack meaning.
- Regression tests cover active-item edits, requiredness, permission, and pack revisions.

## Phase 2 — generation and resolution

- Add an idempotent Catalog command for an opaque company-scoped internal CODE128 value.
  This allocates an internal identifier, not a GS1 GTIN. Generate the value and create its
  code row atomically under the existing product command lock.
- Add protected, exact company-scoped scan resolution returning SKU/version, unit binding
  and effective revision, ratio, and parsed GS1 lot/expiry/serial hints. Unknown, inactive,
  ambiguous, stale-pack, and unauthorized results fail closed. Do not fetch QR URLs.
- Normalize GTIN lookup consistently across 8/12/13/14-digit representations and prevent
  duplicate company ownership of equivalent GTIN values during writes.

## Phase 3 — voucher handoff and operability

- Return the item ID/version, unit ID, and unit revision required by voucher composition.
  Voucher execution validates its existing item/unit owner facts; the scan is a lookup,
  never an alternative authority for price, tax, stock, lot, or serial posting.
- Expose a bounded exact-code lookup, regenerate OpenAPI/client types, and add a console
  voucher scanner that fills the protected item/version/unit fields. Scans with GS1 lot,
  expiry, or serial hints are refused by this voucher form because it cannot record those
  facts; the read endpoint returns the hints for a future tracking-capable form.
- Generate code data separately from private SVG label rendering. The label endpoint
  renders Code 128, GTIN retail formats, or QR according to the registered type.

## Final review

Run affected Catalog and client suites, lint, strict typing, contract generation and a
second pass over tenant isolation, field denies, idempotency, history and pack ambiguity.
Operational scan-to-voucher work must remain unavailable wherever inventory execution is
not yet available; a scan cannot bypass voucher eligibility or stock guards.

The initial scanner contract supports ordinary Code 128/GTIN/QR values and the GS1-128
AI 01/10/17/21 subset. Unsupported AIM identifiers and unknown GS1 AIs fail closed.
Label layout, printer setup, and bulk label sheets remain client concerns. Code lookup
does not create a stock, lot, serial, or voucher transaction, nor a persistent raw-scan
audit event; the subsequent voucher command has its normal audit and posting checks.
