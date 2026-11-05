# Simple product API implementation TODO

Authorized 2026-10-28: implement the revised API plan uninterrupted, then review
twice and fix findings. UI implementation remains deferred.

- [x] Phase 1: live company authoring control, migration, rollout seed and tests.
- [x] Phase 2: single-product reads and native field metadata.
- [x] Phase 3: atomic simple creation/editing with legacy compatibility.
- [x] Phase 4: variant guards, ordinary attributes and product child adapters.
- [x] Phase 5: bulk/import adapters and stale work protection.
- [x] Phase 6: stock/opening and operational integration verification.
- [x] Phase 7: documentation, exported contracts and generated API client.
- [x] Review 1: simplification/correctness; fix findings and rerun affected checks.
- [x] Review 2: security/compatibility; fix findings and rerun affected checks.

## Evidence and limitations

Implementation started with extensive unrelated staged/unstaged stock, voucher,
Identity and UI work already present. Preserve it; do not commit or publish.
Record test results and deployment prerequisites here as work completes.

Initial checks: 20 mode/product/legacy/attribute-form tests passed; four simple
bulk/seed tests passed; three ordinary-attribute/setup/field-denial tests passed.
Targeted strict mypy checks passed. Broader regression and native MySQL verification
are in progress. MySQL comparison found the inherited tenant index missing from
the new CREATE statement; the migration was corrected before rerunning.

Deployment requires Catalog migration 0210 and the explicit legacy-company roster
seed before enabling the complete release. No application database was migrated;
native checks use a random, disposable catalog_test_ schema on local MySQL.

Integration results: 32 Accounting stock/opening/GL/tracking/selection/reconciliation
tests, 14 Vouchers stock-capture/enrollment tests and 10 Identity field/role tests
passed. Native MySQL verified model parity, seven simple-product workflows,
concurrent idempotency, three mode-versus-axis races, and upgrade/head ->
downgrade/0131 -> upgrade/head. Test schemas were dropped by the verifier.

Review 1 findings and fixes: ensured MySQL current reads after the company lock,
added three real mode/axis race cases, protected both aggregate versions, isolated
product cursors from native item cursors, reused native bulk alias resolution, and
fixed shared custom-definition serialization in import templates. Seven file-import
and template regression tests passed, including a simple CSV import with distinct
item/shared fields. TypeScript client generation checks, eight client transport
tests and client typechecking passed.

The broad Catalog run completed with 60 passes and one activation-command timeout
(`request is busy`, unchanged 10-second native command budget). The exact failed
activation/custom-field test passed on isolated rerun (16.48 seconds total test
time). No production timeout, permission rule or test assertion was weakened.

Repository slash commands `/simplify` and `/security-review` are not installed in
this session or its local command directories. The two requested reviews are
performed manually against CLAUDE.md sections 5 and 6, with the relevant automated
checks and native database evidence recorded here.

Review 2 findings and fixes: current and retained mode-receipt field permissions
are rechecked; simple imports verify both item and shared field visibility;
manufacturer date order is validated at the public boundary (422, not an internal
adapter error); setup routes declare the standard error envelope; and update
metadata marks fields absent from the product PATCH contract read-only. Native
entity bindings and explicit label overrides remain intact. Native family/item
IDs, financial authority and stock source contracts were preserved.

Final targeted product/mode/feature/bulk/seed/access checks: 18 passed. Additional
metadata regression: one passed. Mode replay tests explicitly verify permission
revocation. Targeted Ruff checks and strict mypy for 17 implementation modules
passed. The legacy package initializer retains pre-existing import-order/late-import
lint findings; this task's model export was placed in the normal import section.
Catalog/Identity OpenAPI and generated client checks, field/audit contract checks,
and TypeScript typechecking passed. There are no remaining unchecked delivery or
review items. Production/local-application rollout is separate: apply migration
0210 and the explicit legacy-company roster seed before deploying the new fallback.

Future UI priority confirmed by the user: clear, simple product creation for business
and ordinary users; familiar labels, understandable layout and the shared style/CSS
system. No duplicate family/SKU cards in simple mode. UI work stays deferred.
