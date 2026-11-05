# Dedicated company GST settings page

## Add forms in right drawers (2026-11-02)

Authorized follow-up: open Add GST registration and Add outward reporting profile
in right-side drawers, keeping the history page simple.

1. Verify the current inline behavior with a failing drawer regression. Reuse the
   shared Drawer, move form actions to its pinned footer, and keep failures with
   the form. Preserve the existing scoped APIs, validation and retry keys.
2. Guard drawer dismissal for entered values and pending requests; verify focus,
   cancel/discard, save/failure and evidence behavior with the real components.
3. Review desktop/mobile layouts in all themes, run affected tests and a production
   build, and refresh the managed local console with the product-heading change.

The drawer regression failed for both inline forms before implementation. Both
now use the existing shared Drawer, unique form IDs and its pinned footer, without
nested cards. Errors stay inside the open drawer; successful saves close it and
refresh the history. Header Close, Cancel, Escape and the scrim preserve dirty
values through Keep editing/Discard. Confirmation closes before the drawer so
focus and body scrolling restore correctly. Pending saves and evidence hashing
block all dismissal paths. Server choices, exact turnover strings, dated validity,
evidence hashes and unchanged-payload retry keys retain their existing contracts.

Verification: **53 console tests** and **18 shared overlay tests** pass. All **96
scenario/width/theme checks** pass (8 scenarios at 1440/768/390/320px in light,
dark and ledger), including independent registration/profile drawer scenarios.
Checks confirm the right edge, full height, readable fields, no horizontal overflow,
scrolling body and pinned save actions. Desktop and mobile screenshots were
inspected in `.tools/company-gst-settings-review/`; logs use `.tools/gst-drawer-*`.
Manual simplification/security/correctness review found no remaining blocker in
this scope; named review commands are unavailable. No API, permission, tax
calculation, dependency or live statutory data change was needed.

Production TypeScript/build checks pass (`.tools/gst-drawer-build.log`). The managed
console was refreshed to the prepared build and reports UP on port 4320. The GST
route still returns 307 to sign-in without a session. The shorter Product
configuration heading is included. Original Next source configuration is unchanged;
task-file whitespace checks pass. No commit or publication.

Scope authorized on 2026-11-02: place a GST settings action after Edit company
settings, move registrations and outward reporting profiles to their own page,
and simplify company configuration. Preserve the local layout, concurrent edits,
existing statutory APIs, dated histories and server-owned management capabilities.

## Phases

1. Add `/companies/{companyId}/gst-settings`, company-scoped admission and verified
   company context. Move the two GST sections out of configuration; preserve safe
   return navigation and provide the adjacent action for readable India GST companies.
2. Verify registration/profile forms, loading and recovery, empty/read-only states,
   existing writes and retained evidence. Carry draft and pending protection onto
   page navigation, report links and refresh. Fix any findings within this UI scope.
3. Run affected unit, route, navigation and TypeScript checks. Check desktop,
   tablet and mobile layouts in light, dark and ledger; inspect screenshots and
   manually review simplification/security/correctness if named commands are unavailable.

The page does not switch the working company. Report links require the selected
company and its scoped report permission. Non-GST company configuration retains
its existing tax-applicability view. No backend change or publication is requested.

## Delivery and review

- Configuration now contains company defaults and features. Its GST action follows
  the edit action, remains available to scoped readers, and does not load GST lists.
- GST settings verifies the named company before loading either history. It keeps
  the originating configuration, settings/directory filters and accounting context;
  direct visits return to company configuration. Invalid/external returns fall back.
- Forms and dated closures reuse the native Identity contracts and server-returned
  capabilities. Report links require the selected company and scoped report access.
  GSTR-3B's company-settings link now opens the dedicated page.
- Failed initial history reads no longer display empty lists. Outward profiles have
  explicit loading/reload states. Drafts and pending writes guard refresh, back,
  breadcrumbs, report links and company changes. Containing pages own discard
  confirmation; standalone GST components retain their browser guards, preventing
  a second unload warning after an already-confirmed discard.
- Both GST cards retain the compact spacing. Company headers can wrap their status
  badge at 320px, keeping the name readable without reducing button target sizes.

## Verification

- The missing GST action, false empty-history state and duplicate unload warning
  were reproduced before their fixes. The affected company/configuration/tax/route,
  navigation, API-client and BFF tests pass; final GST draft/form checks pass **31
  tests**, final configuration checks **37**, and GSTR-3B checks **12**.
- All **84 scenario/width/theme checks** pass: configuration, GST history, expanded
  GST forms, empty GST registrations, read-only GST, VAT and `none`, at 1440px,
  768px, 390px and 320px in light, dark and ledger. The 320px company-heading failure
  was reproduced and fixed. Screenshots include compact spacing, control bounds,
  heading readability, action ordering and responsive summaries. Evidence:
  `.tools/company-gst-settings-review/` and `.tools/company-gst-settings-*.log`.
- Two broader product-navigation tests still fail because `scope_kind=COMPANY` is
  removed from a product return query. Both failures reproduce using the original
  committed administration-navigation helper through an isolated test alias;
  evidence is `.tools/company-gst-settings-baseline-final.log`. Product code and
  those expectations were preserved because they are outside the GST move.
- Manual simplification/security/correctness review found no remaining blocker in
  this scope. The named review commands are unavailable. UUID admission, named-company
  reads, strict existing write contracts, dated history, decimal strings, evidence
  hashes and replay keys retain their existing boundaries. No dependency, permission
  key, schema, tax calculation or business data changed.

The console uses a production server locally. Builds are prepared in a separate
generated directory, retaining the existing `.next` output and original source
configuration. Only the workspace-managed console is refreshed after verification;
the previous output remains available for rollback. No commit or publication.

Final console TypeScript and production build pass. Concurrent Trial Balance
import/type changes briefly interrupted delivery; the corrected workspace then
passed checking and `.tools/company-gst-settings-build-delivery.log` records the
successful build, including the GST route. The workspace-managed console was
refreshed and reports **UP** on port 4320. An unauthenticated request to the new
company GST route returns **307 to sign-in**, preserving route protection. Original
`next-env.d.ts`, `tsconfig.json` and Next configuration remain at their existing
paths and unchanged. Task-file whitespace checks pass. No live statutory records
were changed; form/permission behavior was verified with fixture service responses.
