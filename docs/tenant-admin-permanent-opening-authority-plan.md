# Permanent Tenant Administrator opening authority

The user requested on 2026-10-30 that opening access work permanently for new
companies and existing Tenant Administrator assignments. This supersedes the
2026-10-22 bootstrap-only policy for `tenant_admin`; `company_admin` keeps its
existing bounded policy.

1. Add the existing native permission set to the canonical Tenant Administrator:
   `accounting.finance.manage`, `ledger.post_journal`, `period.post`,
   `accounting.export.read`, `opening_balance.read`, `opening_balance.manage`,
   `opening_balance.initialize_zero`. Test fresh seeds, reconciliation, retained
   role identities/assignments and company scope. These grants also authorize
   native finance-management and journal operations; they are not an opening-only
   permission family. Do not disguise that broader authority or bypass native
   posting checks.
2. Apply the reviewed fixed catalogue through the existing fresh platform
   operator UI, preserving custom roles and assignments. Verify effective
   permissions for the retained administrator in all three QA companies.
3. Verify editable opening controls, capture/preview and native readiness through
   UI and authenticated API readbacks. Keep fiscal state, first-posted ratchets,
   field policies, audit/idempotency and correction checks. Do not invent
   nonzero migration balances or turn on ordinary voucher/stock release flags.
4. Review security/correctness and record reusable cases and actual outcomes in
   the current findings CSV. Verify future provisioning using the same shipped
   role and seed, rather than a one-off grant to the QA user.

Period close/reopen/lock/adjustment, voucher approval/posting, impersonation and
security-audit self-review are not added to the shipped Tenant Administrator.
Existing custom grants are preserved and must not be confused with the canonical
role's grants. No new permission keys, schema migrations or API contracts are needed.
