# Company product configuration: end-to-end consumer review

Reviewed 2026-10-30 after the Company-only simplification. This review follows
configuration creation, publication, default acceptance, product adoption and
the consumers that read the saved product pins. The implementation TODO is
[here](company-product-configuration-consumer-review-plan.md); reusable cases and
results are in [the CSV](company-product-configuration-consumer-results-2026-10-30.csv).

## Bugs found and fixed

| ID | Complexity | Finding | Correction |
|---|---|---|---|
| CFG-C01 | High | A newly adopted Company VALUE/CLEAR profile choice reverted to the optional native type profile when the saved pins were read. Preview and adoption therefore disagreed. | New adoption records and signed preview evidence use resolution version 2. All SKU consumers honor Company precedence. Existing version 1 records keep their original behavior. |
| CFG-C02 | Medium | Company publication validated generic goods/service configuration without the constraints of its configured default product type. Incompatible defaults could be published and fail during product creation. | Resolve the configured goods/service type before validating preview/publication, so incompatible requiredness and native profile constraints fail before publication. |
| CFG-C03 | Medium | The adoption UI accepted previews from an older response contract, which could offer adoption without confirming Company-only semantics. | Verify version 2; missing, old or unsupported markers show a protected failure and expose no adoption action. No extra setting is shown to users. |
| CFG-C04 | Low | Final review found that the new server-controlled adoption marker was presented as writable by native field metadata, even though the commit body rejects it. | Mark it read-only in native metadata and retain the field-deny checks for server writes. A fail-first metadata regression covers this. |

Fail-first native cases reproduced profile VALUE/CLEAR loss and incompatible
default-type publication. A fail-first UI case reproduced acceptance of version
1. The fixed regressions also cover service defaults, native commit validation,
exact quantity/price suggestions, readiness, future publication, protected version
reads, unsupported versions and strict rejection of a caller-selected marker.

## Consumer coverage

| Consumer | Resolution and review |
|---|---|
| Company overview, create/edit, preview/publish and history | One Company draft route; dated publication and source/generation guards; old owner history remains protected/read-only. |
| New goods/services and family/SKU setup | Company defaults plus the selected native type; explicit accepted suggestions, dirty-value preservation, units, pricing and tax setup retain their native contracts. |
| Existing SKU defaults and requirements | Saved adoption version and immutable sources govern the read; future Company publication does not silently change those pins. |
| Type/group/profile reference pickers | Native master preparation remains independent of configuration ownership; all configuration option sources retain closed proxy routing and field admission. |
| Attributes, barcodes, categories and manufacturers | Configuration controls availability/requiredness; native ownership, field denies and existing-state rules remain authoritative. |
| Units, quantity preview and price validation | SKU configuration reads the recorded resolution version; exact native Decimal/grid rules remain unchanged. |
| Imports and bulk | Current Company rules prepare templates/new rows; native per-row commands and reviewed adoption enforce configuration, object/version guards and transactional rollback. |
| Readiness and activation | Proposed review uses Company-only semantics; native activation writes version 2 adoption and immutable activation/source evidence. |
| BOM dependencies and dated category changes | The shared SKU configuration resolver preserves the recorded semantics; native revision, readiness and active-history guards remain in force. |
| Accounting/Vouchers/Reports | These consume Catalog source/activation facts rather than resolving mutable Company configuration tables. Existing exact financial/stock facts are not rewritten. |

## Migration and deployment

[Catalog 0214](../dbs/catalog/versions/0214_adoption_resolution_version.py) adds
one non-null integer column with server default 1. The model, native field
registry, read schemas, preview schema, generated OpenAPI/client and test factory
are synchronized. Native adoption alone selects version 2; the commit body cannot
set it. No historical data update or replacement configuration store is added.

The disposable MySQL checks passed the complete chain, additive row/evidence
preservation, old-only downgrade/reupgrade and refusal of rollback after version
2 exists. Online rollback validates the retained rows; offline rollback is
intentionally refused. Apply 0214 before deploying the matching Catalog API.
The ordinary application database has not been upgraded in this review.

## Verification and review

The main UI suite passed 238 cases and the supporting consumer suite passed 167
(405 UI cases in total). The actual React/shared-CSS browser review
passed 42 Company-flow checks and 30 adoption checks at 1440px/390px in light,
dark and ledger themes, without overflow or browser errors. The mobile adoption
confirmation was visually inspected. Strict mypy passed for all 354 Catalog
source files; console TypeScript, Ruff and generated contract freshness passed.
Four dedicated MySQL cases passed; Docker-only verification is separately skipped
when Docker is unavailable.

159 distinct native cases passed across the correction, consumer, publication,
product setup, import, quantity, activation, BOM, pricing and category suites.
The initial correction batch passed 23 cases, the specialized batch passed 40,
and both active dated-category checks passed. The broad integration run passed
90/91; its remaining fixture still attempted retired TYPE ownership. It now
publishes inventory/multi-level pricing for the Company default type, retaining
its permission assertions; all three profile tests passed. The final
publication/consumer batch passed 31 cases. The five migration contract cases
passed, with the optional Docker case skipped; the standalone activation/version
repeat passed. Counts are deduplicated against 160 collected native cases,
including the skipped Docker case. An initial
activation invocation hit the existing command timeout under concurrent native
test load; its controlled repeat passed, including version 2 adoption, immutable
activation evidence and idempotent replay. The production timeout is unchanged.

Manual CLAUDE.md sections 5/6 review covers tenant/company object admission,
field-policy checks for the new marker, strict inputs, server-controlled writes,
signed preview freshness, audit/idempotent replay, bounded source selection,
exact quantities/prices and immutable historical records. `/simplify` and
`/security-review` are unavailable in this session; the checks are performed
manually. No grants, active products or financial facts are directly manipulated.
Final simplification uses the strictly validated default type IDs directly in
publication queries, avoiding two redundant generic resolutions per preview.

No unresolved functional finding remains in this reviewed scope. The CSV has
29 reusable cases: 27 PASS and two NOT_RUN for application rollout and live VM
login. This does not include a deployment or publication of repository commits.

## Reuse

Run the native regressions from `apis/catalog` with
`.venv/Scripts/python.exe -m pytest tests/test_company_configuration_consumers.py tests/test_company_product_configuration.py tests/test_configuration_profiles.py tests/test_configuration_corrections.py tests/test_configuration_ui_contract.py -q`.
Run UI tests from `mfes/apps/console` with
`pnpm exec vitest run tests/company-product-configuration.test.tsx tests/product-configuration-ui.test.tsx tests/product-configuration-workflows.test.tsx tests/product-entry-consumption-ui.test.tsx`.
The CSV links the remaining consumer suites by area. The MySQL migration tests
require `QA_MYSQL_SERVER_URL` pointing to the dedicated local 13396 test server
with no database selected; they create and remove isolated random schemas.

Evidence is under `.test_artifacts/company-configuration-consumers-*`. The native
API tests use isolated databases and signed policy sources; browser checks use
fixture BFF responses with actual components/styles. The combined VM is shut
down, so live tenant login/publication is NOT_RUN and is not represented as an
end-to-end deployed-tenant pass.
