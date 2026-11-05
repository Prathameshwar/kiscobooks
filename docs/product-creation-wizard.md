> Current UI (2026-11-04): [Simple Product creation](simple-product-ready-plan.md) is available at `/masters/items/new`. Product edit/detail, advanced creation and batch/serial pages remain retired. The implementation below is historical.

# Product creation wizard

User scope: four steps, Create available on every step, configuration-dependent
product setup, validation, safe submission, responsive shared UI and final review.

## Phases

1. Extend the native atomic family/SKU create command with bounded initial master
   setup. Reuse existing handlers and their company, field, configuration and audit
   checks; retain one idempotent transaction. Synchronize OpenAPI and the client.
2. Add four freely navigable steps: product details; groups and units; tax and
   pricing; tracking and review. Preserve draft values on navigation. Create from
   any step validates the entire submitted draft and focuses the relevant step.
3. Exercise native rollback, replay, permission and validation cases; verify UI
   submission, recovery, configuration gating, desktop/mobile and three themes.
   Review implementation twice and fix findings before recording delivery.

## Boundaries

Opening stock and value are operational Accounting/Vouchers facts. Catalog rejects
them, including disguised custom fields. B21-B23 in the voucher delivery tracker are
not implemented. Do not store or imply stock balances as part of a master create.
The opening-stock section must explain this limitation until the separate native
movement, valuation and reconciliation work is authorized and designed.

Batch, expiry and serial tracking follow the selected published inventory profile;
individual lot/serial stock facts belong to receipt/opening execution. Prices saved
as drafts are explicitly identified as drafts requiring native publication.

Decision 2026-10-27: the user confirmed that opening stock stays clearly unavailable
in this wizard until its native implementation is delivered.

## Delivered flow

Decision 2026-10-30: each newly added product price starts with two decimal places,
which the user may change. A single price uses unnumbered field and remove labels;
two or three prices use matching 1, 2, 3 labels. Removing entries renumbers the
remaining rows and preserves their entered values and precision selections.
Verification: 70 tests across five affected suites and console TypeScript passed.
Manual simplify/security review found no further issue: exact input values,
native validation, storage scale and publication/access checks retain their
existing behavior. The unavailable review commands were covered manually.

Decision 2026-10-30: removed "Tax and price source / reason" from the shared
simple/family creation panel, draft state and payload. Initial tax and prices
require no note. The native assignment/draft/publication API and three backing
columns are removed together (Catalog 0211-0213); reviewed configuration versions,
permissions, exact amounts, publication and audit checks continue to apply.

Four freely navigable steps reuse FormLayout, Card, Stepper, ReviewList, the native
reference selectors and token CSS. Create is present on every step. Whole-draft
validation returns to the responsible step, preserves entered values and focuses
the invalid control. Default SKU identity follows the product until explicitly
edited. Creation hides unrelated classification tabs. Missing groups and units can
be created by an authorised administrator without abandoning the draft. Groups and
product types use the right-side create panels; units retain their new-tab workflow.

The native FamilyCreate.initial_setup input reuses existing group, unit, barcode,
attribute, tax and price handlers in the existing family/SKU transaction. Any failure
rolls back all new records and audit events. Native field and reference checks still
apply. Up to three fixed price drafts are created in existing books; their exact IDs
are retained in the command receipt and returned for bounded detail readback. Lean
list projections have not been widened to include amounts or sensitive detail.

The existing activation and price-publication controls remain required. No product
is silently activated, no price draft is described as live, and no stock is posted.

## Review findings and fixes

Correctness/security review: explicit company/field permissions and purpose-aware
purchase-price authority are checked on creation and replay. Setup error fields are
scoped to their owning step. Stock input remains forbidden. Replay verifies current
authority without reapplying an old creation precondition. The committed receipt is
the source of saved-price IDs, and readback checks company, record and SKU identities.

Live verification exposed Identity source refreshes advancing source_version even
when effective settings are unchanged. A canonical SHA-256 fingerprint binds the
reviewed effective options, profiles, numeric defaults, scope revisions and context.
Only the create mutation recomputes it under the normal policy lock. Identical values
permit using the current source checkpoint for the internal handlers; changed values
or policy generation still require review. Current field, permission, reference,
currency and publication checks are never skipped, and global pricing guards are
unchanged. Completed idempotent replays do not revalidate historical configuration.

Presentation/accessibility review: visible progress, keyboard step focus, retained
drafts, distinct SKU naming, exact ratio/amount input, profile-driven tracking labels,
protected-field placeholders and explicit draft-price messaging. Decorative checkbox
artwork no longer intercepts pointer input. Removed configuration options can be
explicitly cleared, and refreshing a conflict can retain the draft. A price-readback
outage now states that the product was already created, rather than claiming no change.

Manual equivalents of the unavailable simplify/security-review commands covered
CLAUDE.md sections 5 and 6. No service boundary, posting rule or tenant authority was
widened. There is no new wizard table or migration. For live verification, Catalog's
already committed 0207–0208 migrations were applied to bring the local database from
0206 to the current source head and restore readiness.

## Live evidence

Using tenant3 in the existing isolated Catalog enrollment verification company, the
browser created product WZ-MVQVI5YW from the first step after entering the other steps.
Native readback verified its primary group, base unit binding, barcode, typed attribute
and exact 123.4500 INR price draft. Reloading did not submit again. There were no final
browser or API errors. Opening quantity/value were absent throughout.

Private screenshots and test artifacts remain in ignored .tools/extension-masters.

## Final verification

All three phases are complete. The final focused Console run passed 122 tests
across seven suites; the additional request-policy suite passed 10 tests. Native
initial-setup integration tests passed all 12 cases, including rollback, replay,
field restrictions, exact price drafts and equivalent source refreshes. TypeScript,
Ruff and strict mypy passed. OpenAPI and generated Catalog client freshness checks
passed. A final read-only browser run checked all four steps across three themes
at desktop and mobile widths (24 captures), with no overflow, browser errors, API
failures or unintended submissions. Serial-tracked base bindings use whole-unit
precision and increment. Final correctness and presentation reviews found no
remaining issue within this scope; the opening-stock boundary remains explicit.

## Inline reference creation decision - 2026-10-30

The user selected + New beside the product group and type selectors, opening a
right-side panel. Group creation reuses CatalogMasterEditor; type creation reuses
ProductCatalogEditor and ProductTypeRevision for draft requirements and explicit
publication. The same reference component serves simple products and family/SKU
creation. Company-scoped read/manage permissions gate the actions; native field
policies and publication permissions still govern each command.

Save a compatible active group to select it automatically. A new type is selected
only after publication and an authorised compatible-option read. Without publishing
authority, the created type and draft remain available for a permitted publisher;
the product selection is unchanged. Closing the panel preserves the product draft
and already saved masters. Unsaved panel edits require discard confirmation, and
pending/uncertain writes retain their request keys. Panel form events are isolated
from the product form. See [review](product-reference-create-review-2026-10-30.md).
