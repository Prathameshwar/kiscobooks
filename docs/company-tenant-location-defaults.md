# Tenant location suggestions for new companies

1. Completed: expose the authenticated tenant's existing country/state defaults in the session response. Database models and company-create validation are unchanged; Identity OpenAPI and SDK 0.2.29 were regenerated.
2. Completed: carry the defaults into the company wizard. Select only an available supported country and its available state. Fields stay editable, manual selections are preserved and country changes clear the state. A tenant change resets the wizard.
3. Completed: 86 UI/session/navigation checks, 14 Identity session/auth/isolation checks and 8 SDK tests passed. Console/Auth TypeScript, generated-contract checks, Ruff and schema mypy passed. Manual simplification and security reviews checked asynchronous selection, explicit submissions and current-tenant isolation; no unresolved findings remain. Repository slash review commands were unavailable, so equivalent manual reviews were used.

Tenant location values are starting suggestions for creation. Companies retain their own explicitly submitted values, and later tenant changes do not update existing companies.
