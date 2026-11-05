# Notification Microservice — Remediation & Enhancement Plan

**Date:** 2026-10-15  
**Status:** Approved for Execution  
**Scope:** Remediation of 8 confirmed operational/domain bugs (B01–B08) and 7 integration/architecture gaps (G01–G07) across `apis/notification`, caller services (`vouchers`, `identity`, `accounting`), and clients.  
**Companion Documents:** `docs/notification.md`, `docs/notification-operations.md`, `docs/notification-implementation-todo.md`.

---

## 1. Findings Ledger

### A. Confirmed Bugs (B01–B08)
| ID | Severity | File | Description |
|---|---|---|---|
| **B01** | **Critical** | `tasks/delivery_worker.py` | **Worker Infinite Busy-Loop Spin on ConflictError:** When `dispatch_stored` encounters a non-dispatchable state (expired request, deactivated endpoint/sender/provider), worker catches `ConflictError` and simply `continue`s. Rows remain in `pending`/`retry_wait` with `next_attempt_at <= now`, locking the query window and starving all tenants. |
| **B02** | **Critical** | `callbacks.py`<br>`tasks/normalize.py` | **Webhook Message ID Disconnect:** `callbacks.py` expects `x-provider-message-id` in HTTP headers. Real webhooks (Twilio, Meta, SES) send IDs in their body payload. All valid callbacks are marked `unmatched`, completely breaking status progression (`delivered`, `read`, `failed`). |
| **B03** | **Critical** | `tasks/consume.py` | **Scheduled Sends Dispatched Immediately:** `_plan_channel` sets `status="pending"` and `next_attempt_at=now` instead of respecting `command.scheduled_at`. Worker attempts dispatch immediately, gets `ConflictError`, and busy-loops until scheduled time. |
| **B04** | **High** | `tasks/dispatch.py` | **Retry Limits & Jittered Backoff Ignored:** `attempt_number` is never checked against `RoutingRule.max_attempts`. Backoff hardcodes $2^{\min(n, 10)}$ instead of calling `domain/retry.py:backoff_seconds` with rule's `initial_backoff_seconds` and `max_backoff_seconds`. |
| **B05** | **High** | `api/management.py` | **Template Activation Overlap Race Condition:** `create_activation` selects existing activations without `with_for_update()`, allowing concurrent requests to create overlapping active windows. |
| **B06** | **Medium** | `api/management.py`<br>`domain/routing.py` | **Routing Rule Validation & Specificity Flaws:** Channel compatibility is not checked (SMS provider can be linked to Email rule), sender ownership is not verified, and `_specificity` ignores category match when event key matches. |
| **B07** | **Medium** | `providers/ses.py` | **SES HTML Body Dropped:** `SesAdapter` only transmits `Body.Text`, dropping rendered `body_html_ciphertext`. |
| **B08** | **Medium** | `providers/http.py` | **Meta WhatsApp Empty Parameters Error:** Serializes `"parameters": []` when template has no variables; Meta Graph API rejects this as HTTP 400. |

### B. Architectural & Integration Gaps (G01–G07)
| ID | Severity | File / Service | Description |
|---|---|---|---|
| **G01** | **Medium** | `tasks/dispatch.py` | **Missing Finalization Timestamps & Outbox Event:** `accepted_at` / `failed_at` are not written in `_finalize`, and no `notification.delivery.status_changed` event is emitted. |
| **G02** | **Medium** | `api/routes.py` | **Missing Manual Retry API:** Permission `notification.delivery.retry` is defined in platform, but `POST /v1/deliveries/{id}/retry` was never implemented. |
| **G03** | **Medium** | `apis/vouchers` | **Voucher Variables & Artifact Handoff:** Send commands only contain 5 basic metadata fields; invoice totals, party names, due dates, and PDF attachments are absent. |
| **G04** | **Medium** | `apis/identity` | **Missing Security & Lifecycle Notifications:** Identity never sends password reset, magic link, login security alert, or licence expiry notifications. |
| **G05** | **Medium** | `apis/accounting` | **Missing Accounting Communications:** No outbound notifications for customer ledger statements, payment receipts, or dunning notices. |
| **G06** | **Low** | `tasks/project.py`<br>`tasks/consume.py` | **Legacy Insecure Consumers:** Unauthenticated `run_preference_projector` and legacy `run_consumer` remain in the codebase. |
| **G07** | **Low** | `mfes/apps/console` | **Console UI Gap:** Missing administration interface for notification templates, provider accounts, routing rules, and delivery logs. |

---

## 2. Phase-Wise Execution Roadmap

```
┌────────────────────────────────────────────────────────┐
│ Phase NR0: Test Harness & Baseline Reproductions       │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Phase NR1: Dispatcher & Worker Resilience (B01,03,04,G1)│
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Phase NR2: Provider Adapters & Webhooks (B02, B07, B08) │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Phase NR3: Governance, Concurrency & Retry API (B05,06,G2)
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Phase NR4: Caller Integrations (Vouchers/Identity/Acc) │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Phase NR5: End-to-End Verification & OpenAPI Sync      │
└────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Action Items (TODO Checklist)

### Phase NR0 — Test Harness & Baseline Reproductions
- [x] Preserve current passing test suite (69 tests passing).
- [x] Fix 25 mypy type errors in `apis/notification/tests/`:
  - [x] Add type annotations to helper fixtures in `test_party_contact_projection.py` and `test_delivery_worker.py`.
  - [x] Replace `SimpleNamespace` mocks with proper `ProviderAccount` objects or typed protocols.
  - [x] Fix `None` comparison in `test_identity_delivery.py`.
- [x] Add reproduction tests for B01 (worker spin), B02 (webhook payload parse), B03 (scheduled send), and B04 (retry exhaustion). Confirm failures before remediation.

### Phase NR1 — Dispatcher & Worker Resilience (B01, B03, B04, G01)
- [x] **Fix B01 (`delivery_worker.py` & `dispatch.py`):**
  - Distinguish transient conflict (concurrency race) from permanent unviability (expired request, deactivated endpoint/sender/provider).
  - On permanent unviability, transition `delivery.status` to `expired` or `failed` with descriptive `status_reason`, set `completed_at=now`, and log delivery event.
  - Back off deliveries when provider credentials cannot be loaded from environment.
- [x] **Fix B03 (`tasks/consume.py`):**
  - In `_plan_channel`, check `command.scheduled_at`.
  - If `command.scheduled_at > now`: set `status="scheduled"` and `next_attempt_at=command.scheduled_at`.
  - Otherwise: set `status="pending"` and `next_attempt_at=now`.
- [x] **Fix B04 (`tasks/dispatch.py`):**
  - Make `attempt_key` unique per attempt (`{delivery_id}:{attempt_number}`) to prevent SQL unique constraint crash on retry.
  - Retrieve `RoutingRule` in `_finalize` or pass `max_attempts`, `initial_backoff_seconds`, and `max_backoff_seconds`.
  - If `attempt_number >= rule.max_attempts`: set `delivery.status = "failed"` and `delivery.status_reason = "max_attempts_exceeded"`.
  - Calculate `next_attempt_at` using `domain.retry.backoff_seconds` with deterministic jitter.
- [x] **Implement G01 (`tasks/dispatch.py`):**
  - Set `delivery.accepted_at = completed` when outcome is `accepted`.
  - Set `delivery.failed_at = completed` and `delivery.completed_at = completed` when outcome is `permanent_failure` or retries exhausted.
  - Emit `notification.delivery.status_changed` outbox event in `_finalize`.

### Phase NR2 — Provider Adapters & Webhook Payload Normalization (B02, B07, B08)
- [x] **Fix B02 (`callbacks.py`, `providers/normalize.py` & `tasks/normalize.py`):**
  - Implement `extract_callback_metadata(channel, body)` to parse:
    - Twilio SMS: URL-encoded form data (`MessageSid`, `MessageStatus`).
    - Meta WhatsApp: JSON payload (`entry[0].changes[0].value.statuses[0].id` and status).
    - AWS SES / SNS: JSON payload (`Message.mail.messageId` and event type).
  - In `callbacks.py`, fallback to body inspection if `x-provider-message-id` header is absent.
  - In `tasks/normalize.py`, decrypt `payload_ciphertext` if `event.provider_message_id` is missing.
- [x] **Fix B07 (`providers/ses.py` & `providers/base.py`):**
  - Add `body_html: str | None = None` to `SendCommand`.
  - Pass `body_html` in `dispatch_stored`.
  - In `SesAdapter`, construct `Content.Simple.Body` with both `Text` and `Html` when `command.body_html` is present.
- [x] **Fix B08 (`providers/http.py`):**
  - In `MetaWhatsAppAdapter`, omit `"components"` if `command.template_parameters` is empty, avoiding Meta API 400 Bad Request.

### Phase NR3 — Governance, Concurrency & Manual Retry API (B05, B06, G02, G06)
- [x] **Fix B05 (`api/management.py`):**
  - Add `with_for_update()` to template activation overlap check in `create_activation`.
- [x] **Fix B06 (`api/management.py` & `domain/routing.py`):**
  - In `create_routing_rule`, validate `body.category in CATEGORIES`.
  - Verify `provider.channel == body.channel`.
  - Verify `sender.provider_account_id == body.provider_account_id`.
  - In `domain/routing.py:_specificity`, verify `route.category in {"*", category}` for all matches.
- [x] **Implement G02 (`api/routes.py`):**
  - Add `POST /v1/deliveries/{delivery_id}/retry` endpoint requiring `notification.delivery.retry`.
  - Verify delivery is in terminal failed/expired state, reset `attempt_count=0`, set `status="pending"`, `next_attempt_at=utcnow()`, and emit outbox event.
- [x] **Clean Up G06 (`tasks/project.py` & `tasks/consume.py`):**
  - Disable deprecated unauthenticated `run_preference_projector` and `run_consumer`.

### Phase NR4 — Producer Service Integrations (G03, G04, G05)
- [x] **Enrich Voucher Send Commands (G03 in `apis/vouchers`):**
  - Include `currency`, `due_date`, and `party_id` in `emit_send` template variables.
  - Verified with `apis/vouchers/tests/test_notification_share.py`.
- [ ] **Identity Security Notifications Backlog (G04 in `apis/identity`):**
  - Planned: `identity.security_alert` on password change or new IP login.
  - Planned: company licence renewal scanner job.
- [ ] **Accounting Notification Backlog (G05 in `apis/accounting`):**
  - Planned: outbound event emissions for customer statements and payment receipt vouchers.

### Phase NR5 — End-to-End Verification & OpenAPI Synchronization
- [x] Run full test suite across SQLite and MySQL test harness (`uv run pytest` -> 77 passed).
- [x] Run `mypy src tests` and ensure 0 type errors.
- [x] Run `ruff check .` with clean results.
- [x] Re-export `openapi.json` via `tools/export_openapi.py`.
- [x] Update `clients/api-client` types via `node scripts/generate.mjs` (8 tests passing).
- [x] Update `docs/notification-operations.md` runbook with remediation details.

---

## 4. Verification & Acceptance Criteria

1. **Worker Liveness:** When invalid, expired, or deactivated deliveries exist in the database, the dispatch worker gracefully expires or fails them without busy-looping or delaying healthy deliveries.
2. **Webhook Status Advancement:** Twilio, Meta, and SES webhook fixtures advance delivery states from `accepted` $\rightarrow$ `delivered` without custom gateway header injections.
3. **Scheduled Sends:** Messages with `scheduled_at` in the future remain in `scheduled` state until `scheduled_at` elapses.
4. **Retry Guarantees:** Deliveries experiencing 500 errors back off with jitter and terminate as `failed` at `attempt_count == max_attempts`.
5. **Type Safety & Zero Warnings:** Clean `mypy` and `ruff` runs across both `src/` and `tests/`.
