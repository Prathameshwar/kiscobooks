# Accounting master release and rollback

This is a local implementation release procedure, not authorization to deploy. Scope is the
approved [completion plan](accounting-masters-completion-plan.md). Follow the
[live todo](accounting-masters-todo.md) for actual verification status.

## Contents and compatibility

Migration head 0072; metadata version 1; template version 3. There are 38 service tables:
29 business masters, two workflow evidence tables, three shared message/idempotency/outbox
tables and four reference replicas. The base chart has 28 groups (15 primary, 13 subgroup).
The GST extension adds Tax Recoverables separately.

Existing resource URLs and historical receipts/bindings remain compatible. Group aliases and
metadata are additive. Export response contracts are now resource-specific. Decimal writes
are documented as strings and reject floats. Query filters are resource-specific and rejected
when unsupported or unreadable. See the [matrix](accounting-master-matrix.json).

## Apply to an existing installation

1. Take a consistent backup and inventory existing tenant/company setup IDs. Record the
   intended migration URL in deployment configuration and the operator's user ID. Keep old
   writers stopped during the schema/data transition; old binaries do not enforce the marker.
2. From the repository root, run the committed migration chain against that configured target:

   ```powershell
   apis/accounting/.venv/Scripts/python.exe -m alembic -c dbs/accounting/alembic.ini upgrade head
   ```

3. From `apis/accounting`, use the same `ACCOUNTING_DATABASE_URL` and backfill each existing
   company explicitly. Replace the placeholders with reviewed UUIDs:

   ```powershell
   .venv/Scripts/python.exe -m accounting.seeds.master_metadata --tenant-id <tenant-uuid> --company-id <company-uuid> --actor-id <operator-uuid>
   ```

   The trusted deployment command takes a company lock, validates the hierarchy, derives
   metadata and writes revision/outbox evidence in one transaction. It preserves all IDs,
   names, links and receipts. Failure rolls back the marker and all data effects. Fix the
   reported underlying hierarchy problem using an approved reconciliation, then retry;
   repeating a completed backfill does nothing. Unsupported metadata versions fail closed.
   Readiness and company data paths, including saved command replays, refuse pending metadata.
4. Deploy the updated Identity field contract with the Accounting binary and typed client.
   Check readiness and scoped reads. Fresh companies initialize at metadata version 1;
   do not backfill them or create setup rows outside the supported initialization API.
5. Use `/accounting-setup/preview` then `/accounting-setup/install` with current scoped
   credentials and a new idempotency key to apply template v3 per selection. This is separate
   from metadata backfill. Inspect conflicts; financially used Reserves subtrees are never
   force-moved. Legacy custom names and v1/v2 bindings remain historical evidence.
6. Configure the supervised audit publisher and Audit source credentials as described in the
   [API README](../apis/accounting/README.md#audit-publisher). Include the exact current
   `AUDIT_EVENTS` set, including group aliases, setup metadata upgrade and setup update. Check confirmed
   publication and consumer deduplication before returning to normal operation.

## Rollback limits

Prefer restoring a consistent pre-upgrade backup and matching application version during a
failed deployment window. Never run an older binary against partially upgraded company data.
Every new DDL revision has a downgrade; the disposable native harness exercises a fresh
upgrade/down-to-base/up sequence. A populated production downgrade has additional conditions:

- Reversing 0061 restores a non-null company registration on tax profiles. Registration-free
  duty profiles must be reconciled before that DDL can succeed; never fabricate registrations.
- Reversing 0070 restores the old address-use uniqueness. General and registration-scoped
  uses of the same address/purpose must be reconciled before restoring that narrower key.
- Dropping new metadata columns or the alias table discards their new data. A schema downgrade
  does not undo template hierarchy edits, metadata audit events or new versioned bindings.
  Preserve evidence and restore the consistent backup when a semantic reversal is required.

No migration/backfill/release command in this procedure has been run on an application database
as part of the implementation tests. Native harnesses create and remove only their own random
`accounting_test_` schemas on the loopback test server.
