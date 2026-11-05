# Catalog source handoff and authorized Identity integration

Date: 2026-09-12. Status: implemented and tested over actual signed HTTP; live broker/MySQL release verification remains pending.
Scope authorized: Catalog API/database, shared mechanisms and the minimal Identity-owned
source integration below. Billing execution remains outside Catalog.

## Original verified gap (resolved for Identity)

Before this increment, Identity had company/detail/features endpoints, but no versioned, complete Catalog company,
capability or field-source contract. Its field-set currently returns the company native registry
only (`apis/identity/src/identity/api/companies.py`). `company.updated` is an audit delta, not a
complete authoritative snapshot. The shared gateway context provides grants and user/group
identities; it does not provide a complete, versioned field-policy source. Empty local tables
therefore cannot establish that an actor has no field denies.

Identity company/feature/field contracts now adopt version 1 after owner/client tests. Billing
contracts retain adopted_version=None. See [source operations](catalog-source-operations.md)
for table, endpoint and worker details.

## Authorized and implemented minimal Identity change

Keep Identity as sole writer and authority. Implement these changes in its own API/migration
chain; do not move any Identity ORM model into Catalog or the shared library:

1. A tenant-scoped source-generation record, advanced in the same transaction as relevant
   company, feature, definition, layout, policy and subject-assignment changes. Include the
   changed aggregate's complete versioned payload in the existing transactional outbox.
2. A protected internal snapshot workflow for company context, effective capabilities and
   field sources. Use service-specific issuer/audience/operation keys and a scoped allowlist.
   The implemented paths are POST `/internal/v1/tenants/{tenant_id}/companies/{company_id}/catalog-snapshots`,
   GET the same prefix plus `/{snapshot_id}`, and GET plus `/{snapshot_id}/pages/{page_number}`. They require a verified
   tenant/company and scope checks; an authenticated service is not automatically tenant-wide.
3. Pin every snapshot to a source generation. Page immutable records with bounded payloads,
   total counts, per-page digests and a final complete manifest. A zero-record manifest is an
   explicit known-empty set; a missing page or absent stream remains unavailable.
4. Include minimal company jurisdiction/currency/precision/rounding and lifecycle facts; the
   complete effective feature set; Catalog entity definitions/layout; field policies; and the
   subject memberships/role assignments needed to resolve the original actor. Export no
   credentials, bank details, unrelated PII or complete Identity business records.
5. Publish tombstones for deleted identities; preserve inactive rows and version history.
   Define dated assignment validity and security-source freshness. Snapshots must not infer
   a tombstone from an incomplete page or from a field-denied response.
6. Add tests for two tenants/companies, signed service scope, concurrent snapshot/mutation,
   duplicate/out-of-order delivery, subject revocation, inactive definitions, complete-empty
   policy sets and startup/recovery. Run the existing Identity suite and migration checks.

Catalog then captures events before requesting the snapshot, stages and verifies its complete
manifest, merges newer events and exposes that generation atomically. Catalog business writes
remain unavailable for unverified/stale company or field context. No synchronous owner call
occurs inside a money-affecting transaction. The current signed gateway actor protocol stays
in use; this source contract supplies the missing authoritative business and field context.

This integration adds no customer/party master, stock, actual-cost, billing document or coupon
runtime implementation. Those remain separate Billing source dependencies. The user has now
selected India GST and provided "2000" as the combined workload answer; the working interpretation
is documented in [v1 scope](catalog-v1-scope.md). Security freshness SLA and measured production
capacity are not inferred from those choices.

## Other exact external gates

| Owner/input | Required capability | Does not block |
|---|---|---|
| Billing party/customer type/membership | Customer-specific pricing and supplier references | Independent unit/classification authoring after Identity context |
| Billing physical lot/declaration | Verified stock-scoped commercial definitions | Product/pack prices that do not use those scopes |
| Billing policy acknowledgement | Confirmed operational warehouse/promotion enforcement | Authoring a draft definition |
| Billing fiscal context | Fiscal-cycle custom numbering | No-reset sequences |
| India GST selected; applicable notification/rate sources still require validation | Statutory tax/MRP adapters and tax-ready activation | Unrelated master definitions |
| Real MySQL/RabbitMQ | Infrastructure, concurrency, recovery and performance sign-off | Pure validation and offline migration checks |

## Decision log

- 2026-09-12: User explicitly reconfirmed approval to implement the minimal Identity sources.
  Inspection confirms the source models/migrations, signed endpoints and publisher already
  exist; verify and retain them rather than adding duplicate source tables or widening ownership.

- 2026-09-11: Recorded the specific source gap and a reviewable minimal Identity-owned change.
  This is a proposed scope expansion, not permission to implement another service's domain.

- 2026-09-11: User approved continuing all phases without further routine pauses after the
  explicit Identity source proposal. Proceed with the minimal source integration in Identity.
  Delivery substeps: source protocol/model/migrations -> transactional producer and authenticated
  snapshots -> Catalog verified projections/metadata -> first complete unit/master workflow.
  Review and verify each substep. A source snapshot is read under the same tenant generation
  lock acquired by every participating writer; change events commit with their native writes.
  Snapshot pages are immutable and complete-count/digest verified; missing pages never activate.
  Initial engineering bounds are 10,000 records/8 MiB per bounded snapshot; larger snapshots
  reject explicitly pending the durable job extension. These are not production capacity claims.

- 2026-09-11: Implemented the authorized Identity source proposal and first Catalog unit/packs
  workflows. Verified real signed HTTP, scope/freshness, corruption, policy revocation and
  atomic catch-up; live broker/MySQL release gates remain open.


## V1 source verification (2026-09-12)

The explicit approval was checked against the existing owner implementation. Identity already
has source generation/snapshot/page models (0035-0037), signed company-scoped snapshot endpoints,
transactional change capture, the dedicated publisher and current-actor authorization proofs.
Catalog already has the verified HTTP client, projections, bootstrap/catch-up and refresh worker.
No missing implementation was found in this minimal approved scope; no duplicate source schema
or unrelated Identity domain change was introduced.

- Identity: `tests/test_catalog_sources.py`, `tests/test_catalog_authorizations.py` and
  `tests/test_catalog_publisher.py`: **17 passed in 27.08s**.
- Catalog: `tests/test_identity_source_integration.py`, `tests/test_identity_source_client.py`
  and `tests/test_source_worker.py`: **19 passed in 65.33s**. Integration tests use an actual
  isolated Identity HTTP process; broker supervision tests do not prove live RabbitMQ recovery.
- Result files: `apis/identity/.test-results-catalog-v1-sources.xml` and
  `apis/catalog/.test-results-v1-identity-sources.xml`.

Live MySQL migration/concurrency and live RabbitMQ recovery gates remain open. This verification
adds no completed implementation tasks; the full backlog remains 47/205.
