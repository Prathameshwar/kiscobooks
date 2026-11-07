# Mixed product import and VM fixes

Authorized by the user's 2026-11-06 request to import ten mixed products, verify end to end, and fix findings in the VM and actual application code. This extends the preceding Advanced-mode VM review.

## Execution phases

1. Preserve the existing workspace changes, reproduce the three confirmed defects with failing regression tests, and prepare seven Goods plus three Services against current native import templates. Advanced import retains its documented draft lifecycle.
2. Fix default selling-price choices, explicit optional batch selection, and verified company-context forwarding for Catalog batch-pricing endpoints. Extend fixes for findings from the native ten-product run: bounded independent import continuation (preserving ATOMIC transactions) and effective inventory facts honoring the saved SKU batch choice. Run affected Catalog, Identity and Console tests plus lint/type checks; review authorization, money precision, replay and source guards.
3. Build and deploy a release based on the current VM release with only the task's application changes. Verify service health and the repaired browser/gateway paths.
4. Import the ten products through the native staged/validated/reviewed commit workflow. Complete their documented setup/activation and eligible Goods openings. Verify persisted tax, default sale prices, batch prices, stock quantities/values, posted vouchers, balanced journals, replay and directory visibility. Retain import files and results.

## Status

In progress. The result and retained fixture identifiers will be recorded here after execution. Product/serial/batch management pages previously retired by decision are outside the repair scope.
