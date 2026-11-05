# GST and GSTR-3B final review

The subsequent [joint end-to-end review](gst-returns-e2e-review.md) records the
latest source-cut, calculation-revision and shared-workspace fixes and checks.

Reviewed 2026-11-02 after the eight-phase delivery. This review preserves unrelated
workspace changes and does not commit or publish them.

## Findings and fixes

| Finding | Corrected behavior |
|---|---|
| Not applicable coverage could hide recorded GST activity | Outward, inward, ITC, portal, opening and payment coverage is checked against actual retained activity. Contradictory coverage blocks review. |
| Ordinary domestic ITC could be classified as imports or ISD | Native claims follow their domestic or reverse-charge supply profile: 4(A)(5) or 4(A)(3). Imports and ISD need separate retained statutory evidence. |
| Generic blocked credit could be placed in 4(D)(2) | Native blocked credit remains an inward-ineligible working. The statutory section 16(4)/place-of-supply disclosure needs specific retained evidence; generic blocking does not establish those grounds. |
| An immutable but unposted credit instruction could be allocated | Accounting requires its committed credit event. Draft instructions are also excluded from Reports' unallocated posted-source checks. |
| Independently rounded statutory totals could disagree with child cells | Source values remain exact at four decimals; each aggregated statutory leaf cell rounds to two decimals before derived totals, net ITC and payment calculations. |
| Table 3.2 rejected applicable ECO interstate supplies | Its disclosure ceiling includes 3.1(a) and the ECO's 3.1.1(i), without adding the disclosure to liability again. Supplier-only 3.1.1(ii) is excluded. |
| Historical ledger balances prevented an otherwise Nil return | Opening cash/ITC and previous-return evidence do not count as current activity. Current transactions, portal amounts, outstanding liabilities and missing coverage still prevent Nil. |
| Prepare stayed enabled after opening an externally filed preparation | The displayed filed GSTIN/period disables Prepare. Selecting another period clears that preparation and restores the action subject to current permissions; the server also rejects re-preparation of filed periods. |

Each calculation/capture/source fix has a regression test that failed before the
fix. The GST Portal's [GSTR-3B FAQ](https://tutorial.gst.gov.in/userguide/returns/GSTR3B.htm)
documents the Nil criteria and GSTR-1 Tables 15/15A mapping into 3.1.1(i) and 3.2.
This retains the supported October 2025 form version; earlier saved preparations
remain frozen and are not recalculated or rewritten.

## Verification

| Check | Final result |
|---|---|
| Reports native MySQL: statutory calculations, API, artifacts and existing tax-report regressions | 66 passed |
| Accounting native MySQL: GST contract/capture and credit-action APIs | 14 passed |
| Identity native MySQL: dated GST setup and filing-preference APIs | 7 passed |
| GST workspace, company configuration and existing tax-report UI | 78 passed, including the new filed-Prepare regression |
| Targeted Ruff and mypy; scoped Console application/test TypeScript | Passed |
| Identity, Accounting and Reports OpenAPI/generated-client checks | Passed |
| Native migration/model/index parity and owned downgrade/upgrade | Passed; local heads remain Identity 0096, Accounting 0228 and Reports 0039 |
| Populated browser workflow over the authenticated shell | Passed: statutory sections, source search, kebab/drawer row height, file hashing, review/filing history and actual native artifact bytes |
| Light, Dark and Ledger at 1440px and 390px | Passed; tables scroll within their containers, without horizontal page expansion |
| Three-page prescribed preparation PDF | Visually reviewed; correct statutory ordering, tax heads, payments, exact contributors and verification placeholders |
| Live company applicability, card/direct navigation and API readiness | Passed; the QA company currently has no eligible GSTIN/profile |
| Local runtime | Updated; Identity, Accounting and Reports ready, all six report workers running |

The native suites use new disposable MySQL schemas. No production voucher,
registration, return or payment is manufactured for verification. Browser and
artifact evidence is retained under the ignored
`.test_artifacts/tax-reports-review/GSTR3B/` directory. Full repository TypeScript
is not claimed: unrelated Purchase fixture errors are outside this review; the
Console application and relevant GST/report tests pass their scoped check.

All deliberately failing regression tests passed after their fixes. Existing
company UI tests emit React act warnings, and Vitest emits a Vite CJS deprecation
notice; neither caused a failure.

The manual simplify/security review covers exact money, committed financial
sources, current tenant/company/field authority, bounded source lookups, immutable
review/filing evidence, and protected exports. Slash-command tools are unavailable;
this is the equivalent manual review. No new migration or wire schema is needed
for these fixes.

## Scope and live-company limits

The current QA company has no eligible Indian GST registration/filing profile.
The live review checks the correctly hidden card and explicit setup requirement;
populated form/review/export browser checks use clearly identified fixtures whose
calculation and artifacts come from native MySQL verification. They do not prove
filing for a real registered company.

This is return preparation, reconciliation, print/export and external filing
evidence. Direct GST Portal filing, portal-upload JSON and automatic payment are
not implemented. Imported/ISD/other unsupported native tax sources require
reviewed retained evidence; missing evidence remains Needs attention.
