# Product detail presentation

Authorized scope: redesign the product detail page with polished shared CSS, readable information and responsive layouts. Preserve existing editing, permission checks, reference resolution and management actions. VM deployment remains deferred.

1. Review simple product and advanced SKU/Profile detail rendering and shared design tokens.
2. Add a shared product detail presentation: identity header, status, grouped facts, trading information and contextual navigation. Integrate both detail paths while preserving their edit forms.
3. Add centralized theme-aware CSS, mobile layouts and accessibility checks.
4. Run component regressions, TypeScript and browser layout checks; inspect rendered artifacts and record limitations.

- [x] Review existing rendering and styling.
- [x] Detail presentation and both entry paths.
- [x] Shared styling and responsive layout.
- [x] Component regressions, TypeScript, visual review and final verification.

Completed and deployed. See [review and validation](product-detail-design-review-2026-11-07.md) and the [VM deployment record](vm-latest-build-2026-11-07.md). Local Vitest was blocked by Windows esbuild process creation; the normal Console suite subsequently passed on the VM, including the product-detail tests.


Latest deployment status: the fixes were built and deployed on 2026-11-07. See [VM deployment verification](vm-latest-build-2026-11-07.md). Earlier deferred/local-only statements above record the prior implementation stage.
