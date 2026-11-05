# Advanced product creation: Phase 1 execution record

2026-11-04. Phase 1 implements the Catalog wizard context and private draft
foundation in [the plan](advanced-product-creation-plan.md). The UI is scheduled
for Phases 5–6; Catalog aggregate creation is scheduled for Phase 2.

## Native context

`GET /v1/companies/{company_id}/advanced-product-creations/options` accepts
`kind`, `group_id` and `product_type_revision_id`. It requires the current
company's `item.create`, `item.read`, `product_configuration.read` and readable
applicable native references. Advanced authoring mode must be enabled. The
response contains the verified live mode/version, effective configured defaults
and source version, current family and SKU field sets, selected published Type
capabilities, company inventory/GST facts, active named sale levels and required
category schemes. Native reference endpoints supply searchable choices; their
permissions and field policies remain authoritative. A failed or denied source
blocks the options request rather than inventing a Simple/default state.
The response explicitly says whether named price levels are readable; required
selling prices without that access block the options request.

## Draft endpoints and policy

| Endpoint | Contract |
|---|---|
| `POST /drafts` | Save a new bounded snapshot; `Idempotency-Key` required; same key/body returns the same draft. |
| `GET /drafts` | List at most 20 private summaries, without draft contents. |
| `GET /drafts/{id}` | Resume the initiating actor's company-scoped content; `needs_review` flags changed mode/configuration/field sources. |
| `PUT /drafts/{id}` | Replace a complete snapshot with `expected_version`; current source versions and writable native fields are rechecked. |
| `DELETE /drafts/{id}` | Explicit owner deletion with `If-Match` row version; audit marker is retained. |

The prefix is `/v1/companies/{company_id}/advanced-product-creations` for
every row above. The owner is the actor who created the draft; even another
active user with the same company permissions receives 404 for that draft.
The tenant filter also applies to the new table. A company mode change leaves
the saved draft readable with `needs_review=true`, but prevents another save
until Advanced mode is restored and the current options are reviewed.

Unsubmitted drafts do not expire automatically. The owner may delete them;
at most 20 may exist for one actor/company. One snapshot is limited to 64 KiB,
64 explicit SKU rows, bounded nesting and JSON values. Decimal money and
quantity input must be strings. The draft is intentionally incomplete data;
it is never replayed directly as a native command. The later submit endpoint
must parse its own strict schema and recheck every native field, permission,
reference and source version. The current draft field guard checks direct
family/SKU and custom fields on save and read. Setup/opening input remains
transport data until its native contracts are implemented in Phases 3–4.

## Storage, migration and audit

`advanced_product_draft` stores the actor, company, snapshot, row version and
mode/configuration/field source versions. Catalog revision `0222` adds it with
one `CREATE TABLE` DDL. Downgrade refuses to erase nonempty drafts. No product,
price, Accounting balance or Voucher document is written by these endpoints.
Create, update and delete emit registered audit events in the same transaction;
the audit evidence contains change markers, not draft content.

## Review and remaining boundaries

Phase 1 review checks `CLAUDE.md` sections 5–6: authenticated company and
actor scope; field read/write denies; bounded input; no data in audit payload;
no money or stock effects; versioned source review; migration/model alignment.
The focused Catalog suite reported **13 passed, 2 skipped**. The optional
dedicated-port native test was skipped because that isolated server is not
configured; a local native rehearsal used a private 45 MB Catalog backup in
`%LOCALAPPDATA%/BillBackups/`, restored it to a temporary schema, applied
`0221→0222`, and found zero metadata differences. Local Catalog was then
upgraded to `0222` and compared with the model: zero differences. The other
seven local database heads match their script heads. The temporary rehearsal
schema was removed. Ruff, strict mypy for changed Python files, OpenAPI and
audit exports, generated Catalog client check, Catalog declaration compilation,
Console typecheck and API client runtime tests passed. The API client's full
typecheck currently fails in unrelated `tests/accounting-types.ts` because
`AccountCreate` is absent from the concurrently modified Accounting declaration;
the Phase 1 Catalog declaration compiles. No blocking security or correctness
finding was found in the Phase 1 change.

Phase 2 must define the strict submit command and idempotent aggregate receipt.
Phase 3 must validate business setup natively; Phase 4 must validate opening
data with Accounting/Vouchers. The mode-selected directory card and route are
Phase 5 work. Verification results and any limitations are recorded in
[the live TODO](advanced-product-creation-todo.md).
