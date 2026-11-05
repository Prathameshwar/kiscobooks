# Product group/type create panels

2026-10-31 refinement: the selectors now use the shared outlined IconButton with a
plus icon, retaining the accessible name and adding its hover tooltip. The compact
square action remains beside the selector at phone widths, centered on the control.
Creation permissions, drawers and draft preservation retain their existing behavior.
The refinement passed 21 focused tests, including browser alignment at three widths
in all three themes. Manual simplification/security review found no additional
issues; the shared button retains keyboard focus, accessible naming and disabled state.
The full Console typecheck currently reports errors in concurrent Purchase-print
work (generated print routes, PurchasePrintPreview and the PrintJobDetail client
contract); no errors were reported in the changed product-reference files.

Implemented a compact plus button beside the product group and product type selectors. Each opens
the shared Drawer from the right. Existing CatalogMasterEditor, ProductCatalogEditor
and ProductTypeRevision forms handle field metadata, custom fields, native requests,
validation, retry and publication. Ordinary standalone master routes retain their
existing navigation and behavior.

A compatible active group selects automatically after saving. Type creation proceeds
through draft requirements and the existing explicit publication confirmation. An
authorised kind/parent-scoped published-option read must succeed before selection.
If the creator cannot publish, the saved type/draft remain intact for a permitted
publisher and the product selection remains unchanged. A failed final read can be
retried without recreating or republishing anything.

The lookup alone refreshes after creation. Product fields/drafts remain mounted;
both simple and family/SKU forms retain entered identity and selected group. Closing
an edited panel asks to discard its unsaved changes; the product draft and masters
already saved remain intact. Pending/uncertain writes block closing and retain their
body/key for retry. The native group form freezes uncertain embedded saves, while
its ordinary standalone behavior remains intact.

Company-scoped item_group.read/manage and product_type.read/manage govern creation
actions; type selection also requires configuration read access. Publication still
requires its separate native permission and writable publication fields. No role or
permission key was added. All writes use the existing product-fields boundary and
owning Catalog APIs. No backend route, public schema, migration, dependency, default
seed, financial posting, stock movement or release flag changed.

## Verification and review

- Two missing-action cases failed before implementation.
- Final affected run: 12 suites / 229 tests passed, zero skips. Evidence:
  `.test_artifacts/product-reference-create-complete.json`.
- After simplifying the shared uncertain-save predicate, the final three affected
  suites passed 82 cases again; these overlap the 229 above. Evidence:
  `.test_artifacts/product-reference-create-reviewed.json`.
- Shared form/control cases include native validation, protected fields, read-only
  access, group compatibility, saved drafts without publication, exact uncertain
  group/publication retries, cancellation/focus restoration and parent verification.
- Real product forms in both modes retain their product identity after group save
  and type cancellation. Only the requested native master write is issued; no
  product write is triggered by the panel.
- Native Edge layout tests: two cases covering 18 source/width/theme combinations
  at 1440, 768 and 390 pixels in light, dark and ledger. Same-row top/height alignment,
  mobile wrapping, right-edge anchoring and horizontal overflow checks passed.
  Evidence: `.test_artifacts/product-reference-create-layout-final.json`. Phone captures
  were visually inspected. These render component fixtures for geometry, not live
  API journeys. Browser tests are explicitly opt-in and require the existing local
  QA Playwright runner; normal component collection has no new runner dependency.
- Console TypeScript passed. Task-scoped whitespace and artifact checks are recorded
  with the final local commands. Repository-wide coverage was not rerun or relabelled.

Manual equivalents of unavailable simplify/security-review commands walked
CLAUDE.md sections 5 and 6. Review reproduced and fixed React portal submission
bubbling into the outer product form, which had moved the family wizard back to
validation. The panel now isolates submit/Enter events; the integrated regression
passes in both modes. Review also added frozen embedded group retries, preserving
their exact key/body after interrupted writes. A first cold lazy-import test wait
was too short and now has an explicit bounded import wait. No remaining reproduced
defect was found within this scope.

The CSS shares label/control/hint grid rows with the action, so wrapped labels and
error text do not need guessed vertical offsets. The compact plus stays beside
the selector on small screens. Shared drawer focus trapping, Escape, busy-close prevention and focus
restoration remain in use. Callback receipts and option reads preserve company,
parent, active/publication and product-kind checks; native server field policies
remain authoritative. Existing records are never silently deleted on cancellation.

## Live acceptance pending

The local Identity API at port 8001 was checked and remains offline after the VM
shutdown. Live authenticated creation/publication/readback has not run for this
change. No manual database manipulation was performed. After services resume, use
the QA tenant and verify + New group save and + New type/create/review/publish in
both product modes, including cancel/retry and protected access. Keep that live
ledger separate from local fixture results.

See [CSV](product-reference-create-results-2026-10-30.csv),
[plan/todo](product-reference-create-drawer-plan.md) and
[reusable commands](testing/tenant-admin/README.md#product-group-and-type-create-panels).
