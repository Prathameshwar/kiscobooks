# Product detail design review — 2026-11-07

The simple product, advanced SKU and product profile detail pages now share a polished presentation: a themed identity header, visible code/status chips, grouped facts, section navigation and separate trading/record information cards. Desktop cards stack on smaller screens. Native scalar details use readable definition lists instead of disabled edit controls. Reference and custom-field controls retain their existing resolution and permission behavior.

The edit forms, command handling, revision checks and management workflows are retained. Unsupported secondary-button classes on the simple record's header/footer and advanced record's edit action were replaced with the shared ghost-button style. Section targets accept keyboard focus. Shared styling uses defined design tokens and remains scoped to product details.

Validation:

- Console TypeScript passes.
- Actual React/JSDOM component regressions pass for presentation, protected fields, denied reference access, all three detail routes, signed Simple edit saves and read-only access. Opening details makes no writes.
- Chromium checks pass for 45 combinations: simple/SKU/profile × light/dark/ledger × 1440/1024/768/390/320px. No horizontal overflow; section navigation moves keyboard focus to its target.
- Six desktop/mobile screenshots were inspected with the real shared CSS and bundled Inter font. Artifacts are under `.test_artifacts/product-detail-design/`.
- All referenced style tokens exist, no literal palette colors were introduced, and whitespace checks pass for task files.

Review found no remaining defect in the redesigned presentation. References still delegate tenant and read-access checks to the existing reference component; denied fields are excluded from both header metadata and body sections. No write authority, audit behavior or stock/money logic was added. The requested `/simplify` and `/security-review` commands are unavailable in this session; equivalent focused code and permission reviews were performed manually.

Limitations: normal Vitest startup is blocked by `spawn EPERM` when starting esbuild. Browser checks use fixture markup rendered by actual components on the existing headless browser; they do not verify a deployed app or live company data. Existing custom-field controls remain disabled in read view. VM deployment was not performed.

Shared UI version is `0.1.75`. The two workspace consumers resolve it via `link:../../packages/ui`; the pnpm lockfile already records those links and needs no numeric version change.
