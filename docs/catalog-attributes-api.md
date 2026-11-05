# Native attribute implementation package (C6.03)

This is the completed API/database milestone after commercial masters. It uses the existing
Catalog command, field-policy, list, option, audit and company-lock mechanisms. It does
not create product/SKU rows or reinterpret descriptive custom fields.

## Delivery sequence

1. Add attribute_definition and attribute_option, each with its model, one DDL revision,
   protected schemas, company constraints and factories. Definitions have stable code/name,
   native value type, optional supported measurement dimension and variant eligibility.
2. Add attribute_set, attribute_set_revision and attribute_set_member. Author a bounded
   draft membership set, validate it atomically, then publish an immutable revision.
3. Add the actual same-company attribute_set_revision foreign key to product_type_revision.
   Only published, applicable templates can be pinned. Existing type revisions preserve
   their current no-template meaning; published revisions are never rewritten.
4. Expose master CRUD/lifecycle, option browsing and set draft/publication APIs. Reuse
   signed keyset pages, native filters/search/sorts and server-side changed-field checks.
5. Review tenant/company isolation, immutability, typed values, uniqueness, parent access,
   publication permissions, audit/receipt rollback and query bounds. Regenerate clients and
   pass coverage/static checks before checking C6.03.

## Native contracts

| Resource | Contract |
|---|---|
| Definition | TEXT, INTEGER, DECIMAL, BOOLEAN or DATE; measurement dimension only on numeric definitions. Code/value semantics become immutable when options or revision members reference them. |
| Option | Definition-scoped stable code/name and exactly one typed value. Decimal remains exact, dates use supported database bounds, numeric measured values name a compatible unit. Store typed values and a canonical equality signature; never identify variants by labels. |
| Attribute set | Company-unique code/name and active lifecycle. Reusable template identity, with no product ownership. |
| Set revision | Increasing revision and optimistic row_version; draft then immutable publication. Publication requires a valid nonempty membership set and active referenced definitions. |
| Member | One definition per revision, explicit requiredness, variant eligibility and display position. Variant eligibility cannot exceed the definition. A member describes allowed use; family_attribute_option remains the later owner of a family's selected axis options. |
| Type binding | Optional published set-revision reference, validated and pinned as part of the product-type requirement revision. Real local FK, no placeholder IDs or remote template CRUD. |

Typed value handling uses shared exact-number/conversion and canonical serialization
primitives. Native domain rules choose equality semantics and reject unsupported values;
there are no tenant expressions, custom-field-dependent calculations or implicit rounding.
Option values remain stable once referenced; retirement preserves history and prevents new
selection. Immutable set membership does not copy mutable labels into the domain identity.

The initial synchronous membership bound is 128 definitions per revision, matching the
existing bounded metadata/write workload. Larger templates require a separately reviewed
job path. The existing hierarchy and list bounds remain unchanged. No automatic Cartesian
variant expansion belongs to this milestone.

Decision 2026-09-12: implement five planned attribute tables plus the incremental type-binding
DDL. Keep item/family values, axis combinations and SKU activation in C7; keep reusable
inventory/warranty/return/handling profiles in C6.06. C6.03 was subsequently reviewed and verified; see the evidence below.

See the [exact method/path/permission/body/query registry](catalog-attribute-routes.md).

## Current API and storage behavior

Signed-off schema is 46 tables/head 0047. C6.03 is complete; the task ledger remains
the completion authority. Master endpoints use the existing company prefix `/v1/companies/{company_id}`.

| Endpoint family | Commands and reads | Permission |
|---|---|---|
| `/attribute-definitions` | POST, paged GET; GET/PATCH `/{id}`; POST `/{id}/activate` or `/deactivate` | attribute_definition.read/manage |
| `/attribute-options` | Same six operations; definition_id filter and protected typed detail | attribute_option.read/manage |
| `/attribute-sets` | Same six operations | attribute_set.read/manage |
| `/attribute-sets/{set_id}/revisions` | POST draft, paged GET; GET `/{revision_id}` | attribute_set.read/manage |
| `.../{revision_id}/members` | GET signed page; PUT complete bounded draft membership with expected_version | attribute_set.read/manage |
| `.../{revision_id}/publish` | POST expected_version; validates all members then freezes revision | attribute_set.publish |
| Product-type revision create/update | Optional attribute_set_revision_id pins a real published revision | product_type.manage/publish |

All writes require an idempotency key, current company authority and applicable changed-field
permission. Master mutations have optimistic versions. Signed INTEGER version exhaustion rejects the
change with 409 before commit; exhausted rows remain readable, and no-op writes stay harmless. Draft membership replacement preserves
retained member IDs and safely supports position swaps; deleted draft members have no published
history. Published members and revisions cannot be edited. Publishing requires permission for
all promoted member requirements. Receipt replay uses current field policies.

Master pages support code/name prefix search, code/name/id sorting, active/code filters and
resource-specific typed filters; options additionally filter by definition and value type.
Revision/member pages use indexed revision/position sorting and typed filters; they reject q
because these identities have no text-search contract. List schemas omit typed option values,
comparison signatures and complete membership documents. Registered option sources support
company- and parent-scoped selection.

INTEGER input/output accepts exact signed 64-bit values; output uses decimal strings to avoid
JavaScript precision loss. DB writes retain native integers. DECIMAL input is exact decimal text
at storage scale 4. TEXT equality uses NFKC, trimming and case folding; labels remain separate.
Measured options require a compatible active unit and its declared canonical conversion. Exact
rational equality detects 1 kg and 1000 g as the same option without rounding. Original entered
value/unit remain stored. Hash/canonical bytes are private equality evidence; a hash collision
fails closed. Unit precision and increments are checked before storage.

Definitions cannot change code/type/dimension once an option/member references them. Active
options or published active templates prevent definition retirement. An active product type
prevents retirement of any pinned template, including a draft type requirement. Reactivation
validates dependencies in both directions. Retiring a definition inside an inactive template
prevents that template being reactivated until its required definitions are active again.

The source registry contains native fields for all five tables. Seven attribute permissions
ship in shared 0.11.0 with corresponding Identity reader/admin role seeds. These tables contain
native attributes, not custom-field business expressions. Item/family option-use constraints are
added with their real C7 references; no absent product table is queried in this milestone.

## Verification (2026-09-12)

Full Catalog: 324 passed/one live-MySQL skip; affected review rerun: 198 passed. Union: 336
distinct passing tests, one skip. Combined coverage 99.70%, domains 100%; changed-module
coverage was cleared before remeasurement. Shared 737/99.30%, Identity 931/five skips,
Audit 90/two skips and Notification 51 pass. Ruff, mypy, generated OpenAPI/TypeScript and
client tests pass. These are code/offline/SQLite checks; live MySQL/broker release gates remain.


## Product attribute authoring review (15 September 2026)

Native attributes now have a Console workflow at `/products/attributes`: find a SKU,
manage reusable definitions/options, declare family specifications and allowed options,
edit draft SKU values, and create one explicit variant at a time. Definitions/options use
Catalog field-set labels and write permissions; product values use the bounded, authorized
`GET /v1/companies/{company_id}/items/{object_id}/attribute-form` graph. The graph includes
resolved definition/option/unit labels, exact saved values, separate family/SKU versions,
default SKU identity, lifecycle and conservative write capabilities. It requires current
read authority over the full replacement graph; a protected field is never silently dropped.

Final review decision (15 September 2026): after a confirmed save, a failed form reload
retains the result so retrying the same action reloads without resending the write.
Unconfirmed writes retain their idempotency key. Definition/option PATCH bodies contain
only changed writable fields; renaming an option does not require reading its protected
typed value. Measured option editors resolve the saved unit label when authorized,
fall back to the readable unit ID if enrichment fails, and honor unit visibility metadata.

Practical example: a shirt family declares Colour and Size as required variant axes, with
Blue/Red and Small/Large allowed options. Explicit SKU creation chooses one combination;
no Cartesian product or automatic stock creation occurs. Material can be an optional text
specification and weight a decimal with a compatible mass unit. False, zero and unset values
remain distinct. INTEGER and DECIMAL values travel as strings; measurement values must
match the declared dimension and the selected unit's quantity grid.

Family attribute PUT is complete replacement of declarations. Omit `default_item_attributes`
to retain default SKU values and version. Include it (even `[]`) to replace those values,
with `expected_default_item_version`; axes still require their complete option combination.
A first axis declaration therefore requires explicit default SKU selections in the same
command. Unchanged SKU value and variant-key rows keep their IDs/versions; changed rows are
updated with audit/version checks, and explicitly removed draft values are retired.

Existing combinations freeze the axis definition set, but allowed options may grow.
Active families accept **additional allowed options only**: declarations, positions,
requiredness, existing allowed options and active SKU values are preserved. They accept new
DRAFT variants and authoring of those drafts. Each SKU must independently pass configuration,
pricing/tax/inventory and activation checks. ACTIVE SKU attribute edits remain forbidden.
Definition/option semantic changes and retirement retain the existing dependency guards.

Readiness revalidates saved value types, declared membership, permitted option selections,
measurement dimensions/grids and template requirements instead of counting value rows only.
Cross-company references, denied field reads/writes, stale versions and duplicate variant
combinations fail transactionally. Idempotency and company locking cover the entire command.

Migration **0131** replaces the native SKU scalar check in one ALTER statement so measured
INTEGER values match the existing schema/domain contract. Apply it before using that path
in an existing database. Downgrade is deliberately refused: measured integer data must be
explicitly reconciled before reinstating the older check. No database is migrated by UI/API
startup. Tests and review evidence are tracked in `product-configuration-todo.md` and
`.test_artifacts/product-attributes-fixes-20260915/`.
