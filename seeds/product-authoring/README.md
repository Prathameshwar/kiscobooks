# Legacy company authoring compatibility

Run the Catalog 0210 schema migration, then prepare a complete authorized Identity
company roster at a coordinated cutoff. Pause company creation for roster capture
and seed application, or reconcile all creations through the cutoff before release.
Do not infer company age from Catalog projections or existing products.

The JSON manifest shape is:

```json
{
  "source": "identity-company-roster",
  "complete": true,
  "cutoff_at": "2026-10-28T00:00:00+00:00",
  "companies": [{"tenant_id": "<tenant UUID>", "company_id": "<company UUID>"}]
}
```

From `apis/catalog`, set `CATALOG_DATABASE_URL` securely in the process environment
and run `uv run python tools/seed_product_authoring.py --manifest <path> --operator <UUID>`.
Review the dry run; add `--apply` to seed the compatibility rows. A re-run leaves
existing settings untouched. Each inserted row and its audit event commit together.

Only roster companies get advanced mode. Companies created after the cutoff use
the simple fallback without requiring asynchronous bootstrap to finish. Install
the full API release only after the seed and cutoff reconciliation are complete.
This procedure does not enable operational inventory features or alter stock.
