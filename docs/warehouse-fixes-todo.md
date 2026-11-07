# Warehouse fixes and final review

The user authorized fixes for all eleven findings on 2026-11-07 and requested a review afterwards. Existing application paths and unrelated working-tree changes must be preserved. VM deployment remains deferred.

## Phases

1. Native correctness: W02 effective membership retirement, W05 timezone validation, W07 metadata-only Main provisioning, W04 feature-aware creation metadata, and W03 uncertain standalone-create recovery. Validate targeted APIs and actual UI behavior before continuing.
2. Warehouse management: W01 release publication/delivery recovery/history and W09 product warehouse/replenishment maintenance using existing owner commands and permission checks.
3. Owner integrations: W06 company-owned tax-registration validation, W08 document ship-from context, W10 date-aware warehouse-group reporting, and W11 reservation/operation-aware availability. Keep service contracts, versions, OpenAPI and clients synchronized. Investigate existing owner mechanisms before adding new storage or making policy decisions.
4. Review: relevant regression suites, type/lint/contract checks, simplification and security/correctness review. Record residual limitations explicitly.

## Checklist

- [x] W01 Company release publication, delivery retry/history and retirement recovery UI.
- [x] W02 Effective-date-safe group retirement guard.
- [x] W03 Standalone uncertain-create recovery.
- [x] W04 Feature-aware warehouse creation UI/metadata.
- [x] W05 Native IANA timezone validation.
- [x] W06 Company-owned tax-registration reference validation.
- [x] W07 Inventory-off Main metadata provisioning.
- [x] W08 Warehouse location/address/tax context handoff; Purchase goods validates receiving registration.
- [x] W09 Product warehouse/replenishment policy maintenance UI.
- [x] W10 Date-aware warehouse group reporting integration.
- [x] W11 Operation/product-aware sale eligibility; reservation availability explicitly unavailable, as requested.
- [x] Manual correctness, simplification and security review; available regression and contract checks.
- [ ] Standard Vitest execution: blocked by Windows esbuild spawn EPERM; actual React regressions pass.
- [x] VM deployment and post-deployment readiness/financial checks: [completed 2026-11-07](vm-latest-build-2026-11-07.md). Individual warehouse workflows retain their documented regression coverage; the release check is not an exhaustive live workflow certification.

## Evidence

See [the fix review](warehouse-fixes-review-2026-11-07.md) for evidence and validation limits. Eleven findings have local implementations and targeted regression evidence. This does not certify the VM, which was not updated.

The user explicitly chose to keep reservations disabled. No reservation lifecycle or fabricated zero availability was introduced.


Latest deployment status: the fixes were built and deployed on 2026-11-07. See [VM deployment verification](vm-latest-build-2026-11-07.md). Earlier deferred/local-only statements above record the prior implementation stage.
