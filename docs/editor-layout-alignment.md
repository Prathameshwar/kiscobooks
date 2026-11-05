# Edit page layout alignment

Approved scope: apply the shared routed-editor styling to the previously listed
Accounting edit pages, product configuration drafts, custom-field/value editors,
SKU/family attribute editors and the platform tenant-administrator editor.

1. Add regression assertions for accessible sections, one form card, contextual
   guidance and attached Save/Cancel actions. Align the shared Accounting editor
   (29 resource forms) and product configuration drafts.
2. Align product fields, inline attribute masters, SKU/family attributes and the
   tenant-administrator editor. Reuse FormLayout, SectionHeader, CardBody,
   FormActions and responsive shared field grids. Preserve editor behavior and
   permission/immutability/retry/discard checks.
3. Run affected editor and shared-component checks, Console TypeScript and browser
   layout checks in desktop/mobile themes. Review security/correctness and record
   results. No API, database, permission or source-sync changes are in this task.

## Completed layout decisions (2026-10-27)

All three phases are complete. Routed Accounting and product-configuration
editors now use one form card, named sections, contextual guidance and an attached
action footer. The shared Accounting implementation covers 29 editable resource
forms. The tenant-administrator editor uses the same layout and responsive field
grid. Product field definitions, saved values, adoption review, SKU/family
attributes, variants and inline attribute masters use the shared cards and
section hierarchy without the old nested manager padding.

FormActions accepts an inline Cancel callback in addition to its existing safe
navigation link. Inline Cancel remains a non-submit button and respects pending
state. Attribute values and repeated configuration groups use FieldGroup instead
of browser-default fieldsets. A narrow-screen browser regression exposed long
action groups spilling outside their card; a targeted shared footer rule now
allows those groups to wrap inside it.

## Verification

- 384 unique Console tests passed across the affected editors, route contracts,
  navigation, configuration workflows and permission/error branches. Three stale
  Accounting navigation assertions were updated for the existing single Masters
  menu; no application navigation behavior changed in this task.
- All 2,060 shared UI tests passed across the run and the final targeted rerun.
  The newly added attribute-group regression first failed against the old markup
  and passed after the fix. The other layout and footer regressions also failed
  before their corresponding changes. Existing jsdom navigation and React act
  warnings remain non-failing.
- Console and shared UI TypeScript checks passed.
- A local browser fixture rendered the actual components, Console shell and CSS:
  five editor scenarios, 1440/1024/390/320 px widths and Light/Dark/Ledger themes
  (60 combinations). All passed control/card-boundary overflow, reachable footer,
  no nested forms and no browser runtime-error checks. Attribute layouts were
  rerun after the final FieldGroup change. Screenshots were visually reviewed.
  These are fixture-based layout checks, not live service CRUD verification.
- Manual simplification and CLAUDE sections 5/6 review found no new issues. The
  named /simplify and /security-review commands are unavailable in this session.
  Request bodies, company/tenant scope, metadata-driven field protection, exact
  numeric validation, immutable states, version/idempotency handling and discard
  guards remain intact. No dependency, schema or backend changes were needed.
