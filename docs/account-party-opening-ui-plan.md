# Account and party opening UI delivery

Authorized 2026-10-28: implement the UI over the completed opening APIs, reusing
existing Console styles, controls, navigation, request and financial review patterns.

- [x] 1. Typed UI adapter, narrow proxy policy, company permission gates and metadata.
- [x] 2. Guided company worksheet: coverage, account balances, party bills/on-account
  evidence, historical FX values and optional YTD summary; exact decimal validation.
- [x] 3. Server preview, reviewed save/replace, bounded draft preparation, native journal
  navigation, reconciliation and explicit completion; safe same-request retry.
- [x] 4. File templates, bounded import, validation/issues/history/resume, private exports
  and immutable revision history. Link from account/party and Masters entry points.
- [x] 5. UI, validation, permission and proxy tests; typecheck and browser review where
  available. Review twice, fix findings and record precise verification limits.

Use a company-wide workspace because opening accounting must balance across ledgers.
Party links preselect an authorized account, never create another party balance owner.
Do not silently post journals, finalize zero, or enable deployment admission switches.
No financial worksheet data is persisted in browser storage. Posted corrections remain
in the existing native journal workflow. Preserve concurrent Sales and stock UI work.

Completed with two reviews and fixes. See [delivery and verification](account-party-opening-ui-delivery.md).

## 2026-11-04 workflow revision

The user requested three steps: choose Buyer/Supplier/one Other Accounts group; edit an
alphabetical paged account grid with quick search; validate rows and review automatic or
manual source settings and posting. They confirmed company books begin for every row and
a configured equity offset for any difference. See the
[implementation plan](account-party-opening-three-step-plan.md). Automatic posting remains
an explicit final action; switching modes or opening a page never posts money.

Final review decision, 2026-11-04: the confirmed automatic action includes native
confirmation, reconciliation and finalization on this page. No subsequent manual
finalize action is required. Missing starter opening accounts are initialized during
explicit preview, with retained same-key recovery. Existing or partially posted
worksheets offer Complete opening automatically; posted journals are skipped.
