# Tenant administrator UI findings: implementation plan

User authorized implementation of the 30 October review findings. Preserve local
paths and concurrent printing/company-setting edits; publish only through the
configured mapping when publication is requested.

1. **Controls and existing bugs:** failing regressions first, then shared lookup/
   date/text heights, responsive money fieldgroups/action rows, mode-compatible
   item entry, safe voucher Back navigation, formatted preview/history and truthful
   Audit error/filter presentation (B02–B05, B07, B09–B12).
2. **Review and report flow:** readable native voucher summary, local field errors
   and correction focus, scoped customer-ledger entry, source coverage/readiness
   labels, distinguishable report/export history and automatic workspace reads
   (B06, B08, G02–G04, G08). Validate native readable fields, tenant/company/year
   scope, pending/refused/stale responses and exact decimal presentation.
3. **High: designer responsiveness (B01):** keep the desktop editor unchanged;
   below the content-width threshold use explicit palette/properties panels and a
   compact wrapping toolbar. Only one small-screen panel is open at a time. Keep
   the document stage usable, restore/Undo state intact, Escape/dismiss and focus
   return available, with no save/publish side effect from panel navigation.
4. **High: saved draft discovery/edit (G01):** inspect existing native list/detail/
   revision and replacement contracts; add the scoped directory and canonical
   saved route first, then versioned edits for supported ordinary money and
   account Purchase captures. Preserve captured immutable source evidence unless
   the user explicitly replaces a reference; reload metadata on changed scope/
   date/type; retain uncertain same-key replay and stale-version refusal. Do not
   reopen submitted/approved documents as editable drafts.
5. **High: statutory/goods Purchase and counts (G05/G06):** inspect governing owner
   work and supported contracts before implementation. Company country plus tax
   type selects supported tax behavior; never silently replace tax-bearing input
   with an untaxed profile or enable execution flags. Physical count records
   observations and protected book quantities separately and calculates the
   difference. The owner selected continuing movements with reconciliation against
   a recorded count cutoff. Preserve cutoff and later-movement evidence separately;
   apply the approved delta once to the current stock position. Surplus uses current
   verified native stock cost, with mandatory review when no cost exists. Both policy
   choices are recorded; native count grain/locking and B25/C3 delivery remain.
6. **Invitation acceptance (G07):** preserve the provider-ready contract and
   truthful configured/delivery states. Real receipt requires the already absent
   provider/mailbox settings; no transport credentials or recipient are invented.
7. Run affected unit suites, TypeScript and focused browser/API rechecks across
   Retail, Services and Distribution at 1440/768/390px. Review security, scope,
   stale requests, money display versus capture and code simplification; fix new
   defects and record exact outcomes in a new CSV without rewriting old ledgers.

The phase plans refine the previously approved delivery sequence. They authorize
UI/native contract work; business financial release remains separately governed.

## Todo

- [x] Read instructions, preserve baseline and record phase order.
- [x] B02 shared visible control heights.
- [x] B03 money/related fieldgroups and action layout.
- [x] B04 compatible account/item mode controls.
- [x] B05 contextual voucher Back navigation.
- [x] B07 preview display precision and currency.
- [x] B09 readable history/issue separators.
- [x] B10 failed-list counts stay unavailable.
- [x] B11 readable security-exclusion chip.
- [x] B12 grouped voucher workflow actions.
- [x] G02 automatic readable saved summary.
- [x] B08 field-associated validation/focus.
- [x] B06 selected customer native ledger.
- [x] G03 native ledger coverage presentation and explicit stock compatibility limit.
- [ ] G03 complete native stock capability metadata.
- [x] G04 distinguishable report/export history.
- [x] G08 automatic report workspace reads.
- [x] B01 compact usable designer panels and toolbar.
- [x] G01 scoped directory and supported money/untaxed Purchase versioned edit.
- [ ] G01 dedicated editors for remaining native captures and richer date/type changes.
- [ ] G05 supported statutory/goods workflow, subject to owner prerequisites.
- [x] G06 count cutoff and surplus-cost policies selected and recorded.
- [ ] G06 native physical count owner/API/migrations/review and C3 acceptance.
- [ ] G07 real invitation receipt, subject to provider/mailbox configuration.
- [x] Final affected local checks, review/fixes, reusable recheck and current result CSV.
- [ ] Live three-company post-fix acceptance after VM services return.

## Completed local evidence

- 182 affected Console assertions and 197 shared-control assertions pass. Audit
  and Edge teardown contention from initial concurrent runs resolved in final checks.
- 52 final focused summary/editor/report/reference assertions plus three shared
  label boundary/scope/abort assertions pass; totals overlap earlier suite coverage.
- Final Purchase replacement review reproduced and fixed loss of unrelated stored
  references/parties; 25 final draft/directory/summary/reference assertions pass.
- Six final designer/history browser geometry assertions pass at 1440/768/390px.
  The initial helper cleanup fixture failure in that combined artifact is retained;
  its corrected three-test final suite passes separately.
- Console/shared UI TypeScript pass. The final manual review corrected report form
  submission with an unverified reference and phone history clipping, and consolidated
  duplicated scoped label reads. Full native replacement/replay checks pass for the
  supported draft editor slice.
- [Current review](tenant-admin-ui-fixes-review-2026-10-30.md) and
  [20-row result CSV](tenant-admin-ui-fixes-results-2026-10-30.csv) distinguish
  implemented/partial/native prerequisite states. The VM was shut down by the user;
  live post-fix acceptance is explicitly NOT_RUN, with a reusable runner prepared.
