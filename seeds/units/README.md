# Company unit defaults

New company enrollment and the Console creation wizard automatically provision the
packaged `catalog/seeds/unit_defaults_v1.json` through the same Catalog transaction.
Active companies receive 4 count/service units and their 4 canonical declarations.
With inventory enabled, the total is 17 units, 17 exact declarations and 8 pack labels.
The worker also covers companies created through APIs and later inventory enabling.

Optional operator backfill, from the unchanged repository root:

```powershell
uv run --project apis/catalog python -m seeds.units --env-file start/win/env/catalog.env
```

Use the existing configured worker/service credentials. The command discovers only
authorized enrolled companies, verifies their current Identity snapshots, runs the
normal defaults (including tax defaults), and fails on errors. No direct SQL grants,
DDL, fabricated users or arbitrary tax/unit values are accepted.

Existing records are not updated, reactivated or reinterpreted. Container capacities,
months, workdays, density and SKU quantities are deliberately product-specific.
Native screens support further units, pack labels and exact immutable conversions.
See [delivery decisions](../../docs/company-unit-defaults.md).
