# Catalog stock-location API and database

Status: stock-location **definitions** implemented, 18 September 2026, revisions 0132-0143.
Scope is Catalog definitions and configuration. Stock quantities, movements, transfers, counts
and adjustments are Billing's and have no route, no table and no importable resource here.
Design: [stores, godowns and stock-location configuration](catalog-warehouses.md).
Phasing and closure evidence: [stock-location definitions plan](catalog-warehouse-plan.md).

## Tables and invariants

| Table | Purpose |
|---|---|
| warehouse | One company stock location: code/name, kind STORE/GODOWN/INTERNAL_TRANSIT, optional department, timezone and native address/tax-location facts. Paired checks tie `is_system` to the reserved MAIN code and the transit kind to TRANSIT, so a built-in identity cannot be forged by a write the API never saw. |
| company_warehouse_configuration | One row per company: immutable `main_warehouse_id`, the four current activity-default pointers and the provisioning source version. Main and transit must differ. |
| warehouse_operation_policy_revision | Numbered revision per location with a server-assigned UTC window and the eight typed operation booleans as columns. A publish inserts the revision already in force and closes its predecessor in the same transaction; there is no draft and no update route. |
| warehouse_group | Non-stockholding region/zone identity, company-unique code, `is_active` lifecycle. Groups hold no stock and confer no access to their members. |
| warehouse_group_parent | Dated parent interval per group, unique `(group_id, valid_from)`, no self-parent, depth bounded at eight, cycles refused per date. |
| warehouse_group_assignment | The location's dated primary group, unique `(warehouse_id, valid_from)`. Append-only: a reparent or reassignment effective later leaves March's rollup answering for March. |
| warehouse_bin | Physical subdivision of one location, unique `(warehouse_id, code)`; the parent is part of the bin's identity and never changes. |
| item_warehouse_policy | Per-SKU selection mode ALLOW_ALL_ACTIVE / ALLOW_LIST plus four nullable product activity-default pointers. A missing row is the documented baseline, not a 404 and not a guessed deny. |
| item_warehouse_permission | Explicit per-location operation restrictions, keyed to the policy's scoped item key rather than to `item`, so a restriction without a selection mode cannot exist. Composition with the location revision is narrowing-only and computed, never stored. |
| item_replenishment_policy | Safety / reorder / target / MOQ / maximum / multiple as `DECIMAL(19,4)` on the product's unit grid, lead time and purchase unit binding. The product-wide band stores the nil UUID in `scope_warehouse_id`, tied by check to a NULL `warehouse_id`, which makes "one product-wide band" a unique constraint. |
| catalog_policy_release | Numbered, dated release with `published_at`, bounded manifest counts, manifest digest and the generation and source version it was validated against. |
| catalog_policy_consumer_ack | Trusted consumer, release/aggregate and source-event identity, enforced revision, APPLIED/REJECTED with an allowlisted safe reason. Source-only ingestion with `message_id` dedupe; an older acknowledgement never regresses current enforcement. |

Revisions 0132-0143 each contain one CREATE and one DROP downgrade; no seed DML. Every foreign
key is composite and same-company. Column contracts are in [schema](catalog-schema.md).

## Routes

All paths start `/v1/companies/{company_id}`. Commands require `Idempotency-Key`; updates and
lifecycle actions require `expected_version`; a policy write also echoes `expected_generation`
and `expected_source_version`. Create returns 201 with `Location`. Replay reauthorizes against
current Identity subjects and policies rather than trusting the stored receipt.

| Resource | Operations |
|---|---|
| /warehouse-configuration | GET Main pointer, the four current activity defaults, `multi_godown` state, the live Identity `source_version` and the stored `provisioned_source_version` |
| /warehouse-configuration/bootstrap | POST 201; provisions Main, transit custody and the singleton in one company-locked transaction, and catches up a company created before Catalog was deployed. There is no `PATCH` on the singleton |
| /warehouse-configuration/defaults | POST typed audited action for the four activity defaults; each pointer is checked against the operation it serves, and with `multi_godown` off only Main is accepted |
| /warehouses | POST create; GET list |
| /warehouses/{id} | GET detail; PATCH descriptive, address and timezone changes. `code`, `kind`, `is_system` and `is_active` are reserved — a built-in's identity is a 409 |
| /warehouses/{id}/activate or /deactivate | POST lifecycle. Deactivation costs `warehouse.deactivate` and runs the two-half fence below |
| /warehouses/{id}/primary-group | PUT dated `assign` with `effective_from`; needs `warehouse.manage` over the location **and** `warehouse_group.manage` over the grouping |
| /warehouses/{id}/operation-policy | GET the revision in force, the retained history and each revision's `delivery_state` |
| /warehouses/{id}/operation-policy/preview | POST the eight proposed booleans; writes nothing, takes no idempotency key, and reports the diff plus `publishable` |
| /warehouses/{id}/operation-policy/publish | POST `warehouse.publish`; supersedes rather than rewrites, and a proposal that changes nothing writes nothing and does not move the generation |
| /warehouse-groups | POST create; GET list |
| /warehouse-groups/{id} | GET detail; PATCH labels |
| /warehouse-groups/{id}/activate or /deactivate | POST lifecycle |
| /warehouse-groups/{id}/reparent | POST dated parent change with `warehouse_group.move` |
| /warehouse-groups/{id}/parents | GET the retained parent history, paged |
| /warehouse-groups/{id}/children | GET one tree level at a required `valid_at` |
| /warehouse-groups/{id}/members | GET the deduplicated member locations at a date; needs `warehouse_group.read` **and** `warehouse.read` |
| /warehouse-bins | POST create with the parent location in the body; GET list |
| /warehouse-bins/{id} | GET detail; PATCH labels |
| /warehouse-bins/{id}/activate or /deactivate | POST lifecycle |
| /items/{id}/warehouse-policy | GET the composed effective policy; PUT the whole stated policy |
| /items/{id}/replenishment-policy | GET the stored bands; PUT the whole stated set of bands |
| /policy-releases | GET the ordered series and the release in force; POST 201 publish |
| /policy-releases/{id} | GET an older release and what each consumer acknowledged |

Permissions are `warehouse.read/manage/publish/deactivate`, `warehouse_group.read/manage/move`,
`warehouse_bin.read/manage`, `item_warehouse_policy.read/manage` and `catalog.release.read` —
twelve keys, none of which authorizes a stock movement. `warehouse.deactivate` is separate from
`.manage` because retirement is the one location action that can strand stock, and
`warehouse_group.move` is separate because reparenting rewrites history for every descendant.
Reading a product's location policy needs `warehouse.read` as well as
`item_warehouse_policy.read`: those projections answer with location identities, and an actor
without location read must not enumerate a company's stores through a product.

Lists default to 50, cap at 200, use signed keyset cursors, code/name prefix search,
code/name/id sorting in either direction, typed allowlisted filters and lean list items. A
field read-deny also prohibits filtering, searching and sorting by that field, and omits it from
detail, history and preview output.

## Resolution, composition and the two fences

An omitted location resolves as authorized explicit choice > product activity default > company
activity default > built-in Main. A configured default that is inactive, denied,
operation-disabled or transit is an **error**, never permission to continue down the chain, and
*no eligible location* is a first-class outcome rather than a silent fallback. Product
restrictions narrow a location's capabilities and can never widen them; the intersection is
computed at read time, so a narrower location revision published afterwards shrinks
`effective_operations` without touching the stored product rows.

A published policy reads `PENDING` until a trusted consumer acknowledges the revision it
enforces, then `APPLIED`, or `REJECTED` with the consumer's safe reason. Definitions alone cannot
claim a stop in another database, so `delivery_state` is computed from the acknowledgement rather
than stored at publication.

Retiring a location has two halves. Catalog's own runs first and every refusal is a 409 the
caller can act on: a company or product activity default still pointing at it, an active bin, a
product still stocked there, an open group membership, no release in force, no reviewed operation
policy. Only then does the coordinated half run — stock, reservations, open transfers and pending
documents live in Billing, so Catalog asks for a clearance and the **absence** of one is a 503
pending state, not permission. A consumer's refusal is a 409 carrying its reason code. Nothing
here infers safety from a displayed zero quantity.

## Acknowledgement ingestion

There is no route that writes an acknowledgement. A client asserting "Billing applied this" would
make `APPLIED` meaningless, so those rows arrive only through the consumer worker from a signed
source event, deduped on `message_id`, and Catalog verifies that the release, aggregate and
enforced revision are things it actually published before storing the claim.

## Bulk

[Bulk](catalog-v15-api.md) imports these definitions through the same commands the routes call:
`warehouse` CREATE / UPDATE / ACTIVATE / ASSIGN / PUBLISH_OPERATION_POLICY, `warehouse_group`
CREATE / UPDATE / ACTIVATE / DEACTIVATE / MOVE, `warehouse_bin` CREATE / UPDATE / ACTIVATE /
DEACTIVATE, and on `item` SET_WAREHOUSE_POLICY and SET_REPLENISHMENT_POLICY. Rows address
existing targets by exact scoped code (`sku` for a product), and an omitted location uses the same
resolver as the API.

Four things are deliberately absent. A stock balance, a transfer, a count and a trading party
have **no resource**, so a file naming one is refused when it is staged rather than partly
applied. `warehouse.DEACTIVATE` and the configuration singleton are absent because each is one
reviewed coordinated action, and a file of them is what the fence exists to prevent. Authority is
resolved when the file runs, not when it was staged: a publish key withheld in between fails that
record. Guards — generation, row version and source version — are read at write time and cannot
be supplied by the file.
