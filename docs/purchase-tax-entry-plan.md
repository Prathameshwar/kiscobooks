# Purchase account bill: entering tax

Requested 2026-11-01: the Purchase account bill (`/vouchers/new/purchase`) must not be limited to "This bill carries
no tax". When the box is not ticked the person must be able to enter what tax applies, row by row or as one section,
whichever is the better practice. Confirmed 2026-11-02: goods and stock purchases stay off this screen, VAT and other
regimes wait for their service profiles, and a supplier that cannot be taxed is explained rather than offered.
**Status: delivered for India GST on service lines (2026-11-02).** The service-side limits below are the service's,
not this screen's.

## What the service already did (read from the code, not assumed)

- **Accounting computes the tax; the person does not type it.** `invoice_tax.resolve_line` takes each expense
  account's *tax default* (a SAC code and a tax rule, a master on the account) plus the bill's context and returns the
  components. Two taxed profiles exist for purchase account bills besides `UNTAXED_ACCOUNT`:
  `INDIA_DOMESTIC_SERVICE` (supplier charges GST) and `INDIA_DOMESTIC_SERVICE_RCM` (recipient pays under reverse
  charge). Vouchers stores the context per supply (`voucher_supply_tax_context`).
- **What a taxed bill needs** (the service refuses without it, with a plain message): services only (a goods profile is
  not released — Sales has the same limit); every line's account has a purchase tax default that is a service SAC
  default; **the default's `rcm_applicable` equals the bill's profile** (so the profile is a fact of the accounts as
  much as of the bill); the company's GST registration and the place of supply; the service completion date; the
  supplier's invoice number and date; a *regular* GST supplier for **both** profiles (composition and unregistered
  suppliers are refused, and RCM for an unregistered supplier is not inferred); no rate change between invoice and
  completion (needs payment-date evidence, refused for now).
- The supplier's registration travels as `party_registration_id`; without it Accounting treats the supplier as
  unregistered. Hence the console must read it and send it.

## What was built

**Tax is chosen for the bill, confirmed by the facts the bill holds, and shown per expense account.**

1. **The box stays, and GST sits under it.** "This bill carries no tax" is still the statement a person makes. Unticked
   — which is how a new bill starts once the company's registrations are known — the **GST section** opens:
   - *How GST is charged*: "Charged by the supplier" or "Reverse charge: you pay the GST" (the two profiles).
   - *Your GST registration*: the company's registration in force on the invoice date (primary first); a choice only
     when there are several.
   - *Place of supply*: a state, following the registration's state until chosen. *Service completion date*: following
     the supplier invoice date until chosen. Both are blank in the draft until the person chooses, so a bill never keeps a
     stale default after its supplier or date changed.
   - *Supplier's GST registration*: read from the supplier's tax registrations; a choice when the supplier has several
     regular ones. A supplier with none, or a composition / unregistered one, is explained in a notice with the way out
     (record without tax, or fix the registration in another tab) and blocks the save of a taxed bill.
   - *Tax by expense account*: each account on the bill, its lines, and what its tax default says ("SAC 998399 ·
     Taxable"), or why the bill will be refused (no default; a goods default; the account and the bill disagree about
     reverse charge) with a link to set the default.
2. **Nothing here is a rate or an amount.** Accounting calculates them from the accounts' tax setup (CLAUDE.md §1,
   invariant 14). After **Calculate saved bill** the calculation card shows the tax by component (CGST, SGST, UTGST,
   IGST, Cess; reverse charge marked as the company's own to pay) and GST line by line.
3. **Reads, not writes.** The section reads the company's registrations (Identity), the supplier's registrations and
   each account's default (Accounting) through the existing product proxy; every row is verified to belong to this
   company, supplier and account. Nothing is read for someone without `accounting.tax.read`, and a taxed bill is not
   re-saved by someone who cannot read what it was taxed under.
4. **Why a box and a section, not a row-level tax column.** The profile, registration and place of supply are facts of the
   bill, not of a row; Tally, Zoho and ERPNext all choose the regime for the document and compute per line. The per-row
   view is the "tax by expense account" list and the calculation's line table, which is where a row-level figure exists.

## Phases (each ended with its tests green)

- [x] **T1 Model.** `PurchaseWorkspaceDraft.tax` (`lib/purchase-tax.ts`), reducer action, `purchaseInput` /
  `purchaseFromVoucher` round trip for the two GST profiles. A saved bill whose tax context this screen would rewrite
  (another invoice date or number, a withholding section, a payment date, a line with its own registration) is sent to
  voucher review instead of being silently edited.
- [x] **T2 Tax section.** `PurchaseTaxSection`, `usePurchaseTaxFacts` (reads, caches, concurrency of four, reload),
  gating by permission, by voucher type and by the company's registrations in force.
- [x] **T3 Rows.** Tax default status per expense account; calculation table by line.
- [x] **T4 Calculation.** Unchanged: save, calculate, accept. A live preview as you type is a follow-up.
- [~] **T5 Quick-create.** *Not done, deliberately.* An expense account created from the bill starts without a tax
  default; creating one is a second, non-atomic command. The section flags the missing default and links to the form.
- [x] **T6 Close.** Docs, live check, review (below).

## Findings that need a decision from someone

1. **No screen adds a company GST registration.** Identity has `POST /companies/{id}/tax-registrations`, but the console
   has no form for it (the company wizard says registrations are "added after the company exists, from its own
   settings", and there are none there). Until one exists, GST on a bill can only be used by companies whose
   registration was added through the API. This screen says "A company administrator needs to add one".
2. **The default Purchase *Account Bill* type allowed only Account supplies**, and GST is recorded on service lines.
   *Resolved 2026-11-02.* The type editor has an **Allow service purchase lines** box (Masters → Voucher types → Edit
   rules), and the provisioning default is now **catalogue v3**: `PUR_ACC` allows ACCOUNT and SERVICE
   ([company-voucher-defaults](company-voucher-defaults.md)). New companies get it from discovery; an existing company's
   untouched `PUR_ACC` follows on its next voucher setup as a new revision; an edited type is never replaced. Sales account
   invoices still allow ACCOUNT only, which the Sales GST path will hit the same way.
3. **Local environment:** the Catalog tax publications (`catalog.tax_*.changed`) are never published here (nothing runs
   the Catalog outbox), so Accounting's tax-rule replica is empty, and the Vouchers–Accounting calculation connection is
   not configured (a temporary one was made and removed on 2026-11-02; see
   [purchase-bill-readiness](purchase-bill-readiness.md)). *Calculate saved bill* therefore cannot be completed locally
   for any bill, taxed or not; a taxable calculation is verified by the Accounting suite and by this screen's tests
   against the response shape, not live.

## Verification

- Console: 157 new tests (`purchase-tax-lib` 60, `purchase-tax-api` 27, `purchase-tax-section` 28,
  `purchase-tax-connected` 20, `use-purchase-tax-facts` 12, `purchase-tax-policy` 5, `purchase-calculation-card` 5) and
  three in `purchase-type-rules`. Behaviour changes to existing tests: the page lede ("with or without GST") in two tests,
  and the styles test now reads `PurchaseTaxSection`. The proxy policy test runs the loaders against the real allow-list.
  46 deliberate faults in the new code (a registration of another party accepted, reverse and charged tax summed,
  a refused save shown as an unticked box, and so on) were each caught by a test; seven were not at first and their tests
  were strengthened. `tsc` is clean for this change; the purchase, voucher, sales and accounting-configuration groups pass
  except the supplier-role test in `accounting-configuration-ui` that was failing before this work.
- Live (tenant1, QA company), with the company's registrations read answered by a made-up registration (the only
  stubbed call): the section reads the real supplier registration and account default, a taxed draft was saved, and the
  Vouchers service stored `INDIA_DOMESTIC_SERVICE` with the company and supplier registration ids, place of supply,
  completion date, and the supplier invoice number and date. Layout checked at 1440px and 390px, light and dark.
  QA data: two drafts (`QA-TAX-216805`, `QA-TAX-313898`, since cancelled), and the QA purchase type now allows service
  purchase lines (revision created through the editor).
- Not verified live: a taxable calculation (finding 3), and a taxed bill on a company with a real registration (finding 1).

## Open

- VAT and other regimes: the service has India GST profiles only. When a release adds one, the "How GST is charged"
  choice becomes a choice of profile; this screen does not fake one on the client.
- Amounts that *include* tax (`GROSS_INCL_TAX`) are not offered; the screen sends amounts before tax, and the supplier's
  own total in the bill details is the check against the invoice.
- Composition and unregistered suppliers, and RCM for them, wait for the service's statutory profiles.
- A supplier that has no payable account (e.g. `Supplier 1`, created before 2026-11-02) is repaired by `POST /parties/ledger-repair` (PL-D05); a "Create payable account" action on the bill is no longer wanted: no bill asks for the account.
