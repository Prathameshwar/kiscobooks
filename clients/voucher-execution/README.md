# Voucher execution wire client

Version 0.2.0 defines the private Vouchers/Accounting command, immutable result and signed
HTTP transport. It imports no service models and performs no financial calculation.
`command_digest` binds all accepted evidence except purpose (POST/CANCEL share an attempt)
and the digest itself. Content/configuration/source identities remain fixed on retries.
Authority expires within five minutes for a new attempt; committed reconciliation is permanent.
COMMITTED requires a source receipt, aware commit time and owner committed generation.

Configure matching, distinct execution credentials using `ACCOUNTING_VOUCHER_EXECUTION_CREDENTIALS`
and Vouchers' `VOUCHERS_EXECUTION_OWNER`. A grant may name tenant/company scopes or use
`allow_enrolled_companies=true`: Vouchers discovers native company guards and Accounting
checks its own setup record for each signed request. Use HTTPS outside literal loopback
development. No credentials are seeded or committed. Requests and
responses include signed method/path/body evidence; the client follows no redirects.

Protocol v2 adds typed money capture/policy, fiscal evidence, reversal identity and delegated
gateway authority. Ordinary Journal/Contra/Payment/Receipt use the owner prepare, Identity
reserve, owner commit lifecycle. Identity calls occur outside money transactions; commit
rechecks period, source versions, authority and cancellation. Legacy v1 foundation payloads
retain their original serialization and continue to reject real financial effects.

Amounts use exact positive 19,4 decimal strings; rates use 19,8. Stable fixed-scale encoding
keeps revision fingerprints identical before and after native database reload. Policies may
only narrow the implemented behavior. Cost-centre dimensions, tax and stock are unavailable.
STANDARD supports four money kinds; ADVANCE supports Payment/Receipt. Adjustments/refunds
are explicit money purposes. Pure allocation creates no cash journal; native FX is separate.
Reversal retains original source evidence and uses its own open-period correction date.
Private delegated credentials are excluded from public results, reports and representations.

Tests live in `apis/accounting/tests/test_voucher_execution.py` (owner/transport/native races)
and `apis/vouchers/tests/test_execution_delivery.py` (producer and lost-response recovery).
Money integration and signed owner-to-report acceptance are in `test_voucher_money.py`,
`test_money_boundaries.py`, `test_money_profiles.py` and `test_money_reporting_flow.py`.

Purchase print facts (`printing.py`) are read-only and run under the interactive actor's own
authority. 0.3.9 added two optional, additive fields to `PurchasePrintFacts`: `voucher_number`
(Accounting's journal number for a POSTED bill, `None` for a preview or when the actor may not read
it) and `ledgers` (the ledger account name behind each printed supply line or tender, `None` where
unreadable). A reply without them still validates, so an older Accounting works with a newer Vouchers; deploy
Vouchers first (the models forbid unknown fields, so an older Vouchers refuses a newer reply).
Tests: `tests/test_printing.py`.

0.3.10 relaxes two money validations (no wire change): a non-cash `Tender.reference` is optional
(a cheque still needs `instrument_date`), and a `NEW_REF` line needs its `bill_reference` but no `due_date`
(Accounting dates the bill on the document date). A newer validator accepts everything an older one did,
but an older Accounting refuses such a command as an invalid contract: deploy Accounting before Vouchers.

0.4.0 (B24 goods Purchase bills, additive): stock action `PURCHASE_INVOICE`, tax profile `INDIA_DOMESTIC_GOODS`,
input-credit choice on goods supplies, `SupplyCalculation.stock_cost`, item `purchase_tax` facts and the preview
command's optional `stock`. Unset fields are omitted from the wire. Deploy Catalog and Accounting before Vouchers.
