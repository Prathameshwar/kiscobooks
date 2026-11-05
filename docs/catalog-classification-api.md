# Catalog classification API and database

Status: classification and scheme governance implemented; latest corrections dated 14 September 2026.
Scope is Catalog definitions and membership maintenance.

## Tables and invariants

| Table | Purpose |
|---|---|
| catalog_policy_state | Unique tenant/company generation and lock; serializes hierarchy edits and invalidates previously reviewed generations when descendants change. |
| item_group | Operational group/subgroup definition, allowed GOODS/SERVICE/BOTH kind, custom values and optimistic row version. |
| item_group_parent | Inclusive dated parent/root intervals, retaining original relationships. Same-company composite references; no overlapping parents, cycles, missing ancestor intervals or depth above eight. |
| category_scheme | Independent merchandising axis; SINGLE/MULTIPLE cardinality and native `is_required` membership policy. |
| family_category | Inclusive dated product-family membership, retaining closed and scheduled assignments. |
| item_category | Category tree inside one company and scheme; composite parent references prohibit cross-scheme parents. |

Migrations 0028-0032 each contain one CREATE and one DROP; no seed DML. Matching ORM,
input/detail/list schemas and two-tenant/foreign-key tests accompany the migrations.
Group dates use the documented MySQL DATE range beginning 1000-01-01. The General root
uses that boundary; earlier engine-dependent dates are rejected before SQL. See the
[MySQL date contract](https://dev.mysql.com/doc/refman/26.7/en/date-and-time-type-syntax.html).

## Routes

All paths start `/v1/companies/{company_id}`. Commands require Idempotency-Key; updates
and lifecycle actions require expected_version. Create returns 201 and Location; replay
reauthorizes against current Identity subjects/policies and returns current protected detail.

| Resource | Operations |
|---|---|
| /item-groups | POST create; GET list |
| /item-groups/{id} | GET detail; PATCH descriptive/kind/custom changes |
| /item-groups/{id}/activate or /deactivate | POST lifecycle with optimistic version |
| /item-groups/{id}/reparent | POST dated reparent with expected_version, expected_generation, parent_group_id and effective_from |
| /item-groups/{id}/parents | GET protected, paged history with valid_at and stable date/id sorting |
| /item-groups/{id}/children | GET one paged tree level at required valid_at; search/filter/sort and a parent-bound cursor |
| /category-schemes | POST create; GET list |
| /category-schemes/{id} | GET detail; PATCH labels/membership mode |
| /category-schemes/{id}/activate or /deactivate | POST lifecycle |
| /item-categories | POST create; GET list |
| /item-categories/{id} | GET detail; PATCH labels/custom values |
| /item-categories/{id}/activate or /deactivate | POST lifecycle |
| /item-categories/{id}/reparent | POST parent change with expected_version and expected_generation |

Separate resource permissions are item_group.read/manage/move,
category_scheme.read/manage and item_category.read/manage/move. Identity group permissions
never authorize these resources. CompanyAdmin gets commands and existing Catalog readers
get reads through the versioned Identity role seed. Shared package version 0.7.0 is locked
in all five consuming environments.

Master lists default to 50, cap at 200, use signed keyset cursors, code/name prefix search,
code/name/id sorts in either direction and typed resource filters. Group filters include
allowed_kind; schemes include membership_mode; categories include scheme_id/parent_id.
Custom JSON is omitted from lean lists. Field read-denies also prohibit filtering, searching
or sorting by the denied field. History supports date filters rather than text search. Child browsing uses EXISTS to avoid duplicate rows, requires readable relationship/date fields and binds cursors to the requested parent.
Repeated/unknown query parameters and unsupported sort fields are errors.

Reparenting appends a new interval after the latest interval start, closing its predecessor
at the previous date. It cannot rewrite old/future intervals or backdate before the current
company-local date. The transaction checks every affected dated graph state. Category moves
validate the complete bounded scheme tree. Synchronous validation permits at most 10,000
nodes/edges and 100,000 path checks; larger reviewed-job support remains in the job phase.
Referenced classification identities remain protected; General always remains an active BOTH
root. Scheme policy changes use the reviewed transition below. Category retirement permits
retained closed memberships, while active children and current/future memberships block it.

## Custom fields and defaults

Groups and categories reuse authoritative Identity definitions, layout, native descriptors,
field policies, exact typed validation, immutable values and transactional sequences.
Custom values never choose product kind, tax, price or stock behavior. Typed boolean/list/
currency defaults are decoded; unknown option settings fail closed; disabled feature-backed
company overrides remain disabled rather than exposing tenant defaults. Effective layout
requiredness reaches write validation. Protected custom values are omitted from detail/error
output. Numeric/sequence changes share the owning transaction and audit.

Non-unique searchable custom fields now use prepared index generations and typed filters;
see [index rebuild API](catalog-index-rebuild-api.md). Unique-field adoption remains gated.
Registered dynamic-option sources are implemented; see [metadata/options](catalog-field-metadata-options.md).

General is separately seeded through the same authorized API:
`python -m catalog.seeds.classification --base-url https://catalog.example --company UUID`.
The command accepts a bounded JSON stdin object containing current gateway Authorization
or signed actor headers, plus optional custom_fields. It never creates credentials. It uses
ordinary list/create authorization, source freshness, custom-field validation, idempotency
and audit. Reruns preserve existing names/custom values; no schema migration seeds a tenant.
`seeds/catalog` is the matching repository entrypoint. Seed failures are reported without
printing credentials or response bodies.

## Remaining integration gates

Product memberships/cardinality, configuration inheritance, pricing and Product Tax are
implemented by their native APIs. Categories remain merchandising axes and do not inherit
tax or price rules. Unique-field adoption and downstream transaction enforcement retain
their separate integration contracts. Current hierarchy APIs govern Catalog definitions only. Live MySQL concurrency
and RabbitMQ restart verification have not run in this environment; SQLite/offline SQL tests
are not substitutes for those release gates.

Historical C6 verification: 197 passed, one live-MySQL skip; 99.44% overall and 100% domain coverage. Ruff/mypy, migration/model/offline SQL checks, OpenAPI generation and typed client tests passed at that checkpoint.

Historical C6 follow-up: 205 Catalog tests passed, one live-MySQL skip, 99.50% overall. Shared 0.8.0 and all five locks/environments were synchronized at that checkpoint.


## Scheme governance and dated membership - 14 September 2026

New schemes start optional (`is_required=false`). Enable or relax requiredness through
`POST /category-schemes/{id}/transition-preview`, then `/transition`. Preview takes
`expected_version`, `membership_mode`, `is_required`, and `is_active`. Commit repeats the
input with `preview_token` and `Idempotency-Key`. The preview reports counts, blockers and
eligibility. Its 15-minute proof is bound to the actor, tenant, company, scheme, input,
company generation, Identity source version, business date and native dependencies.

The reviewed command can relax SINGLE to MULTIPLE with existing categories, narrow to
SINGLE only when every current/future family set permits it, and retire a scheme once
all children are inactive and no current/future membership remains. Retirement also clears
requiredness. A required scheme needs a membership for every active family at every known
future membership boundary. Draft products may remain incomplete; requirements and activation
report each missing `category_scheme:{id}`. These are current master policies, not historical
tax or pricing revisions. Existing activation source pins and dated membership rows are retained.

Transitions require `category_scheme.manage` and `.read`, plus readable category, membership
and affected-product dependencies. Field denies apply to preview, commit and replay, including
empty dependency sets. Ordinary direct changes retain dependency guards. Category creation,
editing, reparenting and replay also check current parent-scheme authority.

`POST /product-families/{id}/category-preview` accepts the same body as `PUT .../categories`.
For an ACTIVE family, supply a strictly future `valid_from`, `expected_version`, the complete
`categories` collection, and commit with the returned `preview_token`. The command checks
every active SKU's adopted category policy, required schemes, distinct categories and primary
cardinality. It closes open memberships on the preceding day and appends the new set. Schedules
are appended after all existing starts and closure boundaries, including an empty scheduled
set. It does not overwrite an existing schedule. DRAFT replacement retains its editing contract;
omitted `valid_from` preserves legacy coverage from 1000-01-01. Membership lists support `as_of`
or an unfiltered, signed page of retained history. Activation validates current/future sets and
pins scheme, category and membership versions. Receipt replay rechecks original dependencies.

Category codes are unique within a scheme. Bulk matching rejects an ambiguous code; use its
native ID or a unique external-key mapping. Bulk assignment shares the native validators and
requires the category preview token for an active family.

Bounds: 128 submitted memberships, 128 active SKUs for a family change, 512 affected families
for a scheme transition, 10,000 dependency rows per query, 128 activation date boundaries and
100,000 interval checks. Oversized reviews fail explicitly without partial writes. Mutations,
versions, audit and idempotency receipts share the company-locked transaction.

Migrations 0125-0128 add requiredness and membership dates and replace the two undated unique
keys. Existing rows and IDs remain, with a legacy start of 1000-01-01. Each revision has one
DDL statement. Downgrade past 0126 is deliberately blocked: removing dates could reactivate
closed history. Use a reviewed forward migration. Restoring old unique keys also refuses
incompatible retained rows. Offline verification does not establish live MySQL concurrency.
