/**
 * The audit trail a request is shown — what `GET /v1/audit-events` will return
 * (docs/audit.md §1).
 *
 * A stand-in for the service, and written to behave like it rather than like a fixture: ids are
 * opaque, instants are UTC, `changes` values are **strings** (a money amount is never a number on
 * this wire — CLAUDE.md §6.1), and no row carries a name, an email or an IP-adjacent value beyond
 * what the detail surface itself stores. Actors are ids (§5.2, invariant 9).
 *
 * **Built per call, never at module scope.** A module-scope binding is one object per server
 * *process*, shared by every request that process serves — which for a tenant's audit trail is the
 * cross-tenant leak session-level filtering exists to prevent (CLAUDE.md §5.3). `getAuditTrail()`
 * is therefore where the real `fetch` goes, and it already has the per-request shape for it.
 */
import type { AuditEventDetail, AuditEventItem } from './audit-events';

export type AuditTrail = {
  events: AuditEventItem[];
  /** Keyed by event id — the second surface, `GET /v1/audit-events/{id}`. */
  details: Record<string, AuditEventDetail>;
};

/** A minute, in ms. The sample instants are offsets from the request's own clock. */
const MINUTE = 60_000;

type Seed = {
  id: string;
  minutesAgo: number;
  category: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  actor: string | null;
  actorType?: string;
  onBehalfOf?: string | null;
  service: string;
  changes?: Record<string, { from: string | null; to: string | null }>;
  context?: Record<string, string>;
  reason?: string;
};

/*
 * Ids are UUIDv7-shaped: a time-ordered prefix and a random tail. Nothing in a client may parse
 * one — they are compared and displayed, never decoded (CLAUDE.md §4).
 */
const SEEDS: readonly Seed[] = [
  {
    id: '0192f4a1-1c00-7c31-9a01-4d2b7f0a1001',
    minutesAgo: 4,
    category: 'money',
    action: 'invoice.posted',
    entity_type: 'invoice',
    entity_id: '0192f480-2a10-7f01-8c22-91ab55c30011',
    actor: '0192f001-9d10-7a41-b001-7c2d90ae0001',
    service: 'billing',
    changes: {
      status: { from: 'draft', to: 'posted' },
      invoice_number: { from: null, to: 'INV/2026-27/000184' },
      // A posted total, as the string the wire carries. Four decimals is the storage scale.
      total_amount: { from: '18400.0000', to: '18400.0000' },
      posting_date: { from: null, to: '2026-09-13' },
    },
    context: { fiscal_year: '2026-27', series: 'INV', period_status: 'open' },
  },
  {
    id: '0192f4a0-4400-7c31-9a01-4d2b7f0a1002',
    minutesAgo: 26,
    category: 'money',
    action: 'payment.captured',
    entity_type: 'payment',
    entity_id: '0192f481-7b20-7f01-8c22-91ab55c30012',
    actor: '0192f001-9d10-7a41-b001-7c2d90ae0001',
    service: 'payments',
    changes: {
      status: { from: 'authorized', to: 'captured' },
      amount: { from: '18400.0000', to: '18400.0000' },
      // The gateway token and the last four only — never a card number (CLAUDE.md §5.10).
      card_last_four: { from: null, to: '4242' },
    },
    context: { gateway: 'razorpay', idempotency_key_seen: 'once' },
  },
  {
    id: '0192f49f-1000-7c31-9a01-4d2b7f0a1003',
    minutesAgo: 95,
    category: 'admin',
    action: 'company.updated',
    entity_type: 'company',
    entity_id: '0192f402-3c30-7f01-8c22-91ab55c30013',
    actor: '0192f002-1e20-7a41-b001-7c2d90ae0002',
    service: 'identity',
    changes: {
      legal_name: { from: 'Janso Retail Pvt Ltd', to: 'Janso Retail Private Limited' },
      date_format: { from: 'dd/MM/yyyy', to: 'dd MMM yyyy' },
    },
    context: { immutable_fields_untouched: 'currency, state, fiscal_start' },
    reason: 'Registrar record updated after name change',
  },
  {
    id: '0192f49e-0800-7c31-9a01-4d2b7f0a1004',
    minutesAgo: 140,
    category: 'access',
    action: 'audit.exported',
    entity_type: 'audit_event',
    entity_id: null,
    actor: '0192f002-1e20-7a41-b001-7c2d90ae0002',
    service: 'audit',
    context: { rows: '312', truncated: 'false', format: 'csv' },
    reason: 'Quarterly statutory review',
  },
  {
    id: '0192f49d-2000-7c31-9a01-4d2b7f0a1005',
    minutesAgo: 220,
    category: 'admin',
    action: 'role.assigned',
    entity_type: 'user_role',
    entity_id: '0192f403-9f40-7f01-8c22-91ab55c30014',
    actor: '0192f002-1e20-7a41-b001-7c2d90ae0002',
    service: 'identity',
    changes: {
      role: { from: null, to: 'Accounts Payable Clerk' },
      scope: { from: null, to: 'company:JANSO-RETAIL' },
    },
  },
  {
    id: '0192f49c-1400-7c31-9a01-4d2b7f0a1006',
    minutesAgo: 300,
    category: 'money',
    action: 'invoice.voided',
    entity_type: 'invoice',
    entity_id: '0192f484-1c50-7f01-8c22-91ab55c30015',
    actor: '0192f003-5a30-7a41-b001-7c2d90ae0003',
    service: 'billing',
    changes: { status: { from: 'posted', to: 'void' } },
    /*
     * A void in a *closed* period is not an edit — it is a reversing entry in an open one
     * (CLAUDE.md §6.5). The trail records which period each side landed in.
     */
    context: { reversal_of_period: '2026-07', posted_into_period: '2026-09' },
    reason: 'Duplicate of INV/2026-27/000171',
  },
  {
    id: '0192f49b-3c00-7c31-9a01-4d2b7f0a1007',
    minutesAgo: 460,
    category: 'system',
    action: 'outbox.replayed',
    entity_type: 'outbox_message',
    entity_id: '0192f485-8d60-7f01-8c22-91ab55c30016',
    actor: null,
    actorType: 'service',
    service: 'notification',
    context: { message_id_deduped: 'true', attempt: '2' },
  },
  {
    id: '0192f49a-2800-7c31-9a01-4d2b7f0a1008',
    minutesAgo: 700,
    category: 'access',
    action: 'report.downloaded',
    entity_type: 'report_run',
    entity_id: '0192f486-4e70-7f01-8c22-91ab55c30017',
    actor: '0192f004-7b40-7a41-b001-7c2d90ae0004',
    // Impersonation is time-bound and audited at both ends (§5.5) — the trail keeps both ids.
    onBehalfOf: '0192f001-9d10-7a41-b001-7c2d90ae0001',
    service: 'reports',
    context: { url_expiry_seconds: '900', signed: 'true' },
  },
  {
    id: '0192f499-1800-7c31-9a01-4d2b7f0a1009',
    minutesAgo: 1_500,
    category: 'admin',
    action: 'item.created',
    entity_type: 'item',
    entity_id: '0192f487-2f80-7f01-8c22-91ab55c30018',
    actor: '0192f003-5a30-7a41-b001-7c2d90ae0003',
    service: 'catalog',
    changes: {
      code: { from: null, to: 'RM-BOLT-M8' },
      uom: { from: null, to: 'NOS' },
      is_taxable: { from: null, to: 'true' },
    },
  },
  {
    id: '0192f498-0400-7c31-9a01-4d2b7f0a1010',
    minutesAgo: 2_900,
    category: 'admin',
    action: 'fiscal_period.closed',
    entity_type: 'fiscal_period',
    entity_id: '0192f488-1a90-7f01-8c22-91ab55c30019',
    actor: '0192f002-1e20-7a41-b001-7c2d90ae0002',
    service: 'identity',
    changes: { status: { from: 'open', to: 'closed' } },
    context: { period: '2026-08', unposted_documents: '0' },
    reason: 'Month-end close signed off',
  },
  {
    id: '0192f497-3000-7c31-9a01-4d2b7f0a1011',
    minutesAgo: 4_300,
    category: 'system',
    action: 'feature.enabled',
    entity_type: 'company_feature',
    entity_id: '0192f489-3bb0-7f01-8c22-91ab55c30020',
    actor: '0192f002-1e20-7a41-b001-7c2d90ae0002',
    service: 'identity',
    changes: { multi_currency: { from: 'false', to: 'true' } },
    // A flag that has shaped posted data cannot be turned back off (docs/company-features.md §4).
    context: { ratchet: 'irreversible_once_posted' },
  },
  {
    id: '0192f496-1200-7c31-9a01-4d2b7f0a1012',
    minutesAgo: 7_800,
    category: 'money',
    action: 'credit_note.posted',
    entity_type: 'credit_note',
    entity_id: '0192f48a-5cc0-7f01-8c22-91ab55c30021',
    actor: '0192f003-5a30-7a41-b001-7c2d90ae0003',
    service: 'billing',
    changes: {
      status: { from: 'draft', to: 'posted' },
      total_amount: { from: '0.0000', to: '2360.0000' },
    },
    context: { against_invoice: 'INV/2026-27/000102' },
  },
];

export async function getAuditTrail(now: number = Date.now()): Promise<AuditTrail> {
  const events: AuditEventItem[] = SEEDS.map((seed, index) => ({
    id: seed.id,
    occurred_at: new Date(now - seed.minutesAgo * MINUTE).toISOString(),
    // The chain position counts up with time; the newest event holds the highest sequence.
    sequence: 41_207 - index,
    category: seed.category,
    action: seed.action,
    entity_type: seed.entity_type,
    entity_id: seed.entity_id,
    actor_type: seed.actorType ?? (seed.actor ? 'user' : null),
    actor_user_id: seed.actor,
    on_behalf_of_user_id: seed.onBehalfOf ?? null,
    company_id: '0192f402-3c30-7f01-8c22-91ab55c30013',
    department_id: null,
    source_service: seed.service,
    trace_id: `trace-${seed.id.slice(0, 8)}`,
  }));

  const details: Record<string, AuditEventDetail> = {};
  events.forEach((event, index) => {
    const seed = SEEDS[index]!;
    details[event.id] = {
      ...event,
      changes: seed.changes ?? null,
      context: seed.context ?? null,
      reason: seed.reason ?? null,
      request_id: `req-${event.id.slice(9, 13)}`,
      message_id: `0192f4b0-0000-7c31-9a01-${event.id.slice(-12)}`,
      // Hex of the BINARY(32) chain values. The first event of a chain has no predecessor (§4.2).
      prev_hash: index === events.length - 1 ? null : `${event.id.slice(-12)}`.repeat(5) + 'abcd',
      row_hash: `${event.id.slice(0, 12).replaceAll('-', '')}`.repeat(6) + 'ef01',
    };
  });

  return { events, details };
}
