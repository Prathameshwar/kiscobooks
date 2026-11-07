# Batch and expiry create/edit UI review — 2026-11-07

Follow-up to [configuration and master findings](batch-config-master-review-2026-11-07.md).
The earlier findings remain recorded; this pass concentrates on the client screens.
No application code was changed.

Reviewed the current local tree, including:

- Batch registration, detail and correction at `/inventory/batches`.
- Simple product batch/date entry in the stock-and-prices step.
- Advanced product opening rows, final review and recovery editing.
- The Purchase **Create batch** dialog.
- Inventory Profile revision controls for lot tracking, required dates, FEFO,
  shelf life and minimum remaining life.

Rendered the actual React screens and shared `@janso/ui` controls in JSDOM.
Only remote service responses, product-mode context and Next navigation were
mocked. This verifies form behavior and DOM output; it is not a visual browser,
responsive-layout or deployed-system inspection.

## Findings

| ID | Priority | Screen | Finding |
| --- | --- | --- | --- |
| U01 | P1 | Batch detail/edit | A readable expiry disappears when manufacture-date read access is denied. |
| U02 | P2 | Batch create/edit | Required profile dates are not represented consistently in the form. |
| U03 | P2 | Batch edit | A reason-only date correction is enabled and submitted, then rejected. |
| U04 | P2 | Advanced final review | The review summary omits batch expiry, manufacture and physical MRP. |
| U05 | P2 | Advanced batch entry | Hidden expiry values remain in the payload after expiry is disabled. |
| U06 | P2 | Simple/Advanced batch entry | Client validation does not match native code/date constraints. |
| U07 | P2 | Advanced opening | Dates that cannot cover opening stock pass pre-submit validation. |
| U08 | P2 | Advanced recovery | Specific batch field errors disappear when returning to edit. |
| U09 | P1 | Purchase Create batch | An uncertain registration can be abandoned for a new body and request key. |

### U01 — Permitted expiry is blank or absent when manufacture is protected

**Reproduced in edit and detail.** Return a batch with a readable
`expires_on=2027-11-01`, but omit `manufactured_on` because that field is
read-denied. The edit screen initializes both dates only inside
`"manufactured_on" in row`, so its expiry input becomes blank. The detail screen
uses the same condition to include the whole dates section and omits expiry.

Sources: `StockTrackingPage.tsx:363`, `:487`, `:605`.

This is a cross-field display error: denying manufacture should not suppress an
independently readable expiry. The blank input misrepresents an existing value.
The changed-field filter prevents a write merely from opening the page, but a
user may enter a replacement while believing expiry was missing.

**Correction:** initialize and display each date independently. Preserve the
distinction between a protected field, an unset date and an existing readable date.

### U02 — Required date behavior differs between create and edit

**Reproduced.** With the verified product profile requiring both dates, the
registration inputs have `required=false` because their markers come only from
the static field-set. Client submission does check source requirements, but users
discover the requirement after trying to save.

Edit does not fetch the tracking source at all. A required expiry can be cleared
and PATCH submits `expires_on=null`; only the owner then rejects it. Shelf-life
requirements are also unavailable to the edit form.

Sources: `StockTrackingPage.tsx:513`, `:649`;
`stock-tracking-command.ts:126`. The current native date correction validates
against retained preparation facts in `stock_tracking.py:480`, so the client must
obtain the appropriate correction requirements rather than assume current company
defaults replace the batch's retained rules.

**Correction:** render required-date markers from verified applicable rules and
validate clearing/editing against those rules. Surface access blockers when a
required date cannot be written.

### U03 — “Correct dates” accepts a reason without a correction

**Reproduced.** Open an existing batch, enter a reason, leave dates unchanged, and
click **Save change**. The request contains only `expected_version` and `reason`.
Native Accounting requires at least one date correction and returns 422.

Sources: `StockTrackingPage.tsx:599`, `:961`;
`stock-tracking-command.ts:55`; native check `stock_tracking.py:483`.

**Correction:** enable correction save only when at least one editable date has
changed, or show a local “Change a date before saving” error. Hold/lifecycle
actions should keep their separate reason-only behavior.

Some existing UI retry tests use a reason-only correction and a permissive mock
that returns success. Those tests verify retries but mask this invalid-request
case. Keep a valid date change in the retry fixture and add a no-change assertion.

### U04 — Final review cannot verify the batch's physical dates and MRP

**Reproduced.** Enter manufacture `2026-01-01`, expiry `2028-01-01`, physical MRP
19, quantity 1 and purchase cost 10. The **Review before creating** section
summarizes the batch code, quantity, cost and sale prices, but includes neither
date nor the physical MRP. The values remain in the entry fields and payload.

Source: `AdvancedOpeningReviewStep.tsx:68`.

This particularly matters with multiple SKUs: the batch editor shows one selected
SKU, while the final summary should allow all batches to be checked together.

**Correction:** include both dates and physical MRP per batch, with clear labels,
formatted dates/currency and an explicit unset/protected state.

### U05 — Advanced hides stale dates without blocking their submission

**Reproduced with a saved row/settings change.** Keep an entered expiry in the
work data, then use refreshed options with `expiry_enabled=false`. The expiry
input disappears, `openingErrors()` returns no error, and `openingCommand()` still
sends the old expiry. Optional manufacture also disappears when the required-date
flag is turned off, even when an entered manufacture date remains in the row.

Sources: `AdvancedOpeningReviewStep.tsx:27`;
`advanced-product-opening.ts:48`, `:79`.

The owner can reject the disabled expiry, but the user cannot see or clear it in
that form. Simple entry already reports values that are no longer available under
the current settings instead of silently submitting them.

**Correction:** retain draft data, visibly identify incompatible hidden values,
and provide an explicit way to clear or restore the setting before submitting.
Do not silently discard entered dates on a settings refresh.

### U06 — Native batch-code and date constraints are missing from client validation

**Reproduced in the Simple policy; native rejection independently verified.**

- Codes `ss` and `ß` are accepted as different by the UI's lowercase comparison,
  but native NFKC/casefold comparison rejects them as duplicates.
- Forty `ﬃ` ligatures are accepted by the UI; native normalization expands the
  code to 120 characters and rejects it.
- Expiry `0001-01-01` passes `batchInputs()`, but native input requires dates
  on or after `1000-01-01`. The date field supplies no corresponding minimum.

Sources: `SimpleProductBatches.tsx:46`, `:52`, `:55`;
native `simple_product_creation.py:56`, `:67`, `:151`.
Advanced code comparison is weaker still: it trims/lowercases without NFKC
normalization, and its date check only compares the two strings.

**Correction:** use shared client validation for printable/normalized code
bounds, native-equivalent identity comparison and actual allowed date ranges.
Native validation must remain authoritative.

### U07 — Invalid opening dates are discovered after product creation/activation

**Reproduced in Advanced validation; native rejection independently verified.**
For books-begin `2026-11-07`, both of these positive opening rows pass
`openingErrors()`:

- Manufacture `2026-01-01`, expiry `2026-02-01`: already expired at opening.
- Manufacture `2027-01-01`, expiry `2028-01-01`: manufactured after opening.

The client only checks expiry against manufacture. Native preparation rejects
both against the opening date. The Advanced progression runs opening preflight
after product definition/setup/activation, so an avoidable date mistake can leave
created products awaiting corrected opening setup.

Sources: `advanced-product-opening.ts:48`;
`AdvancedCreationProgress.tsx:150`; native `simple_batch_preparation.py:83`.

**Correction:** validate known opening-date relationships before submission,
with per-row errors. Keep native preflight for permissions, current policy,
unit/warehouse facts and other conditions the client cannot establish.

### U08 — Backend batch error details are lost during Advanced recovery

**Reproduced.** Simulate opening preflight returning 422 with:

```json
{
  "message": "Check the batch dates",
  "fields": {
    "batches.0.expires_on": "Must cover the opening date: 2026-11-07."
  }
}
```

The progress screen displays only the generic message. **Review remaining setup**
passes the intent, status and step back to the wizard, without the field details.
The wizard then clears its errors. The user sees the original row but loses the
specific explanation and field focus.

Sources: `AdvancedCreationProgress.tsx:191`, `:192`;
`AdvancedProductWizard.tsx:151`.

**Correction:** retain field errors, prefix them with the affected SKU, map array
sale-price errors to displayed price levels, and carry them into the editor with
the relevant SKU/batch selected and invalid field focused.

### U09 — Purchase creation does not preserve an uncertain batch registration

**Reproduced with a lost-response simulation.** Create `LOT-REPLY-LOST`; simulate
503 after the request. The dialog reports that the batch could not be created,
unlocks its fields and offers no explicit same-request recovery. Change the code
to `LOT-SECOND-ATTEMPT` and submit: the second request has a new body and a new key.

Sources: `PurchaseBatchChooser.tsx:47`, `:73`;
`purchase-stock.ts:79`.

If the first request committed, its physical batch remains while the dialog
abandons its receipt. Changing the code can create another batch; retrying an
unchanged code after closing/reopening may instead meet an unexplained duplicate.
The simulation confirms client behavior, not actual duplicated database rows.

**Correction:** preserve the exact submitted key/body while the result is
uncertain, freeze edits, provide same-request recovery, and keep recovery data
across dismiss/reopen. Preserve structured server errors instead of treating all
exceptions as definite creation failures.

## Earlier issues still relevant to these screens

These are recorded in the first review and are not counted again:

- The standalone batch/date form does not honor company expiry feature visibility
  consistently with Simple/Advanced entry (B02).
- Batch master registration has no corresponding initial/subsequent price workflow
  (B05), and physical MRP is always labeled optional without Product Configuration
  admission (B06). The Purchase dialog has no physical MRP entry either.
- Optional manufacture cannot be entered in Simple/Advanced when its required flag
  is false, even if shelf-life policy would benefit from it.
- Advanced zero-cost acceptance and redundant SKU price/MRP requirements remain
  B07/B08 in the previous report.

## Checks that worked

The actual batch master edit screen correctly freezes inputs after a lost response
and replays the same body/key; the follow-up success is rendered. Its
**Discard and reload** action restores persisted dates and clears the reason,
including when the saved row version stays unchanged.

Inventory Profile client validation already enforces lot tracking for date rules,
mandatory expiry for FEFO/minimum remaining life, and remaining life not exceeding
shelf life (`product-profiles.ts:301`). No new defect is asserted in those checks.

## Evidence and limits

The [UI probes](testing/batch-ui-review/ui-probes.cjs) exercised all nine findings
with real screen/policy code and included two positive recovery controls. All
assertions passed on the final run. Passing assertions confirm the observed
defects; they are intentionally not fixed-behavior tests.

The [native probes](testing/batch-ui-review/backend-probes.py) ran with Catalog's
virtualenv: **5 passed**, independently confirming native rejection of U06/U07
inputs. Backend responses in React tests were mocked; no production or VM writes
were performed. The existing Vitest/esbuild environment limitation from the first
review remains; these probes avoid that worker process.

```powershell
# From the repository root:
node docs/testing/batch-ui-review/ui-probes.cjs

# From apis/catalog:
.venv/Scripts/python.exe -m pytest -c pyproject.toml -q ../../docs/testing/batch-ui-review/backend-probes.py -p no:cacheprovider
```

Prioritize U01 and U09, then align date requirements/validation and preserve errors
through review/edit recovery. Findings are notes for a subsequent agreed fix;
no application changes, commits or publication were made in this review.
