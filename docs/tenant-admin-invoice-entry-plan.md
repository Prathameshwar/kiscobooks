# Tenant admin #13: Purchase entry and invoice acceptance

The offered Purchase route is a placeholder even though native invoice capture,
calculation and draft acceptance already support Purchase. Finish this independent
UI work using the already selected untaxed account profile from step 6.

1. Reuse the native type/date/field-set entry and shared invoice workflow. Bind the
   route to PURCHASE and reject foreign-company or mismatched type evidence. Add a
   typed account-invoice section for supplier, active payable and expense accounts,
   reference/date, description and exact amounts. Native field permissions govern
   visible and writable fields; do not introduce an alternate calculator.
2. Require a configured untaxed account profile and readable/writable input facts.
   Saving sends existing InvoiceInput and supplier PartyInput, with native account
   and party versions. Preview, accept and submit reuse the existing owner paths.
   Capture supplier-declared totals explicitly; never infer difference tolerance.
3. Test valid/invalid/pending/refused/uncertain saves, same-key retry, native lookup
   scope, fixed decimal bounds, field access and kind-bound routing. Exercise the
   three QA companies through UI with exact owner readbacks, replay and unchanged
   non-posting effects. Review and update current CSV/TODO.
4. Continue selected native invoice, tax and report acceptance; keep C2 and legal
   issuance open until their required owner evidence and concrete D05/D09 statutory
   profile exist. A UI draft does not grant financial or statutory release authority.

This is a refinement of the user-approved High-complexity sequence. It adds no
new financial flag, tax rate/provider, migration or direct application DB write.
Goods, mixed and automatic scheme supplies retain their owner prerequisites.

## Country and tax selection, 2026-10-30

The user directed invoice tax selection from company country and configured tax
type: India plus GST uses the applicable native India GST profile; other countries
and tax types use their supported configured contracts. This must not fall back to
an untaxed profile for a tax-bearing or unsupported supply. The first account-bill
verification below remains an explicitly NON_GST synthetic expense. Native GST
service capture additionally requires dated classification/defaults, registration,
place of supply and service/supplier date evidence; RCM is conditional on the actual
configuration, never assumed for all India purchases.
