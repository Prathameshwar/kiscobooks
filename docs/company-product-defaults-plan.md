# Company Default product type and group

User authorized permanent automatic creation and catch-up for existing companies.

1. Reproduce the missing company defaults in the existing Catalog source-refresh
   workflow. Record reuse, tenant/company isolation and retry expectations.
2. Add one fixed Catalog-owned starter definition: type `Default` (BOTH) and group
   `Default` (BOTH), code `DEFAULT`. A newly created type receives a minimal published
   baseline with no tracking or required brand/manufacturer/expiry; stock mode is
   available only when the verified company has inventory enabled. Keep existing
   Default records, published configuration and all General/custom records intact.
   Serialize under the existing company policy lock, emit system audit evidence and
   retry from the normal enrollment refresh. Inactive/conflicting defaults require
   review rather than silent overwrites.
3. Replace the wizard's client-created General group with read-only verification of
   the provisioned Default pair. Preserve scoped permissions, bounded waiting and
   retry of remaining steps. The worker covers API-created and enrolled existing
   companies independently of the wizard; no application DB manipulation is needed.
   Final review refinement: verify a published type revision through the existing
   bounded, parent-scoped read API before declaring the pair ready. Existing drafts
   require review and are never silently published.
4. Run affected native-storage, source-worker and wizard regressions, static checks,
   final simplification/security review and document the backfill execution state.
   With VM services offline, live existing-company catch-up runs when its normal
   worker resumes; local verification must not be labelled a live backfill.

## Todo

- [x] Inspect current provisioning: UI creates GENERAL; source worker has no type/group defaults.
- [x] Reproduce missing defaults before fixing: source refresh created zero types/groups.
- [x] Permanent audited, scoped, idempotent provisioner and worker integration.
- [x] Wizard Default readiness, published-revision verification and retry.
- [x] Existing-company catch-up command and retained-customization regressions.
- [x] Local checks and simplification/security review; dated result record.
- [ ] Live existing-company catch-up: attempted but Identity enrollment API is offline;
      it failed before company processing. Resume/restart the updated normal worker
      or use the documented one-shot command when services return.

Code and disposable-storage verification are complete. Live application backfill
and a new live company/wizard check remain unverified. See
[review](company-product-defaults-review-2026-10-30.md) and
[CSV](company-product-defaults-results-2026-10-30.csv).
