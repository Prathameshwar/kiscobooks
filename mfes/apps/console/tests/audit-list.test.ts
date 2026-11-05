import { describe, expect, it } from 'vitest';
import {
  AUDIT_CATEGORIES,
  AUDIT_DEFAULT_SORT,
  AUDIT_ENTITY_TYPES,
  AuditQueryError,
  actorLabel,
  createAuditDetailLoader,
  createAuditLoader,
  entityLabel,
  listAuditEvents,
  type AuditEventItem,
} from '../app/lib/audit-events';
import { getAuditTrail } from '../app/lib/audit-trail';

/**
 * The audit list contract — the client's half of `GET /v1/audit-events` (docs/audit.md §5).
 *
 * The rules under test are the ones an auditor's conclusion rests on: the newest event leads, a
 * filter is typed rather than free-form, `security` is not readable on this surface at all, the
 * detail is a second request, and no row carries a name.
 */

/** A fixed instant, so nothing here depends on when the suite runs. */
const NOW = Date.parse('2026-09-13T12:00:00.000Z');

async function trail() {
  return getAuditTrail(NOW);
}

function event(overrides: Partial<AuditEventItem> & { id: string }): AuditEventItem {
  return {
    occurred_at: '2026-09-13T10:00:00.000Z',
    sequence: 1,
    category: 'admin',
    action: 'company.updated',
    entity_type: 'company',
    entity_id: null,
    actor_type: 'user',
    actor_user_id: null,
    on_behalf_of_user_id: null,
    company_id: null,
    department_id: null,
    source_service: 'identity',
    trace_id: null,
    ...overrides,
  };
}

describe('ordering', () => {
  it('leads with the newest event, which is what the endpoint defaults to', async () => {
    const { events } = await trail();
    const page = listAuditEvents(events);

    expect(AUDIT_DEFAULT_SORT).toBe('-occurred_at');
    expect(page.items[0]?.action).toBe('invoice.posted');
    const stamps = page.items.map((item) => item.occurred_at);
    expect([...stamps].sort().reverse()).toEqual(stamps);
  });

  it('sorts by chain position, and breaks a tie on the id', async () => {
    const { events } = await trail();
    expect(listAuditEvents(events, { sort: 'sequence' }).items[0]?.sequence).toBe(41_196);

    /*
     * Two events recorded in the same microsecond. Without the `id` tie-breaker their relative
     * order is whatever the sort happened to produce, and a page boundary between them would skip
     * one row and repeat another (api-conventions §2.4).
     */
    const same = [
      event({ id: 'b', occurred_at: '2026-09-13T10:00:00.000Z' }),
      event({ id: 'a', occurred_at: '2026-09-13T10:00:00.000Z' }),
    ];
    expect(listAuditEvents(same, { sort: 'occurred_at' }).items.map((item) => item.id)).toEqual([
      'a',
      'b',
    ]);
    // Descending flips the compared key, not the tie-breaker.
    expect(listAuditEvents(same, { sort: '-occurred_at' }).items.map((item) => item.id)).toEqual([
      'a',
      'b',
    ]);
  });

  it('rejects a sort on anything but the two indexed keys', async () => {
    const { events } = await trail();
    // No sort on `action`, `actor` or `category`: the trail is partitioned by `occurred_at`, and a
    // sort without an index that leads with it is a full scan of an append-only table.
    expect(() => listAuditEvents(events, { sort: 'action' })).toThrow(AuditQueryError);
    expect(() => listAuditEvents(events, { sort: '-actor_user_id' })).toThrow(AuditQueryError);
  });
});

describe('filters', () => {
  it('narrows by category, entity type and action', async () => {
    const { events } = await trail();

    expect(
      listAuditEvents(events, { category: 'money' }).items.every((item) => item.category === 'money'),
    ).toBe(true);
    expect(listAuditEvents(events, { entity_type: 'invoice' }).items).toHaveLength(2);
    expect(listAuditEvents(events, { action: 'invoice.voided' }).items).toHaveLength(1);
  });

  it('refuses the security category outright, on this surface', async () => {
    const { events } = await trail();
    /*
     * Not "returns nothing" — refused. Security events live behind `audit.read_security` on their
     * own surface (docs/audit.md §5.1), and a reader holding plain `audit.read` must never receive
     * one, including through an export. A silent empty page would read as "there are none".
     */
    expect(() => listAuditEvents(events, { category: 'security' })).toThrow(AuditQueryError);
    expect(AUDIT_CATEGORIES as readonly string[]).not.toContain('security');
    for (const category of AUDIT_CATEGORIES) {
      expect(() => listAuditEvents(events, { category })).not.toThrow();
    }
  });

  it('takes a period as two named bounds, inclusive, and never as an operator', async () => {
    const { events } = await trail();
    const dayAgo = new Date(NOW - 24 * 3_600_000).toISOString();

    const recent = listAuditEvents(events, { occurred_from: dayAgo });
    expect(recent.items.every((item) => item.occurred_at >= dayAgo)).toBe(true);
    expect(recent.items.length).toBeLessThan(events.length);

    // Both ends, and each bound includes its own instant.
    const exact = events[0]!.occurred_at;
    expect(
      listAuditEvents(events, { occurred_from: exact, occurred_to: exact }).items.map((i) => i.id),
    ).toEqual([events[0]!.id]);
  });

  it('offers subject types the trail declares, not only the ones on the page in hand', async () => {
    const { events } = await trail();

    /*
     * The list is declared, not derived. A filter built from the rows in hand could only ever offer
     * what is already visible — which is the opposite of what a filter is for — so the proof is
     * that narrowing the page to one row does not narrow the choices.
     */
    const onePage = listAuditEvents(events, { limit: 1 }).items;
    expect(new Set(onePage.map((item) => item.entity_type)).size).toBe(1);
    expect(AUDIT_ENTITY_TYPES.length).toBeGreaterThan(1);

    // And every type the trail can actually produce is offered, or the filter hides a subject.
    for (const type of new Set(events.map((item) => item.entity_type))) {
      expect(AUDIT_ENTITY_TYPES as readonly string[]).toContain(type);
    }
  });
});

describe('paging', () => {
  it('derives has_more from a limit + 1 read and walks the trail exactly once', async () => {
    const { events } = await trail();
    const first = listAuditEvents(events, { limit: 5 });
    const second = listAuditEvents(events, { limit: 5, cursor: first.page.next_cursor });
    const third = listAuditEvents(events, { limit: 5, cursor: second.page.next_cursor });

    expect(first.page.has_more).toBe(true);
    expect(third.page.has_more).toBe(false);
    const ids = [...first.items, ...second.items, ...third.items].map((item) => item.id);
    expect(new Set(ids).size).toBe(events.length);
  });

  it('never returns a total, however small the trail', async () => {
    const { events } = await trail();
    // A count over a partitioned append-only table is the query that takes the database down, so
    // there is nothing to expose (api-conventions §2.1).
    expect(Object.keys(listAuditEvents(events, { limit: 5 }).page).sort()).toEqual([
      'has_more',
      'limit',
      'next_cursor',
    ]);
  });

  it('rejects a cursor reused after the query changed', async () => {
    const { events } = await trail();
    const cursor = listAuditEvents(events, { limit: 5 }).page.next_cursor as string;

    expect(() => listAuditEvents(events, { limit: 5, category: 'money', cursor })).toThrow(
      AuditQueryError,
    );
    expect(() => listAuditEvents(events, { limit: 5, sort: 'sequence', cursor })).toThrow(
      AuditQueryError,
    );
    expect(() => listAuditEvents(events, { limit: 4, cursor })).toThrow(AuditQueryError);
    expect(listAuditEvents(events, { limit: 5, cursor }).items).toHaveLength(5);
  });

  it('rejects a malformed cursor and an out-of-bounds limit as 422, never as a crash', async () => {
    const { events } = await trail();
    expect(() => listAuditEvents(events, { cursor: 'not-a-cursor' })).toThrow(AuditQueryError);
    expect(() => listAuditEvents(events, { limit: 0 })).toThrow(AuditQueryError);
    expect(() => listAuditEvents(events, { limit: 201 })).toThrow(AuditQueryError);
  });
});

describe('what a row may carry', () => {
  it('holds actor ids and no names, anywhere in the payload', async () => {
    const { events, details } = await trail();
    const serialized = JSON.stringify({ events, details });

    // The one assertion that matters most here: an audit row references the actor and stores no
    // PII (CLAUDE.md §6.9, docs/audit.md §5.2).
    expect(serialized).not.toMatch(/Prathameshwar/i);
    expect(serialized).not.toMatch(/@/);
    for (const item of events) {
      expect(item).not.toHaveProperty('actor_name');
      expect(item).not.toHaveProperty('actor_email');
    }
  });

  it('renders an actor as a type and an id tail, and a service actor as its type', () => {
    expect(actorLabel(event({ id: 'x', actor_user_id: '0192f001-9d10-7a41-b001-7c2d90ae0001' }))).toBe(
      'user ·ae0001',
    );
    // A system event has no user at all — the type is the honest answer, not a blank.
    expect(actorLabel(event({ id: 'x', actor_type: 'service', actor_user_id: null }))).toBe('service');
    expect(actorLabel(event({ id: 'x', actor_type: null, actor_user_id: null }))).toBeNull();
  });

  it('renders a subject as its type, with the id tail when there is one', () => {
    expect(entityLabel(event({ id: 'x', entity_type: 'invoice', entity_id: 'abc-def-123456' }))).toBe(
      'invoice ·123456',
    );
    expect(entityLabel(event({ id: 'x', entity_type: 'audit_event', entity_id: null }))).toBe(
      'audit_event',
    );
  });

  it('keeps the JSON columns off the list and on the detail', async () => {
    const { events, details } = await trail();
    const [row] = listAuditEvents(events, { limit: 1 }).items;

    // `changes` and `context` are JSON columns a list must not return (api-conventions §3), which
    // is exactly why the panel is a second request.
    expect(row).not.toHaveProperty('changes');
    expect(row).not.toHaveProperty('context');
    expect(details[row!.id]).toMatchObject({ changes: expect.any(Object), row_hash: expect.any(String) });
  });

  it('carries money in a change as a string, never as a number', async () => {
    const { details } = await trail();
    const posted = Object.values(details).find((detail) => detail.action === 'invoice.posted');

    expect(posted?.changes?.total_amount).toEqual({ from: '18400.0000', to: '18400.0000' });
    expect(typeof posted?.changes?.total_amount?.to).toBe('string');
  });

  it('has no predecessor hash on the first event of the chain, and one on every other', async () => {
    const { events, details } = await trail();
    const oldest = events[events.length - 1]!;

    expect(details[oldest.id]?.prev_hash).toBeNull();
    for (const item of events.slice(0, -1)) {
      expect(details[item.id]?.prev_hash).toEqual(expect.any(String));
    }
  });
});

describe('the loaders', () => {
  it('answers a page after its delay', async () => {
    const { events } = await trail();
    const load = createAuditLoader(events, 1);
    const page = await load({ limit: 3 }, new AbortController().signal);

    expect(page.items).toHaveLength(3);
    expect(page.page.has_more).toBe(true);
  });

  it('rejects a bad parameter after the round trip, the way a real 422 arrives', async () => {
    const { events } = await trail();
    const load = createAuditLoader(events, 1);

    await expect(load({ category: 'security' }, new AbortController().signal)).rejects.toBeInstanceOf(
      AuditQueryError,
    );
  });

  it('fetches one event’s detail, and fails as an ordinary error when it cannot', async () => {
    const { events, details } = await trail();
    const load = createAuditDetailLoader(details, 1);

    const detail = await load(events[0]!, new AbortController().signal);
    expect(detail.id).toBe(events[0]!.id);
    expect(detail.message_id).toEqual(expect.any(String));

    // Not a 422: the parameters were fine. The panel renders this as "could not be read", with a
    // retry — the row is still on screen either way.
    await expect(
      load(event({ id: 'no-such-event' }), new AbortController().signal),
    ).rejects.not.toBeInstanceOf(AuditQueryError);
  });

  it('rejects with an AbortError when either request is abandoned', async () => {
    const { events, details } = await trail();
    const controller = new AbortController();
    const list = createAuditLoader(events, 50)({}, controller.signal);
    const detail = createAuditDetailLoader(details, 50)(events[0]!, controller.signal);

    controller.abort();

    await expect(list).rejects.toMatchObject({ name: 'AbortError' });
    await expect(detail).rejects.toMatchObject({ name: 'AbortError' });
  });
});
