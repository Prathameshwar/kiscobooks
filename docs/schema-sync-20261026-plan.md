# Database, models and scripts synchronization

1. Completed: checked all eight service model inventories, independent Alembic heads, live schemas and launcher mappings. All 461 tables match. Corrected Notification's model constraint name to the existing revision 0113 definition.
2. Completed: restored the Design SQL backup in rehearsal, preserved all six legacy tables and 98 rows in an archive schema, and applied the existing eight migrations. Upgrade/downgrade/re-upgrade and retained-row hashes passed.
3. Completed: provided the private Design runtime environment and a database account with DML-only grants on its schema. Verified cross-service reads are denied. Design now reports ready on 8014.
4. Completed: added the reusable read-only verifier with per-service interpreter isolation, native constraint/table checks and structural SQL expression comparison. Final verification reports zero drift across all eight services.
5. Completed: affected tests, lint/type checks and manual simplification/security reviews passed. All twelve backend component probes are UP. Evidence and limitations are recorded in [local-schema-sync.md](local-schema-sync.md).

The password-recovery delivery remains owned by Authentik and introduces no billing password or recovery-token table.
