# Native reusable profiles implementation package (C6.06)

This follows C6.03 and stays within the agreed Catalog API/database scope. It defines reusable
requirements and immutable attachments. Billing continues to own physical units, warranty claims,
returns, stock allocation, valuation execution and manufacturing transactions.

## Delivery order

1. Identifier profiles and requirements: two planned tables and a bounded aggregate API.
   Review this working slice before adopting its references in inventory templates.
2. Inventory profile template identity and immutable revisions: two planned tables.
   Review tracking, expiry, identifier and requested valuation compatibility before continuing.
3. Warranty identities/revisions, return identities/revisions/conditions, handling identities/
   revisions: seven planned tables. Each workflow ships with API/schema/model/migration/tests,
   and receives a separate review before the next policy family.
4. Add real same-company profile references to product-type requirement revisions where applicable.
   Product Configuration and item attachments adopt these actual revisions in their later phases.
5. Reuse current command/list/option/field/audit mechanisms; add scoped permissions and role seeds,
   regenerate clients, review and verify before checking C6.06.

## Native design

| Profile | Supported contract | Key checks |
|---|---|---|
| Identifier | SERIAL and IMEI requirement types; declared COMPANY or MANUFACTURER_SKU namespace, bounded min/max counts, required slots, code-owned normalization version | One requirement per type; IMEI uses company uniqueness and explicit slot cardinality; physical values remain Billing-owned. Requirement structure is immutable once created, so changing it creates a new profile identity. Name/lifecycle remain governed master fields. |
| Inventory template | Lot/serial flags, optional identifier profile, expiry/manufacture-date requiredness, shelf-life/minimum remaining days, FIFO/FEFO issue strategy, requested FIFO/MOVING_AVERAGE/SPECIFIC valuation | Goods stock only; expiry requires lots, FEFO requires expiry, identifiers/specific costing require serialized units. Dates/quantities/costs are not stored on a template. |
| Warranty policy | Bounded positive duration in DAYS/MONTHS/YEARS; explicit SALE/DELIVERY/INSTALLATION trigger; supported coverage description | Immutable published revision; service duration is valid without introducing physical inventory. Trigger evidence and claim execution belong to their owner workflows. |
| Return policy | Explicit allowed/forbidden returns, bounded return-window days, native condition rows | One occurrence of each supported condition; no arbitrary refund formula. Disposition requests remain subject to Billing capability/authorization. |
| Handling profile | Exact optional temperature minimum/maximum with explicit Celsius unit, fragile/keep-dry/keep-upright native flags and bounded descriptive instructions | Ordered exact bounds, scale 4, no custom expressions; ordinary requirements do not claim hazardous-material or cold-chain compliance execution. |

Master identities use company-unique stable code/name, row_version and active lifecycle.
Revision parents allocate bounded increasing revision numbers under the company policy lock;
drafts can be edited, publication validates the whole aggregate, published content is immutable.
Retirement preserves references and rejects active dependents. Reactivation validates every
relevant dependency. Lists use signed keyset paging, typed filters, indexed search where a text
field exists, stable sorting and lean protected projections. Aggregate child arrays are bounded;
child browse APIs remain paginated. Commands, receipts and company audit commit atomically.

The identifier header is itself a versioned requirement identity: its code-owned normalization
version and requirements are frozen at creation. This uses the existing planned two-table model
without inventing a mutable published profile or an unplanned generic revision store. A changed
requirement receives a new profile ID and explicit adoption; existing physical units keep their
original profile reference.

Catalog may author a requested valuation/return/identifier requirement while its operational
consumer is unavailable. This is definition authoring only; enabling it for products or posting
requires the actual consumer/source readiness and acknowledgement defined in C5/C7. No mocked
consumer, seeded cost or invented physical device satisfies that gate.

## Reference checks

GSMA distinguishes a 15-digit IMEI, whose final digit is a check digit, from the 16-digit IMEISV.
The initial requirement registry offers IMEI explicitly, without accepting IMEISV as an alias.
[GSMA device identifier specification](https://open-gateway.gsma.com/docs/device-identifier/api-reference).
TallyPrime offers item-specific costing methods. This platform retains the already agreed
explicit FIFO/moving-average/specific-identification consumer contract and keeps issue selection
separate from valuation. [TallyPrime stock valuation](https://help.tallysolutions.com/stock-valuation-methods-tallyprime/).

Decision 2026-09-12: this is the agreed work package; implementation evidence follows below.
Native closed enum registries define supported semantics; unimplemented specialist workflows
remain outside these profile APIs. Existing agreed ownership and precision rules remain intact.

## Identifier slice: current working implementation

Two tables are implemented in 0048/0049, taking the working schema to 48 tables/head 0049.
`/identifier-profiles` offers POST/list, GET/PATCH by ID, and activate/deactivate commands.
The [endpoint registry](catalog-identifier-routes.md) lists all seven exact operations.
`/identifier-profiles/{id}/requirements` is a protected signed page, with identifier_type and
namespace_rule filters and identifier_type/id sorting. It rejects text search. Header pages
reuse indexed code/name prefix search and stable sorting. The standard option-source endpoint
registers catalog.identifier_profiles. All commands use current company scope, field policies,
expected versions where applicable, idempotent receipts and same-transaction company audit.

Creation supplies one or two distinct requirement types. Each has min_count 0..8, max_count
1..8 and explicit requires_slot; multiple values require slots. IMEI requires COMPANY namespace.
Header normalization_version is server-owned 1. Requirement structure is immutable after creation;
changes need a new profile identity. Requirement field denies protect creation and replay, even
when the header write is permitted. Physical identifier arrays are rejected as unknown input.
Conditional write rules are evaluated against the immutable requirement rows on both creation
and replay. A valid receipt cannot mask missing restored requirements or a newly matching deny.

Normalization contract 1 must be implemented by the physical-identifier owner before consumer
acknowledgement: SERIAL uses trimmed NFKC text with case preserved and the declared company or
manufacturer/SKU namespace; IMEI uses a trimmed 15-digit ASCII string with its check digit,
company uniqueness and retained leading zeroes. Original submitted evidence is retained only by
the owner under its access rules. Catalog stores no physical SERIAL/IMEI value or allocator.

Identifier API/database/permission review is complete. Catalog verification records 349 distinct
passing tests, one live-MySQL skip, 99.70% overall and 100% domain coverage. The five profile-rule
tests are included. Conditional authorization and rollback defects were reproduced before fixes;
the stale native-model test fixture was corrected and rechecked. C6.06 remains incomplete for
inventory, warranty, return, handling and product-type bindings. All five locks/environments use
shared 0.12.0; shared and existing-service regressions, Ruff, strict mypy and generated clients pass.


## Inventory slice: reviewed implementation

Two model/migration pairs in 0050/0051 take the working schema to 50 tables/head 0051.
[Eleven exact operations](catalog-inventory-template-routes.md) provide master maintenance,
draft revision creation/PATCH, immutable publication and protected history. Requirements use
native flags, exact integer day limits, FIFO/FEFO issue choice and a separately requested
FIFO/MOVING_AVERAGE/SPECIFIC valuation method. Defaults have tracking/date flags off, no day
or identifier constraint, and FIFO strategies. These are template defaults, not physical-stock
feature enablement. Inventory templates apply to stock goods when later product bindings land.

Database checks mirror date/tracking/count/strategy coherence. Revision references are real
same-company FKs. An identifier can retire while only drafts reference it; publication requires
it to be valid and active. Published revisions of an active template prevent identifier
retirement. Template reactivation checks its published identifier dependencies, including the
presence of immutable requirements. A failing recovery regression reproduced and fixed an
otherwise successful reactivation after incomplete restored data. Rejected writes roll back
resource, revision, receipt and audit effects together.

Two-tenant tests cover both new tables; storage and workflow tests cover scoped references,
constraints, immutable history, revoked/conditional field authority, lean lists, filtering,
paging, sorting, explicit-null versus omission and dependency lifecycle. Full Catalog verification records 357 distinct passes, one live-MySQL skip, 99.71% overall
and 100% domain coverage. Ruff, strict mypy and generated-client checks pass.
Seven warranty/return/handling tables and the real product-type bindings remain in C6.06.


## Warranty slice: implementation and review

Two reviewed model/migration pairs in 0052/0053 take the working schema to 52 tables/head 0053.
[Eleven exact operations](catalog-warranty-routes.md) cover master maintenance and immutable
revision publication. Supported durations remain native calendar units with explicit start
triggers. Informational coverage text is bounded, nullable and excluded from list payloads.
Draft updates validate merged values; publishing checks current write authority on the entire
material definition. Database constraints enforce duration/unit coherence, trigger vocabulary,
scoped parent references, revision uniqueness and positive versions.

Review reproduced HTTP 500 for warranty option browsing: the source registry lacked its
query-model counterpart. The mapping is fixed and the workflow regression passes. All five
warranty API/storage tests pass, including all eleven routes' authentication/scope boundaries,
conditional/revoked field-policy checks, atomic rollback and two-tenant isolation. Existing
inventory regressions and offline migration checks pass. Ruff, strict mypy (147 files), OpenAPI,
generated clients and both transport tests pass. Full Catalog verification: 362 passes, one live-MySQL skip, 99.72% overall and 100%
domain coverage (780.22s). No live MySQL result is claimed.
Return/handling definitions and actual product-type profile bindings remain in C6.06.


## Return aggregate implementation notes

The next slice uses return_policy, return_policy_revision and return_policy_condition. A revision
stores returns_allowed and native window_days; enabled returns require a window (0 means the
trigger business date only), while disabled returns require a null window and no conditions.
At most five distinct supported conditions are edited atomically through the draft revision.
Condition rows retain stable IDs when unchanged. Their browse endpoint remains a protected
signed page, with fixed condition_code filters and stable condition_code/id sorting.

Decision 2026-09-12: add a server-maintained condition_count (0..5) to the revision and verify it
against bounded condition rows before editing, publishing or binding. This distinguishes a
valid empty policy from an incomplete restore that silently lost required conditions. SQL checks
must explicitly require a non-null enabled return window; SQL UNKNOWN must not satisfy this
invariant accidentally. The count is native metadata, never a client-supplied field or refund rule.
Child field checks use the existing transaction-local before/after snapshots; retained receipts
re-evaluate current policy conservatively because a draft condition may later be removed.


## Return slice: reviewed implementation

Three paired migrations (0054/0055/0056) add return identities, revisions and native conditions;
the working schema is 55 tables/head 0056. [Twelve exact operations](catalog-return-routes.md)
provide draft aggregate edits, immutable publication, protected history and child browsing.
Same-transaction field checks apply to added/removed conditions and publication, including fresh
conditional authorization and conservative retained-receipt policy. Partial restore checks reject
missing condition rows rather than silently weakening the selected policy.

The initial targeted suite passes: 23 tests, one live-MySQL skip, including unchanged inventory
and warranty regressions. Strict mypy exposed a heterogeneous SQLAlchemy test-row narrowing
issue; explicit per-row narrowing fixes it while checking every row's tenant/company. Ruff,
strict mypy (157 files), OpenAPI/client generation, TypeScript and both transport tests pass.
The manual authorization/atomicity/schema review found no new functional or security defect.
Changed-module verification records 197 passes/one live-MySQL skip, after purging old
measurements for all twelve changed modules. Combined: 369 distinct passes, 99.74% overall
and 100% domain coverage; no stale source-line data is reused. Handling and actual product-type profile bindings remain in C6.06.

Decision 2026-09-12: clarify return tables as eligibility definitions. Physical return dispositions
and refund execution remain Billing-owned, consistent with the agreed service boundary.


## Handling and product-type bindings: reviewed implementation

Handling adds two model/migration pairs (0057/0058); 0059 adds four nullable, indexed,
same-company foreign keys to ProductTypeRevision. Working schema: 57 tables/head 0059.
[Eleven handling operations](catalog-handling-routes.md) reuse existing master/history/field/
option/receipt/audit mechanisms. Handling bounds, units and flags are native; instructions
remain descriptive. The product-type detail/input/PATCH contracts now expose:

| Field | Target | Adoption checks |
|---|---|---|
| inventory_template_revision_id | inventory_profile_template_revision | Active published parent; complete supported identifier requirements; goods-only type admitting STOCK and the actual template tracking mode; mandatory expiry cannot be weakened |
| warranty_revision_id | warranty_policy_revision | Active published parent and native bounded duration/trigger; valid for goods or services |
| return_policy_revision_id | return_policy_revision | Active published parent, complete condition_count and valid native return eligibility rules; valid for goods or services |
| handling_revision_id | handling_profile_revision | Active published parent, valid exact temperature/flag requirements and goods-only type |

These join the existing attribute_set_revision_id. Lean revision pages omit all detail-only
binding columns. Omitted PATCH values retain references; explicit null clears optional defaults.
Creation, edit and publication validate the complete definition. Native field denies apply to
actual changed bindings and all material fields at publication; old receipts recheck current
permissions. Default references do not enable a company capability or activate a product.

Active product types, including their drafts, prevent referenced profile retirement. Retiring
a type permits profile retirement without rewriting history. Reactivating a type rechecks all
references using bounded existence queries, including return-condition completeness and active
supported identifier requirements. Return policy reactivation also checks completeness: a failing
recovery test reproduced a previously successful activation after a published condition was lost.
The fix rejects it until the missing native member has been restored.

Decision 2026-09-12: physical type defaults are GOODS-only. SERVICE and BOTH can carry warranty/
return definitions but cannot silently inherit stock or handling defaults. Compatibility means
the type admits the template's actual mode; the later selected SKU/unit must still independently
satisfy all constraints. Definition binding is distinct from C7 activation/C5 acknowledgement.
Future Product Configuration scopes reuse these actual immutable targets, without duplicate rules.

The handling audit registry reached 105 events and exposed an inherited 100-route limit in the
shared publisher, outbox selection and consumer queue binding. Shared 0.14.0 supports up to 1,024
exact contracts while batches/prefetch remain capped at 100. Six new regression cases failed
before the fix. The affected 48-test suite and full 751-test platform suite pass (99.30% overall).
Identity publisher (1), Audit ingest/consumer (10) and Notification consumer/projection (7) tests
pass. All five locks/environments are synchronized, preserving concurrent shared 0.13.0 changes.

Handling/publisher checks: eight passes. Binding API/storage/policy/recovery and domain checks
pass after correcting test fixtures to the existing route/null/metadata contracts. Ruff, strict
mypy (172 files), OpenAPI/client generation, TypeScript and two client transport tests pass.
C6.06 is reviewed and checked. Baseline suite: 398 passed and one live-MySQL skip. The final history-module run: 62 passed. Combined evidence: 404 distinct passing cases, 99.75% overall coverage and 100% domain/history-module coverage. All old history-module measurements were purged before merging the final-source run; 101 other source fingerprints match the baseline. The baseline run is not described as a full-suite execution on the final history module.
Live MySQL, RabbitMQ and actual Billing integration remain open.


Authorization follow-up: native field checks now precede product-type profile/template lookup.
Five failing regressions reproduced a reference-availability oracle in denied binding fields;
the fix passes all eleven targeted policy/attribute checks. Baseline full-suite evidence and
separately remeasured fixed-history coverage are combined only after purging old history-module
data. A further conditional row-version regression also failed before correction; all ten
profile-policy tests then passed. The final measurement includes this fix. See the milestone
review for exact evidence; C6.06 is complete, while the broader C6 phase remains open.

## Serial and IMEI definition review (2026-10-12)

Catalog's identifier profile defines required SERIAL and IMEI slots; the published inventory
template selects that profile, and item activation pins it in `item_inventory_profile`.
Effective item facts now return `inventory.identifier_profile_id` alongside tracking flags so
clients can discover the actual selected definition even when the optional configuration-level
profile override is unset. A profile pinned by an activated item cannot be deactivated merely
because its inventory template has since been retired.

These are definition and lifecycle guarantees only. Physical serial/IMEI values, uniqueness,
custody, and voucher/stock movement enforcement still require the planned stock execution
owner. `stock_execution.state` remains `UNAVAILABLE` until that owner is implemented and
verified; clients must not treat an active identifier definition as executable stock tracking.
