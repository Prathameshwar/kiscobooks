# Warehouse configuration, creation, stock and management review

Reviewed 2026-11-07 against the current local working tree. This is a source and local-test review; it does not establish the deployed VM's behavior. Application fixes and deployment are separate work.

## Consolidated findings

Eleven findings: three high priority and eight medium priority. “Reproduced” means a local API or actual React diagnostic exercised the behavior. “Integration gap” means the required producer/consumer or console workflow is absent in the reviewed source; it is not a claim that a particular live transaction produced an incorrect financial result.

| ID | Priority | Area | Finding and user impact | Evidence |
|---|---|---|---|---|
| W01 | High | Configuration / retirement | Warehouse retirement requires a company stock-location policy release, but the console has no release publication, receipt/history or retry workflow. Even a newly created empty store can be blocked from deactivation. Publishing location operation flags or company defaults is a different command and does not supply this missing workflow. | API reproduction plus console integration review |
| W02 | High | Dated group membership | Scheduling a warehouse's group membership to end in the future makes the retirement guard treat it as already closed. The warehouse can be deactivated while the membership is still effective. | API reproduction, including retirement with the owner-adapter boundary configured |
| W03 | Medium | Creation / retry | After an uncertain save response, the standalone warehouse editor leaves identity fields editable. Changing the code submits a new idempotency key. If the first command committed, the second can create another warehouse. The existing protection applies only to embedded editors. | Actual React/JSDOM reproduction of HTTP 503, editable code and a second distinct key |
| W04 | Medium | Feature configuration / creation | Create-field metadata and the console's New warehouse action do not reflect the inventory/multi-godown creation gate. A Main-only company gets a writable form and reaches a 409 only after submission. | API reproduction: writable create metadata followed by feature-gate rejection |
| W05 | Medium | Create / edit validation | Timezone validation checks a text pattern rather than an actual IANA timezone. `Not/AZone` is accepted and stored. The picker improves normal console input, but the native validation boundary remains incomplete. | API reproduction plus shared create/update schema review |
| W06 | Medium | Create / edit validation | `tax_registration_id` accepts an unverified UUID. A nonexistent registration can be stored; the validation also does not establish that it belongs to this company. This is broken reference integrity, rather than evidence of cross-tenant data disclosure. | API reproduction with a never-created registration; native linkage tests also accept arbitrary UUIDs |
| W07 | Medium | Automatic provisioning | Trusted company enrollment skips warehouse provisioning when inventory is off, leaving no Main metadata. The documented contract requires Main to exist in metadata-only mode too. Manual bootstrap is available, but does not repair the automatic enrollment contract. | Enrollment-task reproduction and documentation comparison |
| W08 | High | Warehouse tax context / execution | Warehouse country, state, address and tax-registration linkage are stored, but are absent from the stock execution warehouse fact contract and its producer. No reviewed Vouchers/Accounting consumer resolves these warehouse facts as ship-from tax context. Multi-state warehouse configuration therefore lacks the required transaction handoff. Incorrect tax on a live voucher has not been demonstrated by this review. | Integration gap against the documented transaction-adapter requirement |
| W09 | Medium | Product / warehouse management | Native per-product warehouse policies and replenishment bands exist, but the console has no corresponding maintenance flow. Users cannot maintain SKU location allow-lists, activity defaults and replenishment bands through product management. These dependencies can also require API work before retirement succeeds. | Native endpoints exist; no console consumers or product actions |
| W10 | Medium | Group stock reporting | Warehouse groups and dated membership exist in Catalog, but the stock reporting source emits product groups and flat physical locations. Warehouse group hierarchy/membership is not exported for stock rollups. The console's claim that parent warehouse selections include descendants is consequently unsupported by this producer. | Reporting producer/contract review |
| W11 | Medium | Stock availability | Warehouse stock reports do not provide complete reserved/available-for-sale quantities. Accounting emits `reserved=None` and `reservations_complete=False`; its reported eligible quantity also lacks warehouse operation-policy eligibility. Reports correctly leave unavailable quantities unknown, but users cannot get the promised reservation-aware, sale-ready stock view per warehouse. Transaction stock selection separately checks operation policies. | Stock summary producer and report aggregation review |

## Source references and correction direction

### W01 — Make policy release management reachable

- `apis/catalog/src/catalog/tasks/warehouse_policy.py:154`: retirement requires `release_in_force`; missing release raises “publish a stock-location policy release before retiring a location”.
- `apis/catalog/src/catalog/api/releases.py:44`: native `/policy-releases` commands and reads exist.
- `apis/catalog/src/catalog/tasks/releases.py:237`: release publication invokes stock-owner acknowledgement; the repeat-publication path also retries delivery.
- `mfes/apps/console/app/components/WarehouseSettings.tsx:51` and `WarehouseOperationPolicy.tsx:48`: console publishes defaults/per-location revisions, without a `/policy-releases` consumer.

Provide reviewed company-release publication, delivery state, retry and history in the warehouse console. Explain the required action from a blocked retirement. Preserve the native retirement prerequisite rather than bypassing it.

### W02 — Respect effective membership dates

- `apis/catalog/src/catalog/tasks/warehouse_policy.py:94`: `group_dependency` filters only `valid_to IS NULL` at line 108.
- The diagnostic seeds an existing membership, schedules its end five days ahead through the native assignment command, verifies that it is still effective today, and successfully retires the warehouse.

Evaluate current and pending effective relationships when deciding retirement. Define the treatment of future membership changes explicitly and retain closed historical intervals.

### W03 — Recover an uncertain standalone create

- `mfes/apps/console/app/components/CatalogMasterEditor.tsx:27`: uncertainty is gated by `!!embedded`.
- Line 42 assigns a fresh key when the payload changes.
- `docs/testing/warehouse-review/probes.cjs` renders the actual standalone editor and shared UI controls. After a simulated 503, code changes from `STORE_A` to `STORE_B` and the second POST carries a different key.

Extend uncertain-command recovery to standalone masters: keep the original command recoverable and prevent submitting a changed identity until its outcome is established. Retrying the identical existing payload already preserves its key.

### W04 — Surface feature eligibility before submission

- `apis/catalog/src/catalog/tasks/warehouses.py:127`: native create checks additional-location features.
- `apis/catalog/src/catalog/api/field_metadata.py:91`: writable resource computation lacks the corresponding warehouse-create feature check.
- `mfes/apps/console/app/components/CatalogMasterDirectory.tsx:90`: New action depends on manage permission.
- `mfes/apps/console/app/components/CatalogMasterEditor.tsx:52`: form eligibility relies on writable fields.

Expose feature-aware create eligibility and a clear reason in the directory/editor while retaining native enforcement.

### W05 / W06 — Validate location facts at the owner boundary

- `apis/catalog/src/catalog/schemas/warehouses.py:29`: registration is a plain optional UUID; timezone uses a permissive text pattern at line 30.
- `apis/catalog/src/catalog/tasks/warehouse_policy.py:225`: validation checks country/state reference integrity but does not validate timezone membership or resolve company tax-registration ownership.

Validate timezones with the supported IANA set and return field-specific errors. Resolve tax-registration references through their owner, checking company and relevant jurisdiction/status. Apply the same rules to creation, correction and import paths.

### W07 — Provision Main in metadata-only mode

- `apis/catalog/src/catalog/tasks/warehouse_defaults.py:44`: inventory-off exits with `NOT_APPLICABLE` before creating Main.
- `docs/catalog-warehouses.md:41` and `docs/company-features.md:223`: Main metadata is required with inventory off.

Separate metadata provisioning from permission to perform stock movements; keep bootstrap atomic/idempotent and preserve Main-only stock enforcement.

### W08 — Pass warehouse tax facts to the transaction owner

- `docs/catalog-warehouses.md:141`: actual ship-from address and required company tax-registration references must be available to the transaction adapter.
- `apis/catalog/src/catalog/tasks/stock_sources.py:236`: warehouse facts contain identity, kind, activity, department and operation-policy fields.
- `clients/voucher-execution/src/voucher_execution/stock_facts.py:102`: contract omits country/state/address/tax-registration context.

Design the owner-approved handoff and document behavior for different ship-from contexts. Preserve document tax ownership; this finding does not justify introducing a second warehouse tax engine.

### W09 — Expose product location policy maintenance

- `apis/catalog/src/catalog/api/warehouse_policies.py:40`: warehouse-policy GET/PUT.
- Line 91: replenishment-policy GET/PUT.
- `mfes/apps/console/app/components/ProductInventoryActions.tsx:107`: stock/batch/serial/opening actions, without these policy editors.

Add product location-policy and replenishment maintenance with native validation, explicit defaults/allow-list semantics and dependency links from blocked warehouse retirement.

### W10 — Deliver warehouse groups to reporting

- `apis/catalog/src/catalog/tasks/stock_report_sources.py:83`: builds hierarchy from `ItemGroupParent`.
- Line 96 emits `Location` with ID/code/name and no parent/membership context.
- `mfes/apps/console/app/lib/inventory-workspace.ts:27`: promises parent warehouse descendant inclusion.

Export effective warehouse grouping to reporting without mixing product and location dimensions. Apply date-aware membership, scoped access and descendant deduplication; align the console description with delivered behavior.

### W11 — Complete the available-stock contract

- `apis/accounting/src/accounting/tasks/stock_summary_source.py:300`: eligible quantity excludes held serial units; line 305 emits no reserved quantity.
- Line 338 declares reservations incomplete.
- `apis/reports/src/reports/domain/reporting/inventory.py:392`: reservation/available figures stay unknown when coverage is incomplete.
- `docs/catalog-warehouses.md:151`: requests on-hand, reserved and sale availability per location.

Supply reservation evidence and operation-aware eligibility from the appropriate stock owner before displaying sale-ready quantities. Preserve unknown results while that evidence is unavailable.

## Verification

- Existing Catalog warehouse API/default/mode/resolution/structure suites: **70 passed**.
- Review API diagnostics: **5 passed**. One diagnostic combines invalid timezone and unknown registration; another exercises future-dated group clearance and native retirement.
- Actual React/JSDOM diagnostic: **passed**, confirming the standalone uncertain-create behavior.
- Diagnostic Python file: Ruff check and format check passed.
- Standard `warehouse-ui.test.tsx` Vitest run could not start: esbuild process launch fails with `spawn EPERM` in this environment. The React diagnostic uses TypeScript transpilation and the actual controls without that launcher; it is not a substitute for the entire UI suite.

Explicit reproduction commands:

```powershell
# From apis/catalog:
.venv/Scripts/python.exe -m pytest tests/warehouse_review_probes.py -q -p no:cacheprovider --tb=short
# From repository root:
node docs/testing/warehouse-review/probes.cjs
```

The diagnostics intentionally assert the observed gaps. The Python filename does not use pytest's normal `test_*.py` discovery pattern. Convert these scenarios into assertions of corrected behavior when implementing fixes; a passing review diagnostic does not mean that the behavior is correct.

## Safeguards verified during review

Native transaction selection enforces warehouse/item operation policies; stock-owner retirement checks quantity/value and pending transfer/document evidence. Main and internal transit identities are guarded, country/state pairing is validated, and warehouse group membership does not grant location access. Transfers and physical-stock count entry already have console routes. No new bypass was established in these areas.

## Follow-up checklist

- [ ] W01 Company release publication, delivery retry/history and retirement recovery UI.
- [ ] W02 Effective-date-safe group retirement guard.
- [ ] W03 Standalone uncertain-create recovery.
- [ ] W04 Feature-aware warehouse creation UI/metadata.
- [ ] W05 Native IANA timezone validation.
- [ ] W06 Company-owned tax-registration reference validation.
- [ ] W07 Inventory-off Main metadata provisioning.
- [ ] W08 Warehouse ship-from tax context handoff.
- [ ] W09 Product warehouse/replenishment policy maintenance UI.
- [ ] W10 Date-aware warehouse group reporting integration.
- [ ] W11 Reservation-aware and operation-aware warehouse availability.

Fixes are not started by this review. VM updates remain deferred.
