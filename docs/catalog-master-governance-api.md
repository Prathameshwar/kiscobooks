# Master aliases, external keys and usage (C6.07)

This package continues the agreed Catalog-only phase plan. It uses the existing company
policy lock, trusted Identity field context, signed list cursors and audited idempotent
commands. It does not implement party identifiers or create missing owner API records.

## Delivery sequence

1. Add master_alias and master_external_key with strict target registration, scoped identity
   constraints, paired reversible one-DDL migrations, models, schemas and tests. Registry
   targets initially include the eighteen implemented Catalog masters; revisions, external
   parties and item identities are outside this closed master mapping registry.
2. Add nested create/list/detail/activate/deactivate APIs plus exact protected resolution.
   Identity fields are immutable. Retiring a mapping preserves ownership of its key; a key
   cannot silently move to another master after being used by import or integration.
3. Add the protected paginated master-usage endpoint over actual local dependencies, with
   explicit coverage of the caller's visible definitions and unavailable external usage.
   Lifecycle commands remain the authority for safe changes; a partial usage page does not
   certify that a master can be retired or that Billing has no operational references.
4. Review scope, field-policy side channels, canonical collisions, concurrent creates,
   immutable key ownership, stale/revoked replay and safe retirement. Run affected regressions,
   schema/client checks and coverage before closing C6.07.

## Reviewed contracts

| Resource | Identity and behavior |
|---|---|
| master_alias | Company, registered entity_type, immutable target_id, alias text and code-owned normalization version; normalized NFKC/casefold lookup; unique entity/normalized alias across targets; original display spelling retained |
| master_external_key | Company, registered entity_type, immutable target_id, explicit source_namespace and exact external key; leading zeroes and case retained; unique entity/source/key across targets |
| Master reference registry | Code-owned models, required owner permission and parent field policy; no arbitrary SQL table names or cross-service targets; retired targets retain historic mappings but cannot acquire/reactivate live mappings |
| Mapping lists | Nested under the exact owner; signed keyset pages, typed activity filters and indexed prefix search where supported; dedicated lean schemas; no unconditional counts |
| Exact resolution | Explicit alias or external-source namespace; current target permission and identity/activity field checks before the lookup; then one exact candidate and scoped owner validation; never an unqualified product/barcode scan or silent native-code fallback |
| Usage | Bounded protected dependency references with stable pagination; caller-visible coverage and declared external readiness; no leaked denied IDs/counts and no claim that publication means external enforcement |

Alias spelling and external source keys are metadata used for identity resolution. They cannot
supply business policy, prices, taxes, stock, quantities or capability flags. Imports must bind
explicit source namespaces and run normal domain handlers under current actor authority.
Mapping lifecycle and changes must commit their audit and idempotency receipt in the same
transaction. History is retained; no hard-delete/retarget operation is planned.

Decision 2026-09-12: implemented the two mapping stores and fourteen API operations;
C6.07 review, regression, schema, client and coverage gates are complete. Its two tables
arrived at 59/head0061; the subsequent reviewed draft-product increment brings the schema
to 61/head0063.

## Routes and permission boundary

All routes begin `/v1/companies/{company_id}/masters/{entity_type}`. Targets are the eighteen
implemented unit, packaging, classification, attribute and profile masters. Family/SKU targets
will be added with their real C7 models and migrations; arbitrary targets are rejected.

| Suffix | Operations |
|---|---|
| `/{target_id}/aliases` | GET list; POST create |
| `/{target_id}/aliases/{id}` | GET detail |
| `/{target_id}/aliases/{id}/activate`, `/deactivate` | POST expected-version lifecycle |
| `/aliases/resolve` | GET exact normalized alias |
| `/{target_id}/external-keys` | GET list; POST create |
| `/{target_id}/external-keys/{id}` | GET detail |
| `/{target_id}/external-keys/{id}/activate`, `/deactivate` | POST expected-version lifecycle |
| `/external-keys/resolve` | GET exact namespace/key |
| `/{target_id}/usage-relations` | GET permitted direct local relation metadata |
| `/{target_id}/usage` | GET one relation's signed keyset page |

Mapping read/manage and the underlying master's read/manage authorities are independent.
Creation and activation also require writable owner identity; the mapping API cannot bypass a
code field write restriction. Every replay uses current authority and field rules. Alias display
and canonical read protection are coupled. Exact resolution requires readable mapping and
owner activity before looking up either an existing or missing identity, preventing status probes.
Membership fields are protected on detail, lists, resolution and usage.

Alias normalization is versioned NFKC, casefold and whitespace collapse, with controls rejected.
External keys preserve case, leading zeros and internal spaces; namespaces are explicit lowercase
ASCII identifiers. Surrounding whitespace is rejected. MySQL binary collation protects identity;
SQLite uses the model's dialect variant for local tests. Canonical integrity is checked on reads,
lists, lifecycle and retained-receipt rendering; inconsistent restored data returns a safe conflict.

Lists default to 50 and cap at 200. Aliases allow normalized prefix search, activity filtering and
canonical/id forward or reverse ordering. External keys allow exact namespace/key and activity
filters with id ordering; opaque keys do not use fuzzy search. Cursors bind company, target,
actor, source-policy version and query. Retired identities keep their unique claim permanently.
There is no PATCH, hard delete or retargeting route. Retiring the owner preserves mapping
history, prevents new/reactivated mappings and removes it from active exact resolution.

## Usage coverage

Usage discovers direct native foreign-key relations registered in Catalog field metadata, plus
the two explicit polymorphic mapping relations. The relation catalog includes only source
entities and membership fields readable by the actor; it does not query counts. Individual
pages expose reference IDs, entity and field, with id/-id ordering and supported readable
activity/publication filters. It does not expand recursive dependencies, custom-field values,
physical stock or Billing records. Unsupported relations, text search and sorts are rejected.

Responses identify `permitted_local_relations` or `selected_local_relation` coverage,
`external_usage=unavailable`, and `retirement_check=use_lifecycle_command`. An empty page
cannot authorize retirement. Existing lifecycle handlers still validate their real dependencies.

## Schema and delivery

0060 creates `master_alias`; 0061 creates `master_external_key`. Each has one literal CREATE
and one reversible DROP, scoped unique identity/owner indexes, positive version checks and
closed target checks. Polymorphic targets use the closed owner registry under the company
policy lock; no cross-service foreign key or pretend universal-master table is introduced.

Six new audit event keys cover create/activate/deactivate for both tables, for 111 registered
Catalog audit keys in total. State, audit, policy generation and idempotency receipt commit
atomically; no-op lifecycle calls keep the business version and emit no new change event.


Live verification 2026-09-12: `python -m tools.mysql_smoke` passed against an isolated local
MySQL 9.6.0 instance. All 59 tables through 0061 upgraded, downgraded to base and upgraded
again; comparison found no model/schema drift. Two reference workflows, two company/tenant
scope workflows and two real concurrent command races passed. Random test schema cleanup
completed. This does not claim a full v1 integration or 2,000-SKU performance benchmark.

Review completed 2026-09-12: current-owner activity read checks cover fresh create/activate and retained replay. C6.07 is signed off with the 450-test combined Catalog regression, 99.77% coverage and native MySQL migration/schema/concurrency proof. The full-backlog ledger is 48/205; V1.1 is complete.
