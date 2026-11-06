# Purchase print fixes — 2026-11-05

Authorized by the request to fix the purchase print review findings. The saved
Purchase revision and Accounting calculation remain the authorities. Print changes
must never price or post stock, and every new field must obey current read policies.

## Phases

1. **Source and disclosure.** Add bounded, read-authorized stock references to the
   frozen print snapshot, including warehouse, bin, batch and serial identities.
   Refuse to disclose a denied stock field. Add regressions for Product and Mixed
   bills, replay/download authorization and snapshot integrity.
2. **Standard layout.** Show stock references in a compact receiving block and
   restore the entered amount on Mixed account rows. Show tax components from the
   frozen Accounting calculation, without recalculating tax. Bump the renderer and
   built-in layout versions in Vouchers and Design together.
3. **Designer and Console.** Expose saved receiving references as a custom binding;
   say clearly at template creation which built-in details the starter omits. Improve
   actionable print refusals without leaking owner internals. Keep the shared
   capability manifest, contract, and tests in sync.
4. **Verification and reviews.** Run focused Vouchers/Design/Console suites and
   type checks that are available locally. Review authorization, tenant scoping,
   Decimal handling, immutable job identity, and output escaping twice; fix any
   issues found. Record deployment-only checks separately.

Company legal address/PAN/GSTIN needs a versioned, signed Identity context and
field-policy decision. It is not included in the existing signed print context;
the internal voucher must not invent or fetch these from a different owner.

## Outcome and limits

Phases 1–3 have code and focused regressions. The default now includes saved stock
references and tax component totals; Mixed account lines label their entered amount.
Designer can bind `voucher.receiving_summary` but its starter remains a subset of
the built-in layout. It explicitly tells the person about omitted settlements,
adjustments and receiving details before creation. Readable warehouse names, batch
codes, serial codes and expiry require an owner print-label contract with current
field rights. Full browser rendering and cross-service tests remain deployment gates.

## Verification and review (2026-11-05)

- Python compilation passed for changed Vouchers and Design sources and their focused
  test files. Direct pure-domain smoke checks passed for default Account/Mixed content,
  receiving references, malformed serial rejection, custom receiving binding, and tax
  component display. The `print-capabilities@2` JSON matched the live manifest exactly.
- The affected pytest suite could not start: this Python 3.12 installation lacks
  `pytest_asyncio`, and the package was unavailable from its configured package index.
  Console dependencies are absent (`mfes/node_modules`), so Vitest/typecheck and a
  real-browser PDF review remain unverified here.
- **Review pass 1 — correctness:** checked the saved `StockInput` line identities against
  goods, bounded the copied references, rejected repeated serials and malformed UUIDs,
  retained Accounting's Decimal tax components, and bumped Design's fallback with
  Vouchers' renderer/layout versions. The custom binding is escaped like other fields.
- **Review pass 2 — disclosure:** the stock block is copied only when the current actor
  can read all contributing stock fields; changed or newly denied receiving details
  invalidate the frozen PDF at download. Existing voucher/owner scope, calculation,
  label and digest checks still run. Regressions cover field denial during creation
  and at download. No new endpoint, money write or audit payload was introduced.

### Final review follow-up

The custom receiving binding was initially a fixed-height canvas field. A direct
rendering check confirmed that its HTML could hide a long serial list. The renderer
now puts this binding in a growing flow zone and the shared capability check refuses
layouts that place it beside other elements or zones in the same vertical band. A
focused regression and a direct rendering check cover growth and both collisions.
