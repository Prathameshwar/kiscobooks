# Permanent default price plan

User decision, 2026-10-31: provision at least one `Default` price book when a
company is created so adding product prices has an available destination.
`Price book` is the existing `Price plan` master at `/masters/price-plans`.

## Phases

1. Add failing enrollment regression tests. Extend the trusted Catalog company
   source provisioners with audited, company-scoped, idempotent Default sales
   (`DEFAULT_SALES`) and Default purchase (`DEFAULT_PURCHASE`) plans in the verified
   company base currency. Sales attaches to baseline level one; purchase has no level.
   Reuse an existing baseline/currency plan and preserve authored terms/names.
   Do not create product rates or publish monetary data. Periodic refresh catches
   up existing companies and retries failures independently of other defaults.
2. Keep the existing explicit price-level bootstrap contract. Make company setup
   verify the provisioned price plan; use `Price plan` consistently in product
   creation and Pricing pages, and make the Default readily selectable.
3. Test retries, conflicts, audit, rollback, currency, tenant/company isolation and
   UI access/default/override behavior. Apply the provisioner to existing local
   companies through verified facts, run focused checks and review security and
   simplification against CLAUDE.md sections 5/6.

Tax basis for a new starter plan is explicitly EXCLUSIVE. Existing plans retain
their tax basis; a plan only defines how future explicitly entered prices are
interpreted. A starter plan never supplies a fabricated rate or publication.

## Verification

Seven pricing-default backend tests passed with 95.92% coverage of the new
provisioner; the twelve existing company-product-default tests also passed.
Company setup (47), pricing readiness (9) and product creation (36) UI tests passed.
The constrained company price-plan read is covered by the company boundary suite.
Catalog Ruff, strict mypy and OpenAPI freshness checks passed; Console TypeScript
passed. The managed Identity-source worker was restarted with the new provisioner.
Verified local enrollment retained the existing INR sales plan PRICE1/Price1 and
provided DEFAULT_PURCHASE/Default purchase. Subsequent enrollment created nothing.

Manual CLAUDE.md sections 5/6 review found no additional issues: verified source
facts supply currency and scope; the company policy lock serializes provisioning;
existing authored plans are preserved; audit failure rolls back; retries reuse
the plans. No rates, monetary publications or additional permissions were created.
