# Accounting navigation review

Scope: complete navigation for the ten Accounting masters using the existing Console layout and shared UI controls. Preserve current company grants, native field permissions, lifecycle restrictions and financial command recovery.

1. Add regression coverage for row View/Edit/history links, breadcrumbs, reference destinations, filtered return paths and read-only access. Confirm the navigation gaps before changes.
2. Implement permission-aware row actions and chart setup links; preserve resource directories and detail pages in breadcrumbs. Open verified references from detail pages, including Catalog tax rules, and provide an explicit commercial classification creation path. Keep create-time eligibility filters out of historical reference hydration. Synchronize exchange register filters with its URL.
3. Run the affected UI suites and type checks. Review behavior and security, exercise links, menus and back navigation in the browser at desktop and mobile sizes, fix findings and record evidence.

No new database schema or API contract is planned. Native APIs continue to authorize every destination. Identity bank/tax references will receive links only when implemented detail pages exist.

## Execution

Completed locally. Row menus now provide real View/Edit/history anchors and scoped shortcuts to related directories. Resource/detail breadcrumbs preserve the filtered return trail; chart setup is linked only for a permitted reader. Verified Accounting references and Catalog tax rules open their implemented pages, with field-specific link labels and a return to the originating record. Commercial types have a dated party assignment flow. Exchange register filters are reflected in its URL.

The first review corrected supplier editor breadcrumb wiring, unsupported return paths, and historical reference hydration that incorrectly used create-time ACTIVE filters. The second review found that protected or invalid relationship filters were silently dropped: these now explain the problem and require an explicit clear/change before loading a register. Create-time eligibility and native command recovery remain intact. Bank/tax registration references have no dedicated detail pages and remain readable labels.

Validation: 397 Console tests in 18 suites passed; TypeScript and the final production build passed. Browser fixtures exercised 238 actual navigation checks at 1440px/390px, 426 layout/control checks across light/dark/ledger themes, and 86 protected/invalid filter checks. Browser page errors and business writes were zero. These checks use native-shaped fixtures, without changing live business records. Console was restored and verified UP after its build. Database models, migrations, API schemas and generated contracts needed no change for this navigation follow-up.

The work remains local; nothing was staged or published.
