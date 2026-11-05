# Independent database migrations

Each service owns its models and its `dbs/<service>/alembic.ini` migration chain.
The Windows service registry in `start/win/conf/services.json` supplies the project,
database name, environment prefix and migration location. Apply reviewed forward
migrations explicitly using a DDL connection before starting updated APIs. Runtime
accounts remain restricted; startup readiness does not apply or stamp migrations.
Keep seed data separate in `seeds/` and preserve applied revision history.

## Read-only synchronization check

From the repository root, after installing each service's dependencies:

```powershell
uv run --project apis/identity python dbs/verify_sync.py
uv run --project apis/identity python dbs/verify_sync.py --service design
```

The command launches each service's own virtual-environment interpreter and reads
only its database URL from the private `start/win/env/<service>.env` file. It checks
the launcher mapping, model table inventory, database/migration/readiness revisions,
Alembic comparison and native primary/foreign/check constraints, generated columns,
explicit collations and table options. It never creates, migrates, stamps or drops
database objects. Missing configuration or drift produces a nonzero exit status.

JSON output contains service names and comparison results, without database URLs
or credentials. Use `--output-dir .tools/schema-review` to retain summaries locally.
Common MySQL expression rendering is compared structurally, preserving operator
precedence and string literals; unsupported syntax is compared conservatively and
may require manual review. This checks schemas, not reference seed contents or
application behavior. Repeat after model or migration changes.

The current local heads, repairs and backup evidence are recorded in
[local-schema-sync.md](../docs/local-schema-sync.md).
