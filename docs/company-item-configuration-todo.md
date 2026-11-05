# Company and Item Configuration Implementation TODO

**Date:** 2026-10-10
**Status:** In Progress
**Scope:** Backend APIs and Databases (`apis/accounting`, `apis/catalog`, `dbs/accounting`, `dbs/catalog`, `libs/platform`). UI deferred to later.
**Phased Plan:** Phased execution with verification, review, and findings fixes at each phase milestone.

**Current authority (2026-10-12):** This is the historical checklist. Use the
[CI-P0–CI-P5 plan](company-item-configuration-plan.md) and its
[execution record](company-item-configuration-execution.md) for current status and
evidence. The open sequence, voucher, stock and manufacturing entries below belong
to the existing [voucher delivery tracker](voucher-delivery-tracker.md) and its
Accounting/Vouchers owners; they must not be implemented as parallel Catalog stores.
The checked negative-stock item proves Catalog can define `BLOCK/WARN/ALLOW`, not
that valued `WARN/ALLOW` movements execute. The checked HSN/SAC directory is a
reference lookup, not an approved transaction tax resolution.

---

## Phase 1: Foundation Linkage & Policy Enforcements

- [x] **1.1 Warehouse Godown to GSTIN Linkage**
  - [x] Migration in `dbs/catalog/versions/`: Added `tax_registration_id` (`BINARY(16)` NULL) and index `ix_warehouse_tax_registration` in `0158_add_warehouse_tax_registration.py`.
  - [x] Model update in `apis/catalog/src/catalog/models/warehouses.py`: Added `tax_registration_id` column and index.
  - [x] Schemas in `apis/catalog/src/catalog/schemas/warehouses.py`: Updated `LocationFacts`, `WarehouseListItem`, `WarehouseDetail`.
  - [x] Field registry in `apis/catalog/src/catalog/domain/field_registry.py`: Added `tax_registration_id`.
  - [x] Unit & integration tests: Added `test_warehouse_tax_registration_linkage` in `test_warehouse_api.py`. Verified pass.

- [x] **1.2 Configurable Negative Stock Policy**
  - [x] Shared enum in `libs/platform/src/billing_platform/constants.py`: Defined `NegativeStockPolicy` (`BLOCK`, `WARN`, `ALLOW`).
  - [x] Migration in `dbs/catalog/versions/`: Added `negative_stock_policy` in `0159_add_negative_stock_policy.py`.
  - [x] Model updates in `apis/catalog`: Added check constraints and columns to `InventoryProfileTemplateRevision` and `ItemInventoryProfile`.
  - [x] Schemas & API routes in `apis/catalog`: Exposed in `InventoryRevisionInput`, `InventoryRevisionUpdate`, etc.
  - [x] Unit tests: Added `test_inventory_negative_stock_policy` in `test_inventory_template_api.py`. Verified pass.

- [x] **1.3 CBIC HSN/SAC Master Directory & Lookup**
  - [x] Statutory directory in `apis/catalog/src/catalog/domain/cbic_directory.py`: Seeded goods and services tariff directory with descriptions and default GST rates.
  - [x] Schemas in `apis/catalog/src/catalog/schemas/tax_reads.py`: Added `HsnSacReferenceItem` and `HsnSacSearchResponse`.
  - [x] API endpoints in `apis/catalog/src/catalog/api/tax.py`: Implemented search (`/tax-reference/hsn-sac`) and code lookup (`/tax-reference/hsn-sac/{code}`).
  - [x] Unit tests: Added `test_cbic_hsn_sac_directory_search_and_lookup` in `test_tax_workflows.py`. Verified pass.

- [x] **1.4 Statutory Cash Receipt Gate (§269ST)**
  - [x] Domain rule & tasks in `apis/accounting`: Implemented single receipt and aggregate same-day party cash checks in `party_documents.py` and `subledger_posting.py`.
  - [x] Unit tests: Added Section 269ST aggregate daily validation assertions in `test_finance_boundaries.py`. Verified pass.

- [x] **Phase 1 Review & Verification**
  - [x] Verified test suites: 100% pass across catalog and accounting test targets.
  - [x] Linters (`ruff`) and static types (`mypy`): 0 errors, all checks passing.
  - [x] Findings documented and fixed.

---

## Phase 2: Sequence Numbering & Lifecycle Locks

- [ ] **2.1 Runtime Gap-Free Document Sequence Allocator**
- [ ] **2.2 First-Posting & Feature-Lock Outbox/Inbox**
- [ ] **2.3 Party Credit Limit & Overdue Interceptor**
- [ ] **Phase 2 Review & Verification**

---

## Phase 3: Opening Stock & Valuation Capture

- [ ] **3.1 Opening Stock Schema**
- [ ] **3.2 Opening Stock API & Double-Entry Posting**
- [ ] **3.3 Catalog Stock Projection Sync**
- [ ] **Phase 3 Review & Verification**

---

## Phase 4: Core Voucher Engine & Stock Movement

- [ ] **4.1 Document Baseline & Line Detail Tables (B01 / V1)**
- [ ] **4.2 Stock Movement & Lot Valuation Ledger (V4)**
- [ ] **4.3 Landed-Cost Apportionment**
- [ ] **Phase 4 Review & Verification**

---

## Phase 5: Advanced Manufacturing & Operational Utilities

- [ ] **5.1 Barcode Label Generation & Thermal Print Stream**
- [ ] **5.2 Near-Expiry Auto-Quarantine & Shelf-Life Dispatch**
- [ ] **5.3 Bill of Materials (BOM) & Kitting / Assembly Engine**
- [ ] **Phase 5 Review & Verification**
