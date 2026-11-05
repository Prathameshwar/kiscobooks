# Simple product details switches

Authorized 2026-11-04: when Product Configuration permits Brand, Model or Barcode,
show a switch in Simple product creation and capture the corresponding details.

## Delivery

1. Verify configuration, field permissions and the native barcode owner; add
   regression tests for conditional entry and creation through activation.
2. Add optional switches, respecting configured defaults; required options stay
   enabled. Capture Brand plus optional series, independent Model, and one
   product barcode with its existing CODE128, GTIN or QR format.
3. Pass the barcode through native initial product setup, retaining validation,
   company uniqueness, audit, field access and command replay. Regenerate the
   API contract/client and verify backend, UI, layout and recovery regressions.

## Decisions

- Disabled options are hidden. Optional switches use the configured default and
  require their main value when enabled. Required switches cannot be turned off.
- Turning an optional switch off omits its details from Save. Model does not
  depend on Brand; Brand series requires a selected Brand.
- Barcode input is a string, including leading zeroes, attached to the product.
  Use the existing barcode validation and storage; no schema migration or new
  product approval/activation step is introduced.
- Barcode capture was initially added to Simple creation. The subsequent
  [creation/import review](simple-product-create-import-review.md) adds configured
  barcode columns and native barcode validation to Simple import as well.
- The [Category and Manufacturer extension](simple-product-category-manufacturer.md)
  applies these same switches to category scheme memberships and Goods manufacturer
  selection with an optional site in Simple creation.

## Verification

- The failing regressions reproduced the absent switches and missing barcode
  metadata before implementation.
- 41 creation/configuration UI tests pass. Tests cover default-off/default-on,
  required switches, dependent Brand series, omitted inactive details, field
  permissions, error focus and exact retry bodies/keys.
- Goods, Services, configured and error layouts were checked at 320, 390, 768 and
  1440 pixels in light, dark and ledger themes. The configured layout was rerun
  after enlarging the clickable switch labels to 44 pixels. The 390-pixel dark
  configured screenshot was visually reviewed.
- TypeScript, strict mypy for the five changed backend modules, Ruff, generated
  Catalog OpenAPI/client checks and scoped whitespace checks pass. Client version
  is 0.2.68; shared UI version is 0.1.65. No migration is needed.
- Six existing-flow/import checks pass: Goods/Services with and without inventory,
  live prices, ordinary creation replay, service stock rejection, and the import
  guard for required barcode. The dedicated suite passes all eight checks in its
  final clean run (128.46 seconds): required barcode for Goods/Services, activation,
  leading zeroes, duplicate rollback, disabled/invalid entry, field permissions,
  legacy command hashes and the import guard. Earlier test assumptions about
  omitted read-denied metadata and Decimal normalization were corrected to match
  the existing native contracts; production permission/Decimal rules were unchanged.

## Final review

Manual equivalents of `/simplify` and `/security-review` were used because those
commands are unavailable in this session. The switches reuse the shared Toggle
and FieldGroup; native metadata remains authoritative. Barcode creation uses the
existing initial-setup transaction and native barcode owner, including audit,
field policies and uniqueness. No new permission or public endpoint was added.

Review found and fixed two integration concerns: an absent barcode must not
change previously admitted command hashes, and entered optional details must not
be silently omitted when refreshed field access makes them unwritable. The form
now retains those details and blocks Save until the user explicitly turns the
optional section off or regains access. Required sections remain blocked.

Native read and write permissions remain independent: a read-denied barcode field
is omitted from metadata and read responses; a write deny rejects creation and
rolls back its product/barcode rows. No new read permission is inferred from a write.

Verification notes: the first broad UI run exceeded the existing five-second test
budget under parallel load; the final single-worker run passed all 41 checks with
a 15-second budget. One early SQLite creation run returned an OperationalError;
a diagnostic rerun and subsequent Goods/Services cases passed without a production
change. Full repository CI and a new MySQL migration run were not executed for
this additive API/UI change.
