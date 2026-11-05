# Invoice Designer service (`design`)

Document **layout**: templates, immutable layout versions, routing rules, brand assets,
reusable blocks and print evidence. It decides what a document looks like and never what
it says — no amount, no tax, no number, no posting. It also renders nothing: it answers
"which layout, and what is in it" and records "this artifact came from that version".

[docs/invoice-design.md](../../docs/invoice-design.md) governs this service; read it
before changing anything here. Its §9 lists the open questions — chiefly the renderer and
object storage — and they are not answered anywhere in this code.

## Running it

Configuration has **no defaults**: `DESIGN_DATABASE_URL`,
`DESIGN_ACTOR_SIGNING_SECRET` and `DESIGN_CURSOR_SIGNING_SECRET` (32+ characters each)
must come from the environment or a secret manager. The audit publisher additionally needs
`DESIGN_AUDIT_BROKER_URL`, `DESIGN_AUDIT_BROKER_USER` and `DESIGN_AUDIT_EVENT_SECRET`.

```bash
uv run pytest --cov                     # suites and the 90% floor
uv run ruff check . && uv run mypy src tests tools
uv run python tools/export_openapi.py   # regenerate openapi.json
DESIGN_TEST_MYSQL_SERVER_URL=... uv run python tools/mysql_smoke.py  # real-dialect check
python -m design.tasks.audit_publisher  # drain the outbox onto platform.audit
```

Migrations live in `dbs/design/` (head `0008`), one DDL statement per revision. Port 8014
locally, routed at `/design/`.

## What a change here has to respect

- **Authentication** is the gateway-signed actor context, verified never minted. There is
  no unsigned test path; the suites sign their contexts through the production code path.
- **Authorization** is per route *and* per object: a `design.*` key checked against the
  row's own company, or against tenant scope for a shared row.
- **A child row is fetched through its parent.** A version id alone must never resolve —
  that was a real cross-company read and publish.
- **The canvas is attacker-controlled input.** `extra="forbid"`, typed styling, an
  allowlist of binding roots, bounded counts, no compiled HTML or CSS, and asset and
  component references validated when stored.
- **Every state change emits its audit event on the same session**, through the outbox.
- **One lifecycle mechanism per entity**, asserted by `tests/test_service_contract.py`
  along with singular table names and `DECIMAL(19,4)` measurements.

Tests run against an in-memory SQLite schema, so they do not prove MySQL dialect
behaviour — `tools/mysql_smoke.py` does, on a throwaway schema it drops afterwards, and
the migration chain is recorded in
[docs/local-schema-sync.md](../../docs/local-schema-sync.md).
