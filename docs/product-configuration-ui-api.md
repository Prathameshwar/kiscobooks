# Product configuration UI, API and database

Current decision, 2026-10-30: configuration ownership is Company only. The directory
and owner/scope selectors have been replaced with the company overview and direct
create/edit → review → publish flow. The first draft creates its company scope in
the same native transaction. Retired scope history remains readable but cannot be
edited, published or selected for current defaults. This supersedes the original
five-level delivery notes below. See the [company-only review](company-only-product-configuration-review.md).

The end-to-end consumer correction requires Catalog migration 0214: historical
adoptions retain resolution version 1; new signed previews and native adoptions
use version 2. The UI verifies this marker before presenting adoption actions.
It remains server controlled, never a user setting. Default-type publication
checks and exact downstream defaults use the same native Company precedence.
See the [consumer review](company-product-configuration-consumer-review.md).

Requested 24 October 2026: plan and implement native product configuration using
the existing CSS, layout, controls, owner APIs and database contracts.

## Phases

1. Verify existing native configuration storage/APIs and harden editor metadata and
   searchable reference pickers where required. Preserve object/field permissions,
   exact decimal strings, idempotency, dated immutable publication, source versions
   and product pins. Regenerate OpenAPI/client contracts and apply any necessary
   matching migrations. Initial database inspection reports Catalog head 0191,
   164 model tables, no missing/extra tables and a clean Alembic comparison; reuse
   the existing configuration tables rather than adding a parallel settings store.
2. Implement company-scoped configuration navigation, scope creation and browsing,
   draft creation/editing, explicit comparison/preview/publication, immutable revision
   history and dated effective settings. Include searchable owner/profile controls,
   validation, permission-aware actions, pending/conflict/retry recovery and draft
   navigation guards. Apply defaults to draft products only through the existing
   signed preview and explicit adoption command. Existing active pins stay intact.
3. Exercise UI/API/BFF contracts, isolated database persistence/concurrency, generated
   contracts and build/type checks. Review desktop/mobile light/dark/ledger flows,
   security and correctness, fix findings, and record evidence and limitations.

## Boundaries

Product configuration governs native options, reusable profile/default references
and numeric suggestions. Identity company capabilities and company display precision
remain separate. Publication changes future defaults, preserves history and does not
activate physical inventory, money/provider workflows or silently update active SKUs.
Tests use isolated databases and fixture browser responses; no live configuration
will be published during verification. Preserve existing local edits and paths.

## Initial findings

- Native COMPANY/TYPE/GROUP/FAMILY/SKU scopes, editable drafts, typed children,
  protected previews, immutable dated revisions and safe draft-SKU adoption exist.
- The console has product fields but no product configuration pages or menu.
- The browser request boundary does not currently admit configuration operations.
- Native field metadata carries authority/layout but lacks typed configuration
  controls and searchable revision references for an accessible editor.
- Catalog database/models/migrations are aligned; no storage change is currently needed.

## Delivery and review

Implemented the three delivery phases. The console route is
`/products/configuration`, linked from Inventory and Company settings using active
company-scoped grants. It includes scope creation/browsing, draft editing, publication
comparison/confirmation, immutable history, effective-setting inspection and explicit
signed draft-SKU adoption. Existing shared controls, CSS, layouts, dialogs, tables and
navigation guards are reused without adding a dependency or a parallel settings store.

Catalog provides typed field control metadata, an aggregate-completeness flag and bounded
searchable owner/profile/revision/currency choices. Underlying master/field read permissions,
company ownership, active parent/publication status and signed cursor admission are checked.
Contract changes were exported to OpenAPI and generated client 0.2.16 with the workspace
lock updated. No database/model or migration changes were needed: the local database and
an isolated fresh native MySQL migration both match Catalog head 0191 and 164 model tables.

Review fixes include:

- Added a failing regression for Python 3.12 type-alias introspection, then restored all
  seven unit-dimension choices. Browser checks use native API metadata, so this gap was
  exercised rather than hidden by a handwritten fixture.
- Refuse incomplete/masked aggregate edits and incomplete copies of protected published
  settings; lock collection replacement and mode choices when dependent fields are protected.
- Retain exact command bodies and idempotency keys after uncertain saves/publication/adoption;
  reviews can be closed and reopened without losing their recovery identity.
- Retain validation/conflict drafts, focus invalid fields, require explicit discard before
  conflict reload, and clear unsaved-change protection before successful navigation.
- Show resolved reference names and explicit unavailable/loading states, preserve decimal
  strings without rounding, use company business dates, and compare before/after publication.
- Corrected an outdated API regression that treated permitted active-product barcode
  maintenance as structural adoption. It now verifies discontinued-product refusal and
  explicitly checks that active structural configuration adoption is still blocked.
- Added a failing masked-lifecycle regression and corrected the draft details status:
  protected status now displays "Not readable" instead of inventing "Published".

Verification evidence is retained under `.tools/product-configuration-review/`. The final
security/simplification review walks CLAUDE.md sections 5 and 6 manually: the slash-command
review tools are not available in this session. No live product configuration was published
and no active SKU, financial history, company capability or user grant was changed.

Final verification:

- API: 36 configuration tests passed, including the 7 editor/reference contract tests.
- Native MySQL: 6 configuration workflows passed after upgrading an isolated database
  through head 0191; comparison with all 164 model tables found no schema drift.
- Browser: 50 checks passed at 1440px and 390px using native field control metadata,
  existing layouts, and light/dark/ledger themes. Responses were isolated fixtures;
  these checks did not publish settings to the application database.
- Console: 1,532 tests passed across 129 test files. The final affected-flow rerun
  passed 39 tests, including the added masked-status regression.
- Production console build, console TypeScript, generated Catalog client consistency,
  Catalog OpenAPI export consistency, Ruff, format checks and strict mypy passed.
- SDK transport: 8 tests passed.
- Local managed Catalog was refreshed and is ready on port 8003. Its served OpenAPI
  includes the reference endpoint, typed controls and aggregate-completeness flag.
- Review database and browser-preview processes were stopped. The original console
  build configuration and existing preview source were restored.

Additional review checks exercise immutable/masked scope history, current-company
response verification, owner-filter navigation, effective service contexts, and
closing/reopening uncertain adoption with an identical command body and key.
No unresolved functional or security finding remains in the reviewed configuration
flows. The full coverage run reports 97.93% statements/lines, 85.50% branches and
81.28% functions, above the recorded pre-task baseline of 97.85%, 85.27% and 80.62%
respectively. The console's existing global 90% function-coverage gate still fails;
its threshold was preserved. Passing functional tests/builds are not a claim that
this existing coverage gate is green.

The separate [master UI inventory](master-ui-inventory.md) records 39 core master
categories without a complete management UI. Profile/reference pickers in this
configuration workflow do not provide those masters' creation/publication lifecycles.
