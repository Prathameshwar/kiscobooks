# Extension master delivery

User-approved sequence, 2026-10-27: implement the eight extension masters one at a
time, completing their contracts, UI and verification with the existing shared
design system. Authoring/publication does not enable financial or stock execution.

## Per-master phases

1. Write failing contract/domain/scope regressions. Complete native models and
   one-DDL migrations, schemas, field metadata, permissions/seeds and source
   integration using the existing command/list/audit/idempotency mechanisms.
2. Generate OpenAPI and clients. Add directory/detail/create/edit/revision/review
   screens, permission/config-aware Masters cards and a closed browser proxy.
   Reuse shared CSS, page/section headers, form cards, grids, action footers and
   existing error/discard/retry behavior.
3. Verify domain/API boundaries, tenant/company/field authority, exact numbers,
   immutable publications, concurrent edits, retries, native schema parity and
   responsive browser flows. Record actual readiness and remaining deployment
   prerequisites before moving to the next master.

## Sequence and status

| Order | Master | Status |
|---|---|---|
| 1 | Manufacturing operations | Complete: native API/UI/source and real-login verification |
| 2 | Sequential manufacturing routes | Complete: native API/UI and real-login verification |
| 3 | Single-level BOM, multiple outputs and dated assignments | API/UI and live flow verified; final reviews remain |
| 4 | Promotion stacking policies | Native API/UI and tenant3 browser verification complete; final reviews remain |
| 5 | Promotion limit definitions | Native domain/storage/API verified; metadata/UI and deployment in progress |
| 6 | Campaigns | Pending |
| 7 | Promotions/schemes, supported same-item subset first | Pending |
| 8 | Coupon program definitions | Pending |

Operations/routes/BOM follow catalog-manufacturing-design.md and the selected
single-level Phase 6 baseline. Multi-level expansion, substitutions and execution
remain unavailable. Promotions follow catalog-promotions.md; unsupported mechanics,
coupon issuance/redemption and live counter consumption must fail closed.

## Deployment prerequisite

Catalog currently lacks a current signed Identity source context. Never bypass
its lease, tenant scope or field policy checks. The company enrollment choice
was confirmed by the user: automatically enroll authorised companies. Implement
an explicit enrollment record in the company transaction, authenticated bounded
discovery, enrolled-scope checks on snapshots/actor proofs and managed source
publisher/consumer startup. Existing deployment-managed scopes stay supported.

No new service or datastore is introduced. This document records implementation
authorization, not evidence that the masters or their execution consumers are ready.

## Next slice: sequential routes

Reuse the operation directory/revision shell and the existing native aggregate-child pattern
used by return-policy conditions. Add route identity, immutable route revisions and native
ordered steps (three one-DDL revisions), route read/manage/publish keys, field metadata,
contracts and generated clients. Drafts may be empty; publication requires 1–50 sequential
steps with contiguous positions and published, nonretired operations from the current company.
Each step pins its operation revision; a route never follows a mutable latest operation.

Steps capture exact DECIMAL(19,4) nonnegative setup/run/lead-time minutes, a positive quantity
basis and PER_OUTPUT_UNIT/PER_BATCH time basis. The quantity basis expresses output units or
the declared batch size respectively; later BOM adoption must bind the output-unit contract.
No route time or service reference calculates wages, charges, scheduling or execution.
Edits replace the complete reviewed draft step set under the aggregate version/graph lock;
native stable step IDs and pinned published content remain reproducible. Published content
is immutable; retirement affects new selection while preserving historical references.

UI: shared header/specification/reason form, ordered step cards, searchable operation-revision
selectors, exact-number text inputs, add/remove/reorder controls, attached actions and explicit
publication review. Protect reference hydration as well as selection, preserve inaccessible
stored values, and never submit a partial paged child set. Verification covers scope/field
denials, invalid or retired references, incomplete collections, replay/concurrency, native
schema parity, keyboard interaction and real tenant login. Route authoring is another
preparatory definition slice; the full BOM capability/configuration gate remains separate.


## First master evidence (2026-10-27)

Manufacturing operations now have company-scoped directory/detail/create/edit and draft/review/
publish/retire screens using the existing shared components and CSS. Native definitions,
field metadata, closed proxy, dedicated role keys, generated clients, idempotency and audit
are synchronized. Active service options are constrained to company-owned SERVICE SKUs.

- Catalog targeted operation/profile metadata: 17 passed, including operation write-policy
  rollback, replay, status filter protection, tenant/company scope and immutable publication.
- Console operation/profile/request policy: 80 passed across the verified runs; TypeScript passed.
- Catalog source client/worker/enrollment: 17 passed across the verified runs. Identity enrollment/owner/audit: 18 passed.
- Identity migration/enrollment regression run: 707 passed, 4 container-only skips. Its typed
  add-column parser was corrected to include already-existing revision 0087 in model parity.
- Native MySQL 9.6: both new migration chains passed isolated upgrade/downgrade/re-upgrade and
  model comparison, then local upgrades. Full sync checks report Identity 0088 / 56 tables and
  Catalog 0193 / 166 tables, with no missing/extra tables or native differences; Alembic checks pass.
- Real tenant3 login: operation creation, draft, publication, locked published content and
  retirement passed. Desktop/mobile widths in light/dark/ledger have no horizontal overflow;
  screenshots reviewed and no browser errors observed. The verification operation remains
  retired with its audit history in KHE, rather than deleting referenced evidence.

Automatic enrollment is configured locally, the two existing active companies are enrolled,
and their current snapshots are delivered by managed publisher/consumer workers. Normal role
seeding added three company-admin keys and one auditor key without widening assignment scopes.
New company readiness still depends on the next successful signed discovery/snapshot refresh.
No manufacturing execution, stock, financial or BOM readiness is claimed.

Manual simplification/security review found and corrected platform audit routing for global
discovery; the native outbox and audit-service read confirm all enrollment/discovery events were
delivered with real tenant scope. Current company/tenant/enrollment checks, signed paging bounds,
closed proxy actions, replay authority and published immutability were reviewed. No remaining
finding is identified in this slice. Named /simplify and /security-review commands are unavailable
in this environment; their checks were performed manually.


Fresh-company verification: tenant3 created `Catalog enrollment verification` through the normal
Identity browser proxy (201). Its native manufacturing-operations read through the correct
product-fields proxy returned 200 with an empty directory. No deployment setting was edited and
no service was restarted after that creation. The company is retained as a nonfinancial test
company; full fiscal/warehouse setup is outside this specific enrollment check. The earlier
browser polling attempt used the company-setup proxy, which correctly rejected a master-directory
request; verification was corrected to use the same closed proxy as the real master screen.

Additional source/profile regression coverage: nine existing product-configuration/profile/audit
contract tests passed. The operation selector and protected publication-status UI tests also pass.


## Sequential route evidence (2026-10-27)

Route identities, draft/review/history/publication/retirement and native ordered steps reuse
shared profile screens, cards, field grids, lookups, menus and action footers. Step references
pin operation revisions. Complete-set checks, exact time/basis strings, field policy, authority
rechecks on retries, scope, immutable publications and historical reference hydration are enforced.
The lookup retains its selected label while the exact reference loads, with bounded company-scoped
choice caching. The reference remains a safe ordinary link to its pinned operation revision.

- Six route API tests pass, including exact values, stable IDs during reorder, immutable/retired
  history, invalid input/empty publication, child-policy rollback and cross-tenant reference denial.
- Shared operation/profile/route/request-policy UI run: 99 passed; added lookup-label regression
  passes (route UI now six tests). The subsequent operation/route/profile-page run passed 39 tests.
- Identity role/company-creator regression: 17 passed. New fixed role seed adds three route keys
  for company administrators and read for tenant auditors, preserving assignment scopes.
- MySQL 9.6: isolated upgrade/downgrade/re-upgrade/model comparison passed. Local Catalog is at
  0196 with 169 tables; full native sync and Alembic checks report no drift or missing/extra tables.
- Real tenant3 browser flow passed creating and publishing the referenced operation, creating a
  two-step route, reordering it, preserving exact values, publishing, checking locked inputs,
  retirement and historical hydration after operation retirement. Six responsive theme/width
  combinations have no page/panel overflow. Screenshots were reviewed; no browser errors occurred.
  Verification operation and route revisions remain retired with their evidence in KHE.

Manual simplification/security review retains native child tables rather than a rule bag,
checks field authority before reference lookup, verifies complete collections before replacement,
and uses current scoped locks for reference eligibility. No unresolved finding is identified.
The full BOM capability, estimates and manufacturing execution remain unavailable.

## Next slice: single-level BOM authoring and dated definition selection

Use six native models: BOM identity, versioned typed draft, immutable published revision,
native component/output rows, and dated assignment. Drafts and publications have separate,
scoped native child rows rather than stored authoring JSON. Publication copies children atomically and
retains a generated dependency manifest/hash with exact SKU/unit/tracking/route evidence. A
deferred draft/publication foreign key gets its own reversible DDL revision. Preserve stable
line keys across same-BOM drafts/publications, with separate immutable row IDs per publication.

Reuse domain/bom_requirements.py for exact, non-posting quantity preview. Support STOCK_INPUT
components, variable-per-basis/fixed-per-run quantities, explicit run counts, yield/loss and one
primary plus distinct secondary output SKUs. Add explicit optional batch min/max/multiple rules;
preview requires a matching explicit run breakdown when batch constraints apply. Reject implicit
rounding, measured-unit estimation, services/nonstock physical rows, repeated output SKUs,
input/output self-consumption, child/phantom expansion and substitutions. Repeated input SKUs
retain distinct line keys. Validate exact SKU-specific fixed unit revisions and quantity grids;
serialized base quantities must remain whole. Preserve pinned route and optional step identity.

The new bom_definitions company feature defaults OFF and requires inventory. It gates new
authoring, publication, assignment and preview; permission-protected published history remains
readable after disablement. Company administrators receive bom.read/manage/publish/assign;
tenant auditors receive read. Use current signed Identity feature state and the existing company
policy lock, field policies, idempotency, native keyset lists and transactional audit throughout.

Assignments use a published nonretired revision's exact primary output and optional production
warehouse, inclusive business-date intervals, a generated company/warehouse scope key and an
active uniqueness slot. Reject overlaps under the company lock; exact warehouse wins over the
company-wide default. Return definition selection only, explicitly with operational_ready=false.
No stock availability, reservation, actual manufacturing, cost posting or consumer acknowledgement
is inferred from authoring/selection. Further configuration/release/estimation work stays gated.

UI reuses existing directory/form/section/card/lookup/review/history patterns, with typed component
and output editors, full-set verification before replacement, exact-number strings, assignment
forms and a clearly labelled non-posting preview. Hide the BOM card when company applicability
is known to be off; show a useful retry/configuration state when that context is unavailable.


## BOM verification (2026-10-27)

Six normalized models, seven one-DDL migrations (0197-0203), typed contracts and the Console
recipe/assignment screens are implemented. Catalog field checks, current signed source authority,
company locks, exact physical grids, immutable publications, idempotent retries and transactional
audit apply. Permissions, feature defaults, role seed, OpenAPI and generated clients are synchronized.

The tenant3 browser flow in `Catalog enrollment verification` created a BOM, entered pinned input
and output SKU units, previewed 30 finished pieces as 60 required input pieces, published, confirmed
immutable content, assigned the recipe, withdrew applicability and retired the publication. History
remains readable. Six desktop/mobile theme checks passed; screenshots reviewed and no browser errors.
The live flow found a descending-sort mismatch in history/assignment lists; a failing API regression
was added and the native allowlists corrected. The completed flow was then verified again.

Current focused checks: 19 BOM API/storage/domain tests passed before the additional sorting case;
the later BOM API plus stack-storage run passed 7 tests, and the sort regression separately passed.
Console BOM/request/card checks passed 41 tests and TypeScript. Domain branch/statement coverage is
100% for the new pure batch/physical-grid module. Native MySQL round-trip/model parity passed, and
Catalog is now at 0206/178 tables including the next slice's three stack-draft tables.
Named simplification/security tools remain unavailable. Both requested final review-and-fix passes
are still pending across the completed delivery. No execution, costing or reservation is enabled.


## Stacking policy verification (2026-10-27)

Catalog 0204-0206 adds three normalized draft tables to the existing immutable published policy,
group and pair facts. Draft edits retain group identity and replace only complete reviewed sets;
publication remaps groups atomically into immutable native policy facts. Native stage ordering,
forward pairs, no implicit stacking, bounded counts and incomparable-basket guards apply. All
reads and writes use current source/company/field authority, company locking, idempotency and audit.
A shared AggregateWork now supplies existing BOM and stack field checks/evidence without copying
the mechanism. BOM API regressions remained green after extraction.

The tenant3 live flow created three ordered groups, reordered product groups, explicitly allowed
a later manual combination, saved, reviewed, published and confirmed locked content. Six theme /
viewport combinations passed without overflow or browser errors. The normal role seed added four
keys without altering assignment scopes. Sales promotion definitions are enabled only in the
verification company. The feature does not authorize sale application, holds or redemption.

Native MySQL round-trip/parity and local 0206 deployment passed. Stack API/migration run: 9 passed,
1 container-only skip. Console stack/route/proxy tests: 15 passed; the later card-inclusive run:
35 passed before the extra version guard case. TypeScript, targeted Ruff and strict mypy pass.
Shared feature/permission catalogue checks: 29 + 34 passed; Identity feature/role checks: 52 passed.
The browser-discovered BOM sort fix, stack child-delete ordering, missing explicit readiness
serialization and malformed concurrency receipt were corrected with regression coverage.

## Next slice: native promotion limit definitions

Use stable company/code/name identities and immutable published cap revisions. Preserve stable
scope/metric/period/timezone/currency/unit identity so a new cap revision cannot reset a quota or
change what prior usage means. Count caps retain signed-64-bit exactness as strings on the wire;
reward quantities and budget caps use DECIMAL(19,4), with their native unit/currency references.
Declare campaign, promotion or program binding scope; future owner-specific native binding tables
reference these exact published revisions. No generic nullable owner key or executable rule JSON.

Reuse the native master header pipeline and shared aggregate command/field/audit mechanisms.
Draft/review/publish history is permission- and feature-gated. Limit publication is a requested
commercial definition and always reports operational_ready=false; no applied live cap or quota
acknowledgement is claimed. Consumer admission, counters, holds, suspension and redemption remain
outside this authoring delivery. Both requested final review-and-fix passes remain pending.


## Interleaved Books navigation request (2026-10-27)

Books is a sibling of Reports under Books and Reports. Ten native books/registers/ledgers have
company-scoped submenu destinations and disabled card landing pages. The same catalogue renderer
serves Books and Reports. Direct name/code matches take priority over section-name fallback.
69 affected tests and TypeScript passed. Fresh tenant3 browser verification checked all ten
submenus, selected states, search and six responsive theme combinations without errors/overflow.
This request is complete locally; the remaining extension masters and both final reviews continue.
