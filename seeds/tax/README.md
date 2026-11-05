# Company tax starter masters

New GST-enabled Indian companies are provisioned automatically by Catalog's
existing Identity source worker. The Console company wizard also waits for the
same bounded bootstrap before opening the new company.

For an operator backfill using an existing configured private environment:

```powershell
uv run --project apis/catalog python -m seeds.tax --env-file start/win/env/catalog.env
```

This uses authenticated enrollment discovery and verified snapshots. It accepts
no authored rates, tenant/company IDs or impersonated users. A failed refresh or
provisioning attempt fails the command, allowing a safe retry. No DDL is performed.

The canonical packaged seed data is
`apis/catalog/src/catalog/seeds/tax_defaults_v2.json`. Its source references and
SHA-256 values identify the exact official documents reviewed for this pack.
Runtime never downloads or guesses tax rates. All percentages are decimal strings.

The current pack contains five categories, thirteen HSN/SAC classifications, twenty
generic goods/service rules and forty-eight dated rates. Taxable and nil-rated
rules have all three supply contexts; exempt/non-GST rules carry no rate rows.
Goods choices include 0.1%, 0.25%, 1.5%, 3%, 5%, 12%, 18% and 40%; services include
1.5%, 5%, 7.5%, 12%, 18% and 40%. Concessional/conditional entries are labelled.
These are explicitly selected templates, not automatic statutory eligibility.
Nil-rated, exempt and non-GST are separate. Zero-rated exports/SEZ, special cess,
valuation adjustments, ITC and reverse charge require their applicable setup.
The removed 28% goods schedule is not a current starter choice. No company,
product group or product tax binding is created automatically. Users choose the
applicable rule for each product using the existing controls.

Apply Catalog migration **0215** before deploying the new provisioner. It adds an
explicit immutable classification scope, defaulting existing rules to `SPECIFIC`.
Generic rules use `ANY`; an empty specific applicability list still blocks use.
Rollback refuses while generic templates exist, to preserve their meaning.

Existing codes, activation choices and dated histories are preserved. Only exact,
unedited version-one starter labels are renamed to rate plus HSN/SAC. Edited or
revised definitions are preserved. The immutable version-one manifest remains in
the package for provenance. Re-running the command also backfills the generic choices.
New history starts no earlier than the company's current business date and the
pack's statutory effective date. Adding/replacing dated tax definitions continues
through the normal reviewed publication workflow. A later statutory pack must be
reviewed and versioned; old company history must never be silently overwritten.
