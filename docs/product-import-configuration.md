# Configuration-aware product imports

The 2026-11-04 [Simple import delivery](simple-product-import-plan.md) supersedes
the draft-only Simple creation behavior below. New `simple_products` templates use
business codes, automatic product codes, current price/Brand/Model settings and
Goods opening stock. They complete native activation/posting. The `products`
definition and its advanced/historical configuration contract remain compatible.

Authorized 2026-10-28: product import and its downloaded template must follow
Product Configuration. Reuse the existing native import engine and product commands.

- [x] Audit templates, downloads, staging, validation, commit and the UI selectors.
- [x] Match template resources and operations to single-product/family-SKU mode;
  preserve historical jobs and exact uncertain retries.
- [x] Reflect goods/services and applicable product settings in template metadata
  and the column guide; retain native field/operation permissions.
- [x] Check the actual row configuration during validation and commit; keep
  configuration/version guards out of spreadsheet authoring where derived safely.
- [x] Add regressions, verify template/import journeys, typecheck and review twice.

Initial findings: explicit resources bypass mode-based template selection; simple
templates do not constrain the chosen goods/services kind; the UI advertises SKU
creation although the item resource only supports updates. Configuration settings
are not explained by template metadata. Product-save imports remain drafts;
physical batches/serials, stock opening and financial posting retain their native
owner workflows. That original legacy definition does not post stock on import.

## Delivered behaviour

Single-product companies receive one product code/name template. Advanced companies
receive family templates (including their first SKU) and an explicitly labelled
**Update existing SKUs** option. The native item import supports UPDATE only;
additional variant creation continues through the existing native variant workflow.
An explicit resource cannot bypass the current company mode. History remains
readable after a mode change; new writes require current authority and mode.

Template preparation accepts product kind, configuration date, optional published
product type and group. Current native configuration resolution determines the
guide and schema; selected context stays locked while files are selected. The guide
explains disabled, optional and required-before-activation settings for brands,
barcodes, categories, manufacturers, variants and unit capabilities, plus inventory
profile availability. Native layouts, specification definitions and custom fields
remain authoritative. Each row is checked against its own actual context.

Disabled brand/barcode inputs are removed from creation templates and rejected on
actual rows. Unit and variant schema choices reflect disabled capabilities. Existing
unchanged historical brand assignments and explicit clearing remain supported.
Required options follow native draft-save and activation rules; importing a draft
does not bypass activation readiness. A required field that conflicts with disabled
configuration produces a settings error instead of weakening the requirement.

Internal creation/setup versions and configuration guards are derived by Catalog.
They are excluded from spreadsheet authoring, including nested definitions. Explicit
supplied guards remain subject to native validation. Excel includes an ignored
Import_Definitions guide sheet so nested JSON references can be understood. Metadata
sheets cannot become import commands. CSV and TSV retain their native flat columns.

Retained templates recheck current mode, configuration and field permissions.
Relevant configuration changes require a current template and another review;
unrelated product writes or equivalent Identity source refreshes do not invalidate
the template. Download conflicts/expiry offer Reload and review while retaining
selected files. Exact uncertain command retries retain their existing request/key.

## Reviews and decision log

- 2026-10-28: User confirmed scope includes both product mode and applicable fields.
  Reuse native configuration, field authority, bulk commands and shared UI controls.
  No new endpoint, response model, ORM model or migration is required. Database,
  migration scripts and generated contracts keep their existing synchronized shape.
- First manual simplify/workflow review fixed the misleading SKU-create choice,
  saved-template download recovery and unresolved Excel nested-schema references.
  Selected files, completed jobs and ordinary party imports retain existing flows.
- Second manual security/correctness review fixed retained shared-custom-field
  revocation and protected product-mode reads for explicit item templates. Field
  issues now use bounded safe paths and generic messages without echoing private
  owner messages or row values. Current company scoping and native command/field
  checks remain mandatory at validation and commit. No remaining finding in scope.
- Dedicated `/simplify` and `/security-review` commands were unavailable; equivalent
  manual reviews were performed against CLAUDE.md sections 5 and 6.
- Shared import mechanisms changed: billing-platform 0.44.1, with all twelve service,
  client and library uv lockfiles refreshed offline. No dependency was added.

## Verification

- Configuration helper: 10 tests passed, 97.06% branch-inclusive coverage (all
  statements covered). Shared import engine/files: 33 passed, 93.27% coverage.
- Native tests cover both modes and all three file formats, actual base-unit setup,
  rollback during validation, reviewed commit, exact replay, update by existing ID,
  wrong resources, kind mismatch, stale configuration, mode changes and permission
  revocation: 14 passed after the final permission fix. The combined native regression
  run passed 21 cases (11 configuration cases plus 10 existing master/simple-bulk
  cases); the subsequent final run adds two file-update cases and the permission case.
- Console regressions cover configuration context, native bounded option lookups,
  guide display, update-only SKUs, file preservation, mode changes and 409/410
  download recovery, alongside existing product/party imports and strict proxies:
  90 tests passed across seven files.
- Strict Catalog mypy and Ruff passed. Shared Python mypy/Ruff passed. Console
  TypeScript passed. Coverage results above are scoped to changed Python modules;
  they do not claim the pre-existing Console-wide coverage gate is resolved.
- Real tenant3 browser: downloaded a configured CSV, uploaded a row with native
  base-unit setup and no internal guards, validated, reviewed and committed once.
  Readback found one DRAFT product with one base-unit binding; completed history
  reopened after restoring the original advanced mode. No stock/financial effect.
  Verification code: UI_IMP_CFG_1793200833146. The draft remains available to inspect.
- Light/dark/ledger desktop and mobile checks (1440/390 pixels): six combinations,
  no horizontal overflow or runtime errors; desktop/mobile screenshots inspected.
  Private test sources, browser state and logs stay in ignored .test_artifacts/.
- Catalog restarted through the managed local lifecycle after the final permission
  fix. A fresh authenticated browser read confirmed the original advanced mode and
  successful current family-template preparation with its configuration guide.
