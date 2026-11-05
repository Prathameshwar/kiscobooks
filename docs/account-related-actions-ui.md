# Account related actions UI

Execution plan, 2026-10-25. Scope: the ledger account view and its existing native supplementary workflows.

1. Add the shared split button to the account view. Offer scoped management and creation for aliases, external references, tax/bank profiles, tax defaults, posting defaults and charge policies, with the account's existing edit, lifecycle and history actions.
2. Preserve the account context through creation, save, cancellation and directory navigation. Use native field metadata and validation; check each child's current company grants independently, including posting publication permission. Explain account state/kind restrictions.
3. Run regression tests, review permission and navigation boundaries, fix findings, then verify keyboard/mobile/theme behavior, types and the production build.

No API, model or schema change is planned: these resources already have native endpoints, company scope, field permissions, version checks, audit and idempotent commands. UI shortcuts do not grant authority or bypass native validation.

## Execution evidence

- Phases 1 and 2 complete: the account view reuses `@janso/ui`'s split button beside its existing kebab menu. Each supplementary area offers an account-filtered management link and, with its own company grants, a creation link. Existing Edit, confirmed activation/retirement and history workflows are reused. Linked account groups and parties require readable, visible fields and valid native identifiers.
- Contextual creation protects the account selector, retains the owner in the native request body, and preserves direct or nested account return links. Ordinary creation retains its searchable selector. Conflicting context blocks submission; native field restrictions remain effective.
- Eligibility hints cover retired/unknown status, bank and tax profile kind/unused-draft requirements, active dated defaults, and readable active customer/supplier account attributes for charges. Native reference, head, interval, uniqueness and party-state validation remains authoritative.
- Permission review fixed the missing UI publication check for posting defaults. Independent child read/manage grants are checked for the current company; role labels, expired grants and other-company grants confer no creation action. Native API authorization is unchanged.
- Manual simplification and security reviews completed (slash-command tooling is unavailable). Findings corrected: contextual owner changes, unavailable creation hints, native manage gating, pending/review navigation, empty reader dropdowns, multiple page headings and account-specific region labels on party pages. No money posting or new API/schema contract was introduced.
- Regression baselines confirmed missing split/context protections, the region label defect and protected charge currency attributes before their fixes.
- Browser review: 141 checks across 1440px/390px and light/dark/ledger themes; portalled menu bounds, keyboard navigation/focus, scoped creation, required validation, saved-child return, directory New, dirty-form cancel/discard and reader restrictions passed. Six saves were intercepted local fixtures; zero live business writes, page errors or duplicate browser warnings. Desktop and mobile screenshots were inspected.
- Final affected tests: seven files, 187 tests passed (`.tools/account-related-final-verified-tests.log`). Full Console TypeScript passed (`.tools/account-related-console-types-current.log`). The optimized production build and its type checks passed; the managed Console restarted and reported UP on port 4320 (`.tools/account-related-console-build.log`). Temporary type failures in concurrently edited invoice-designer files resolved in that workstream before the successful checks; no unrelated source was edited for this task.
- All phases complete. Existing API, SDK, database models and migrations remain the source for these workflows; no additional contract or schema change was required.
