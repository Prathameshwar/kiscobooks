# Purchase calculation presets

Authorized 2026-11-02: implement reusable Purchase calculation formulas with a
proper settings/bill UI, then review and fix findings. Preserve unrelated edits.

## Delivery phases

1. Add a bounded typed preset contract to existing Purchase voucher-type policy.
   Store it in existing immutable policy revisions. Validate names, identities,
   purpose/input/basis choices, dependencies, limits and effective type/class
   restrictions. Reuse Accounting's accepted component calculation authority.
2. Add a settings editor under Masters / Voucher types / Purchase / Entry rules.
   Offer starting recipes, editable named steps, calculation bases and a readable
   example. Saving uses existing authorization, version checks and revision flow.
3. Add a preset picker and step editor to Purchase Discounts & charges. Support
   product, account/service and mixed presentation lines, selected-line targets,
   fixed/percentage inputs, original versus named-adjusted bases, and amount
   basis. Keep entered supplier evidence and accepted owner calculations separate.
   Normalize the chosen recipe into existing native invoice components and retain
   dependencies on reload. Effective policy determines available choices.
4. Verify independent arithmetic examples, native policy/persistence/owner paths,
   permissions, malformed inputs, revision conflicts, UI states and rendering.
   Regenerate affected OpenAPI/client contracts. Review money, security, supplier
   comparisons, allocation and UX, then fix findings.

## Boundaries

Formulas select supported recipes; administrators cannot execute spreadsheet or
JavaScript expressions. Each commercial/tax/cost component is counted once.
Statutory rates and liability remain owned by the tax resolver. Presets do not
authorize posting or broaden type/class permissions. They use the existing entry
mode capabilities and invoice calculation/acceptance workflow.

## Evidence

The four phases are implemented. Presets are stored in existing voucher-type
policy JSON; no database table, migration, service, dependency or executable
expression language was added. OpenAPI and the generated client (0.2.56) include
the typed preset contract, and the client lockfile is synchronized.

Configure formulas at **Masters → Voucher types → Purchase type → Edit rules**.
Enable Purchase invoice entry and the discounts/charges the recipes need, then
create a formula, edit its ordered steps and optionally select a default. The
default is a suggestion: the bill's **Discounts & charges → Calculation formula**
picker applies it explicitly. Existing steps require replacement confirmation.
Changes to a preset never rewrite an existing bill's stored steps.

| Starting recipe | Example before tax on 1,000 |
| --- | --- |
| Standard purchase | 1,000 |
| Two-stage trade discount (10%, then 5% of 900) | 855 |
| Discounts on original amount (10% and 5% of 1,000) | 850 |
| Discount, packing and freight (10%, packing 2% of 900, freight 100) | 1,018 |
| Discount on tax-inclusive amount (10% of 1,180, illustrative 18% GST) | 900 excluding tax |

Each step exposes its name, purpose, fixed/percentage value, all/selected-line
scope, original/after-discounts/selected-step basis, net/gross amount basis and
assessable/no-change treatment. Rows are collapsible; step order is editable.
Dependencies must refer to preceding steps. The current native graph supports
at most 32 dependencies per step; only relevant row discounts are included.

Review findings fixed:

- Native mapping previously referenced only the last discount. It now names
  every contributing discount, preserving a three-stage calculation on save.
- Saved components retain native scope, purpose, amount basis and dependency
  graph. Source labels/preset hints do not decide financial behavior.
- Selected-line adjustments cannot silently fall back to the whole invoice.
- Removing/moving a referenced step produces validation instead of guessing.
- Gross-basis calculations awaiting verified GST can be saved and calculated by
  Accounting; invalid numeric, graph or line inputs still block saving.
- Commercial and tax balances are checked separately. A selected prior charge
  can contribute to a discount basis without treating an excluded charge as
  additional taxable balance.
- Fixed adjustments and percentages use exact integer arithmetic in the local
  example; native Decimal/Fraction calculations remain authoritative.
- Clearing existing components requires write access. Presets obey effective
  invoice limits; class restrictions remove unavailable presets and defaults.
- Manual additions receive distinct identities even after a preset with a
  matching step key. Formula labels show user-facing ordinals.
- The Purchase flow fixture now includes its required supplier role and waits
  for verified selection, replacing an assertion on removed explanatory text.

Verification: native local MySQL Vouchers policy/invoice/configuration suites
passed 72 tests. Accounting recipe/calculation acceptance passed 56 tests;
the affected UI suites passed 186 tests, including all nine Purchase save,
acceptance, approval, posting, revision and duplicate-bill flow cases. Results
are retained in the ignored `.tools/purchase-*-*.log` files. Preset
schema/domain coverage is 96% (90% floor). Strict mypy passed; Ruff and generated
API checks passed. Console application/formula type checks passed. The actual
authenticated Console settings route was reviewed with read-only typed preset
metadata at desktop/mobile widths in Light, Dark and Ledger themes: all eight
browser checks passed, with no runtime errors or page overflow.
The browser review does not write live company configuration.
The workspace-managed Vouchers API was reloaded after verification; its running
OpenAPI now exposes `PurchaseCalculationPolicy`, so the live app accepts the new
configuration contract.

Manual simplification and security reviews walked CLAUDE sections 5 and 6:
existing tenant/company access, manager permissions, immutable revisions,
optimistic conflicts, field checks, accepted owner calculations, posting and
audit boundaries remain in force. No callable `/simplify` or `/security-review`
skill is exposed in this session; the equivalent code reviews were performed.

The shared presentation calculation supports product, account/service and mixed
lines. The connected production Purchase page currently captures account/service
bills. Product/mixed stock capture remains the existing stock-owner integration
boundary; this change does not enable product/mixed posting. Company precision,
rounding, statutory rates and final amounts continue to come from Accounting,
and no real financial posting was used for visual verification.

## Review 2026-11-02 (Purchase bill end-to-end review)

Fixed, each with a test that failed first (`apis/vouchers/tests/test_purchase_calculation_presets.py`):

- **Presets belong to the Purchase configuration family only.** A COMMON or SALES
  configuration profile carrying `purchase_calculation` was accepted, published and bound, and
  then every non-Purchase voucher's effective configuration failed ("calculation presets require
  a standard Purchase invoice"), blocking Sales, Journal, Payment and note entry and posting.
  Create/revise now refuse presets outside the PURCHASE family, and effective resolution drops
  presets from any bound profile for a voucher that is not a standard Purchase (an older profile
  saved before this rule no longer breaks other kinds).
- **Discount limits are checked against the preset's total.** Accounting caps the total manual
  discount, so two 10% steps under a 15% limit were accepted as a preset and refused on every
  bill. The sum of percentage steps (an upper bound of the compounded percentage) and the sum of
  fixed steps are now compared with the limits, on the server and in the settings editor.
- **Preset names are distinct** (ignoring case and spacing), so the bill's picker never shows two
  identical choices.

Known, not changed:

- Editing a preset is a type revision. Like any rule change, it retires the type revision that
  drafts, submitted and approved bills were captured under, so those bills must be saved again
  (re-adopting the new revision) and re-approved before posting. Posted bills are unaffected.
- With discount compounding off, only discounts on the *original amount* are offered, even for a
  single discount: a preset cannot know whether a bill will also carry line discounts, which an
  after-discounts basis would compound.
