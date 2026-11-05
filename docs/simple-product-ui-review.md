# Simple product creation UI review

Authorized 2026-11-04: review and improve the current Simple product form using
the existing product configuration and save workflow.

## Review phases

1. Check the current layout, field applicability, validation, save recovery and
   navigation. Capture regression tests for confirmed issues.
2. Correct the form using shared components and styles. Keep Goods/Services,
   configuration, permissions and exact decimal inputs consistent with the API.
3. Run affected UI tests, TypeScript and browser layout checks across widths and
   themes; inspect screenshots and record findings and limitations.

## Full creation review follow-up (2026-11-04)

The user requested another end-to-end UI review after batch and serial input were
added. Follow the phases above across ordinary Goods/Services, configured details,
tax, multiple prices, batches, serials, custom fields, and save/recovery states.
Reproduce findings before fixes, retain native API/posting behavior, and run all
creation interactions plus responsive checks for both creation steps.

Confirmed and corrected:

- A server error for Product details could stay hidden on Stock and prices. The
  form now reveals the step containing the invalid field and focuses an editable
  visible input, or the error summary when editing is locked. Correcting the field
  and selecting Next clears the prior rejection so navigation can continue.
- Custom fields conditional on entered native details (for example Model) used
  different values for rendering and submission. Both now evaluate the current
  form values. Required conditional inputs validate and entered values are retained
  for both product and shared custom fields.
- Indexed server errors for batch selling prices now identify the correct named
  price field and receive keyboard focus, instead of appearing only as a summary.
- Batch serial errors appeared twice. Each error now stays in its serial section
  beside the affected identifier, with general errors retained where appropriate.
- A navigation regression test still expected the retired draft import label.
  Its expectation now matches the existing ready-product import contract; import
  behavior was not changed.

Verification completed:

- All 92 creation/navigation regression checks passed. A focused coverage rerun
  passed all 64 creation cases: 99.6% statements/lines, 96.55% functions and 87.23%
  branches across SimpleProductCreate and SimpleProductBatches, above the configured
  thresholds. These figures describe the reviewed components, not the whole repo.
- All 12 browser scenarios passed at four widths and three themes (144 layout
  combinations), including saving and completion. Visually inspected mobile Goods,
  configured desktop details, batch grids, ledger-theme classification, saving and
  the small-screen success state. No additional alignment/style issue was found.
- Console TypeScript and scoped whitespace checks passed. No shared CSS or package
  version change was required.

Manual simplicity/security review preserved native permissions, exact decimal
strings, company-keyed form state, save receipts and retry keys. No API, schema,
posting or shared-style change was needed. The slash-command review tools remain
unavailable. Browser fixtures use real components, fonts and shared CSS with
mocked API responses; live gateway/worker posting is outside this UI-only rerun.

## Decisions

- Preserve the one-Save flow, the configured stock step and native posting workflow.
- Constrain desktop line length and pair name/code; retain one column on mobile.
- Make required fields and opening-price dependencies explicit. Focus validation
  errors and the completed result for keyboard and screen-reader users.
- Preserve the caller's return destination and protect all user-entered changes.

## Evidence

Completed 2026-11-04. Confirmed failures were reproduced in tests before fixes.

### Findings corrected

- The generic page rule overrode the form width. The shared selector now keeps a
  centred 52rem maximum, with responsive name/code pairing and mobile stacking.
- Purchase price now becomes visibly required for a positive opening quantity.
  When it is unavailable, the form explains how to resolve that dependency.
- Required Brand, Model and configured prices receive client validation. A
  protected required field disables Save with an explanation. Conditional Type
  access is respected, and entered opening stock cannot silently disappear if
  its write access changes while editing.
- Validation shows a summary and focuses the first editable invalid field.
  Custom and shared custom server errors appear beside their own inputs.
- Selected HSN/SAC and GST rule codes stay visible with their descriptions.
- Code-only, pricing, type and additional-field edits trigger the unsaved-change
  guard; loading the suggested group does not. Return destinations survive the
  success screen and Create another product action. Completion receives focus.
- A long-running posting explains that its saved progress is retained and offers
  Retry Save. The original command/key remains unchanged on uncertain responses.

### Verification

- 30 interaction tests pass, covering default and configured fields, Goods and
  Services, GST, exact decimal validation, custom references, required fields,
  denied access, 401/403/500 loading errors, correction and recovery.
- Focused form coverage passes the configured thresholds: 99.19% statements/lines,
  100% functions and 87.06% branches. This is not whole-repository coverage.
- 48 navigation/product-route regression tests pass.
- Four browser tests cover 48 scenarios: Goods, Services, a populated configured
  form and validation errors; 320, 390, 768 and 1440 pixels; light, dark and ledger
  themes. Width, control containment, focus, conditional fields and themed actions
  are checked. Desktop and mobile screenshots are inspected.
- Console TypeScript and whitespace checks pass. Shared UI is 0.1.62; linked
  workspace consumers resolve the same source without a pinned lockfile change.

Artifacts: `.tools/simple-product-ui-review/` (screenshots and focused coverage).
The browser fixtures render the real component and shared CSS using mocked API
responses; live gateway/worker posting was not rerun during this UI review.

### Final review

Manual simplicity and security review was used because `/simplify` and
`/security-review` are unavailable in this session. The relevant findings are
listed above and have regression coverage. No additional unresolved issue was
found in the reviewed UI paths. Server permission checks, immutable native
posting and idempotency remain the authority; this review changes presentation,
input validation and recovery guidance. Price and quantity inputs remain strings,
return destinations use the existing allowlist, and only the command key is
retained in session storage.

## Alignment and appearance follow-up (2026-11-04)

User request: check the new product page's alignment, UI and look and feel.

- Reproduced the desktop mismatch: Type was 367px wider than the corresponding
  form column. Type, Model and MRP now use the existing responsive field columns.
- Reproduced the mobile spacing issue: combined page/card padding left only
  276px for inputs at a 390px viewport. Scoped shared CSS now leaves 324px at
  390px, and 254px at 320px, with the same single-column mobile layout.
- Kept navigation, field labels, optional detail switches, help/error text and
  Save/Cancel in the existing design system. Shared UI is now 0.1.67; linked
  workspace consumer lockfile resolutions remain current.
- Browser review now embeds the shipped Inter font and checks field widths,
  horizontal alignment and paired input positions as well as overflow, focus,
  themes and conditional fields.

Verification completed:

- 38 creation interaction tests passed, plus five browser cases covering 60
  viewport/theme combinations: Goods, Services, configured details, validation
  errors and unavailable entries at 320, 390, 768 and 1440px in all three themes.
- 329 affected shared UI/theme checks passed, including field structure, layout
  styles, contrast and class coverage. Console TypeScript and scoped whitespace
  checks passed.
- Visually inspected the updated desktop and mobile captures, including the
  populated configured form in dark and ledger themes. Screenshots remain in
  `.tools/simple-product-ui-review/`.

Manual simplicity/security review found no further issue in these presentation
changes. Existing shared field pairs and scoped token-based CSS provide the
layout; permissions, request bodies, exact values and save recovery are not
changed. `/simplify` and `/security-review` are unavailable in this session.
Browser fixtures use the real component and CSS with mocked API responses;
live gateway posting and full repository CI were not rerun for this UI change.
