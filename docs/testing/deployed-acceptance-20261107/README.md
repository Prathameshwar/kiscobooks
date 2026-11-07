# Deployed acceptance — 7 November 2026

Scope: test the existing deployed website in BTCL after the VM update. Use uniquely named test records and retain their IDs. Do not change company configuration or existing vouchers to make a test pass.

1. Confirm the running release and fresh authenticated company selection.
2. Create a goods product through the UI using current required fields. Verify completion, generated code, active native record and availability in purchase search. Exercise validation before saving.
3. Create a purchase product bill through the UI. Verify supplier, product, quantity, rate, receipt information, configured tax/charge sections and optional blank charges. Save, reload, preview/accept calculation and submit. Check posting where the existing policy and permissions permit it; record any prerequisite refusal accurately. Verify persisted invoice/stock sections and absence of duplicate effects.
4. Open Profit and Loss. Verify its default dates respect retained source coverage, create a report, wait for its terminal state and inspect the actual result. Verify an unsupported earlier date gives a clear validation message. Reload the result.
5. Record browser errors, safe API failures, screenshots and readback evidence. A server-side calculation or component test alone does not count as deployed browser acceptance.

Authentication: the former browser session has ended and its password was not retained. The ignored private driver opens a workstation PowerShell prompt and sends the password to the VM browser over SSH stdin. Passwords must not be placed in chat, scripts, command arguments, screenshots or recorded event files. A user login is required before the browser scenarios can run; do not bypass authentication or synthesize a user session.

Initial read-only preflight: active VM release is `latest-build-20261107-061719`. BTCL's latest verified report source covers history from `2026-11-06`. The deployed Profit and Loss definition calculates six presentation rows from that date; `2026-04-01` raises `InsufficientHistoryError`. This preflight is not evidence that the deployed creation/report UI passed.
