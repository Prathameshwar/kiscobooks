# Company configuration layout and tax applicability review

Scope approved by the user's 2026-11-02 request: improve the company details and
GST sections on `/companies/:id/configuration`, and explain non-GST/VAT behavior.
VAT was confirmed by the user. Preserve the existing company editor, statutory
contracts, permission gates and concurrent work.

## Phases

1. Review the page, shared design primitives and tax contracts; reproduce layout
   and applicability gaps with regressions.
2. Improve the company summary and separate registration history, entry,
   reporting profiles and closure controls. Reuse centralized styles and shared
   responsive form primitives. Keep registration and profile forms closed until
   requested, and disable controls during requests.
3. Add a tax applicability view for VAT/no-registration defaults using existing
   scoped reads. Distinguish the default framework from dated registration facts.
   Do not invent country/tax choices or apply India GST controls to foreign VAT.
4. Run affected UI/type checks and browser layout checks in light/dark/ledger at
   desktop, tablet and mobile widths. Repeat simplification and security review;
   record findings, fixes, evidence and remaining limitations.

## Findings and evidence

| Finding | Fix and verification |
|---|---|
| Company details were one undifferentiated list with a raw tax-system code. | Separate business identity and regional/financial summaries; reuse readable tax labels and configured date formatting. Regression reproduced the missing groups. |
| Company header actions squeezed the mobile company name into about 47px. | Give Refresh its own action row; retain a status badge beside the company name. Browser regression measured the squeeze before the fix and now checks readable heading width. |
| GST entry and reporting controls were compressed inside filter toolbars. | Use existing FieldGrid, FieldGroup, FieldPair and FormActions with full-width long fields, paired short fields, required marks and aligned actions. Regression reproduced the compressed structure. |
| Registration history, reporting history and closing controls formed one dense card; reporting entry was always visible. | Separate the two histories into cards, open entry on explicit request, place actions below headings, and put dated closure controls in disclosures. |
| VAT and other defaults had no tax applicability view. | Show actual dated tax-registration records through the existing scoped API with cursor paging, read/error/retry states and readable framework names. Explain default versus registration facts. |
| Businesses without GSTIN had no guidance and could interpret the default as registration status. | Explain that the list can remain empty without inventing a GSTIN; a missing record is not evidence of exemption. Keep all server-provided regime choices and historical treatment. |
| Inputs/actions remained usable during GST writes, including duplicate form submission. | Freeze fields/cancellation, guard concurrent actions and preserve idempotency keys for unchanged failed registration payloads. Pending/retry regressions pass. |
| Root Refresh, feature changes and navigation could discard an inline tax draft. | Aggregate registration/reporting form activity into the existing page draft guard; disable Refresh and conflicting feature changes, confirm Back, and block context changes while pending. Regression reproduced the enabled destructive refresh path. |
| Replacing accepted reporting evidence with an oversized file retained the old accepted proof. | Clear proof before validating each replacement. Regression reproduced the still-enabled Save button after rejection. |
| GST report links could use the working-company context while reviewing a different company. | Offer those links only for the currently selected company with its scoped report-read grant. Registration management remains governed by server-returned capability. |

## Verification

- Initial regressions: **5 failed, 37 passed**, reproducing summary, applicability,
  compressed-form and always-visible-entry gaps before fixes.
- Expanded affected set: **208 tests passed across 10 suites**, including company
  editing, labels, page/navigation, proxy allowlist, permission and tax-history checks.
  Final action-row and heading changes passed **55 affected tests across 4 suites**;
  the registration/report-link suite then passed **7 tests**.
- Evidence replacement and page draft-loss regressions failed before their fixes.
- Browser checks use production React DOM and centralized styles with disposable
  fixture responses; no business records are changed. The initial capture was
  corrected to wait for loaded reporting data and include the host's real base
  palette. Mobile heading-width failures then reproduced the roughly 47px squeeze.
  Final browser verification passed all **36 scenario/width/theme checks**: GST
  history, expanded GST entry, VAT history and the `none` read view at **1440px,
  768px and 390px**, each in light, dark and ledger. Checks include document/control
  bounds, readable heading widths and responsive summary placement. Screenshots
  were inspected, including the expanded mobile dark view.
  Evidence: `.tools/company-configuration-layout-review/` (36 screenshots), with
  `.tools/company-configuration-layout-browser-final.log` and adjacent regression logs.
  Browser instances were closed after each scenario. These are layout checks with
  fixture API data, not a live-company mutation or end-to-end tax certification.
- Final console TypeScript and task-file whitespace checks passed.

## Tax behavior and remaining boundaries

- India companies use the GST framework as a setup default. That choice does not
  establish that the business owns a GSTIN. Dated registrations and their regimes
  govern the existing tax contracts; composition is a GST regime.
- The shipped company setup profiles currently cover **India GST and UK VAT**.
  A catalogue label does not establish that another jurisdiction is implemented.
- The `none` read view handles that stored/default value without claiming exemption
  or erasing registration history. This change does **not** add `none` to the
  countries' creation/edit choices: the current profiles do not offer it.
- VAT history is now visible. **VAT registration creation/editing on this page
  remains unavailable**; the GST-only setup metadata cannot safely author it.
  India state VAT is a separate planned tax extension, not foreign VAT support.
- No tax computation, backend schema/API, statutory dates, permissions, dependency,
  company data or provider settings changed. No commit/publication was requested.

## Final review

Review uses CLAUDE.md security/correctness invariants: scoped reads and server-owned
management authority, field-read omissions, existing typed statutory payloads,
date-effective history, decimal strings, bounded paging, replay keys, draft protection
and safe evidence handling. Shared design primitives supply the styles; no app-local
CSS was added. The named simplify/security-review commands are unavailable, so those
reviews were performed manually. No remaining blocking finding within this layout
and applicability scope. The sequential review/fix/retest loop is complete; VAT
authoring and the jurisdiction/tax extensions remain the explicit boundaries above.

## GST spacing follow-up (2026-11-02)

The header-to-guidance gap measured **28px**: `CardBody`'s 24px top padding
plus the first meta paragraph's 4px margin. The inner page-style flow also used
24px between related guidance, actions and history. Both GST cards now opt in to
the shared `janso-card--compact` class: 12px above the body and between its flow
children, 16px below, with the existing horizontal inset and nested form spacing.

The browser regression failed at the original 28px gap before the fix. All **54
scenario/width/theme checks** then passed, covering saved GST history, expanded
forms, empty registrations, read-only GST, VAT and `none`. The affected console
suites passed **73 tests**; the shared card/content/layout suites passed **46**.
Console TypeScript and task-file whitespace checks passed. Screenshots were
inspected at desktop light and expanded mobile dark; evidence is in
`.tools/company-configuration-spacing-review/` and `.tools/company-gst-spacing-*.log`.
Manual simplification and security/correctness review found no remaining issue:
the change uses scoped direct-child styles and retains existing statutory behavior.
The named review commands remain unavailable. No commit/publication was requested.

## Dedicated GST page follow-up (2026-11-02)

The user's subsequent request moves both GST cards to
`/companies/{companyId}/gst-settings`, entered by the action after Edit company
settings. Configuration no longer mounts GST histories or their draft aggregation.
The dedicated page owns their navigation/refresh guard. See
`company-gst-settings-page.md` for the current implementation, review and evidence;
the inline GST layout and guard references above describe the preceding delivery.
