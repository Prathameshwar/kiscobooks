# Reusable searchable dropdown review

Requested on 2026-10-24. `@janso/ui` owns `SearchSelect`, the shared single/multiple
entity selector and listed autocomplete (WAI-ARIA combobox, `aria-autocomplete=list`).
Small fixed choices continue to use native `Select`. A free-text suggestion mode
is optional clarification; entity references continue to require a listed choice.

## Delivery phases

1. Reproduce shared-control interaction and async defects with failing tests.
   Fix query invalidation, keyboard retry, dialog dismissal, IME input,
   unresolved/removable selections and native validation. Preserve bounded
   results, selected IDs, caller-owned loading and centralized styles.
2. Review asynchronous creation and explicit lookup context changes; correct
   shared consumers where they supply invented option labels. Update the shared
   package version, workspace lockfile and design-system contract/decision log.
3. Run shared UI and consuming-app suites, type checks and production builds.
   Inspect desktop/mobile, keyboard and dialog behavior in a real browser;
   record simplification, security/correctness review and remaining limitations.

The user authorized implementation and review. Existing master, tenant/company
and launcher changes in this workspace are preserved. No publishing is requested.

## Execution

All three phases complete. Final verification passed.

- Confirmed 16 interaction/async regressions failing before their fixes, then eight
  creation/context regressions. A final regression reproduced native `readonly`
  bypassing required validation during creation. All 25 focused cases now pass.
- `SearchSelect` remains the reusable listed autocomplete and single/multiple
  dropdown: typing searches suggestions and explicit selection commits entity IDs.
- New queries invalidate responses immediately; IME waits for composition end.
  Retry is reachable with Enter and preserves failed page cursors. Escape stays
  within the dropdown until it has dismissed/cleared its own interaction state.
- Attached the missing input ref and repaired toggle, clear, chip removal and
  programmatic blur behavior. Unknown IDs stay visible; inactive selections can
  be removed. Required validity checks committed IDs even while creation is pending.
- Creation locks edits, uses the latest controlled selection and ignores stale
  completions after closing, unmounting, disabling or changing lookup scope.
  It is offered only after complete results establish no exact match. The historical
  paging/highlight test now checks the last entity row because creation is deferred
  until the final page; its identity-preservation assertion remains intact.
- `scopeKey` resets lookup state through a keyed internal component. Attribute
  definition/unit and dynamic custom-field consumers supply dataset identities.
  Removed fabricated selected labels from dynamic custom fields so resolved names
  survive a selection. Attribute master option lookups also include company/definition.
- Shared UI version bumped from 0.1.17 to 0.1.18. Ran workspace
  `pnpm install --lockfile-only --ignore-scripts` successfully. Both consuming apps
  use `workspace:*` links, so the lockfile has no package-resolution change.

## Final review

Manual simplification and the CLAUDE.md §5/§6 checks were performed; slash-command
review tools are unavailable in this session. No unresolved findings in the changed
control. Lookup loaders, permission checks, entity labels, formatting and server
idempotency stay caller-owned. The component makes no API requests by itself and
adds no dependency. Dataset changes discard cached labels and stale callbacks;
controlled IDs remain the caller's responsibility. Client creation guards cannot
cancel an already-issued server write.

## Verification

| Check | Result |
|---|---|
| Shared UI suite | 59 files, 1,821 tests passed |
| Console suite | 96 files, 1,069 tests passed |
| Auth UI suite | 15 files, 141 tests passed |
| Auth server suite | 8 files, 74 passed, 1 existing test skipped |
| Shared UI coverage | Statements/lines 99.31% → 99.32%; branches 94.32% → 94.54%; functions 99.36% → 99.37%; all gates pass |
| SearchSelect coverage | 100% statements, lines and functions; 96.63% branches |
| TypeScript | Shared UI, console and auth pass |
| Production builds | Console and auth pass using separate temporary build directories |
| Shared-control browser review | Light/dark/ledger × 1440/390 widths; no browser errors or horizontal overflow |
| Three-master browser review | 50 scenarios at desktop/mobile widths passed; no browser errors |
| Diff hygiene | Task files checked; generated Next config changes restored |

Browser checks exercise real shared controls with caller-provided fixture data,
including desktop/mobile widths and light/dark/ledger themes. They cover scrolling
the active row, selection, native validity, focus restoration, removal of unknown
and inactive selections, remote retry, creation edit locking and dialog dismissal.
They do not replace device testing with an actual mobile keyboard or a screen reader.

Existing unrelated workspace edits were preserved. No commit or publication was
requested. Temporary browser fixtures, screenshots, logs and build outputs remain
under ignored review paths; development build output is preserved.
