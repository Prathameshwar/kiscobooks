# Catalog API

Catalog provides company-scoped product/service definitions, configuration, units and
classification, reusable profiles, commercial pricing, India GST definitions, reviewed
activation, stock-location definitions and bulk administration. Identity supplies verified company, capability and
field-policy context. See [v1 scope](../../docs/catalog-v1-scope.md) for ownership and
release boundaries and [schema](../../docs/catalog-schema.md) for storage details.

## API and operations guides

- [Products and services](../../docs/catalog-products-api.md)
- [Configuration, variants and adoption](../../docs/catalog-v12-api.md)
- [Commercial pricing](../../docs/catalog-v13-api.md)
- [Tax definitions and activation](../../docs/catalog-v14-api.md)
- [Bulk administration and worker recovery](../../docs/catalog-v15-api.md)
- [Stock-location definitions](../../docs/catalog-warehouse-api.md) — locations, groups, bins, operation policies, product location policies, releases and acknowledgement
- [Units](../../docs/catalog-unit-api.md), [classification](../../docs/catalog-classification-api.md) and [reusable profiles](../../docs/catalog-profiles-api.md)
- [Identity source operations](../../docs/catalog-source-operations.md), [custom-index jobs](../../docs/catalog-index-rebuild-api.md) and [audit delivery](../../docs/catalog-audit-delivery.md), [audit contract](../../docs/catalog-audit-contract.md) and [audit operations](../../docs/catalog-audit-operations.md)

## Local development

Use Python 3.12 and the committed lockfile. From this directory:

```powershell
uv sync --frozen
uv run --frozen uvicorn catalog.main:create_app --factory
uv run --frozen python -m catalog.tasks.source_worker
uv run --frozen python -m catalog.tasks.index_worker
uv run --frozen python -m catalog.tasks.audit_publisher
uv run --frozen python -m catalog.tasks.audit_publisher --status
uv run --frozen python tools/export_audit_contract.py --check
uv run --frozen pytest --cov
uv run --frozen ruff check src tests tools ../../dbs/catalog
uv run --frozen mypy src tests tools
uv run --frozen python tools/export_openapi.py --check
```

HTTP and worker are separate supervised processes; supply their required environment credentials
from deployment secret storage. See source operations for allowlists, broker authority and
independent request/response/event keys. Missing or stale Identity context fails closed.

From the repository root, apply migrations only against the intended development database:

```powershell
apis/catalog/.venv/Scripts/python.exe -m alembic -c dbs/catalog/alembic.ini upgrade head
apis/catalog/.venv/Scripts/python.exe -m seeds.reference catalog --dry-run
apis/catalog/.venv/Scripts/python.exe -m seeds.reference catalog
```

Startup does not create/migrate a database. Identity's source artifacts use its own migration
chain 0035-0037. Shared billing-platform dependencies are pinned in each project's lockfile.
Clients live in clients/api-client; export both service OpenAPI contracts before generation.
Audit history is available through the shared console. SQLite and mock broker tests do not
replace live MySQL/RabbitMQ release checks.

For a disposable native-MySQL verification, set `CATALOG_TEST_MYSQL_SERVER_URL` to a loopback
development server URL without a database and run `uv run --frozen python -m tools.mysql_smoke`
from this directory. The tool creates a random `catalog_test_` schema, verifies migrations,
model parity, reference workflows/isolation and concurrent retries, then drops only that schema.
It requires database creation rights and never selects an existing application database.
