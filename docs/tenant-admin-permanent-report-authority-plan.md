# Permanent tenant administrator report authority

User decision, 2026-10-29: add the missing capabilities permanently and make the
tenant administrator ready, rather than depending on a temporary QA grant.

The later user-approved [opening policy](tenant-admin-permanent-opening-authority-plan.md)
adds native finance/journal authority to this same role. This report plan records
the earlier reporting change; its read-only job behavior remains unchanged.

1. Add `report.read`, `report.export`, `report.definition.manage` and the existing
   complete-input financial read keys to the canonical Tenant Administrator role.
   Update the governing role decision and literal catalogue tests. These keys create
   read-only source/report/export jobs; financial posting/closing and self-approval
   remain separate authorities and release prerequisites.
2. Provide an authenticated, fresh platform-operator catalogue reconciliation API.
   It applies only the fixed shipped system-role seed, preserving role identities,
   assignments and tenant-custom roles. Preview exposes a current-state fingerprint;
   apply requires that fingerprint, a reason and an idempotency key. Audit the actor
   and change in the same transaction. Broad cache changes remain bounded by the
   documented TTL; no token or user permission set is rewritten.
3. Regenerate the existing Identity API client and add the platform UI preview/apply
   workflow. Verify unauthenticated, unconfigured operator, ordinary tenant, stale
   preview, unexpected input, replay, rollback and custom-role preservation cases.
4. Apply through the actual authenticated platform UI/API, then verify the retained
   administrator's reporting capabilities and complete the three-company report
   source/run/export acceptance. Financial operator provisioning/approval and C1/C2/C3
   work retain their separately recorded contracts.

The existing ordinary role editor/assignment guards remain applicable. No request
accepts caller-supplied permission keys for a system role, a wildcard grant, or an
application database connection. The installation's current configured operator
remains the authority for applying a changed shipped catalogue.
