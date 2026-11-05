import { afterEach, describe, expect, it, vi } from 'vitest';
const api = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }));
vi.mock('@janso/api-client', () => ({ createAuditClient: () => api }));
import { liveAuditLoader, liveAuditDetailLoader, liveAuditExporter, normalizeChanges } from '../app/lib/audit-api';

afterEach(() => vi.unstubAllGlobals());

describe('live Audit transport', () => {
  it('passes company filters and preserves server cursors without fetching details', async () => {
    api.GET.mockResolvedValueOnce({ response: { ok: true }, data: { items: [], page: { has_more: true, next_cursor: 'signed' } } });
    const result = await liveAuditLoader('company')({ category: 'money', limit: 2 }, new AbortController().signal);
    expect(result.page).toEqual({ limit: 2, has_more: true, next_cursor: 'signed' });
    expect(api.GET).toHaveBeenLastCalledWith('/v1/audit-events', expect.objectContaining({
      params: { query: expect.objectContaining({ company_id: 'company', category: 'money' }) },
    }));
  });
  it.each([401, 403, 422, 503])('preserves failure status %s', async status => {
    api.GET.mockResolvedValueOnce({ response: { ok: false, status } });
    await expect(liveAuditLoader()({}, new AbortController().signal)).rejects.toMatchObject({ status });
  });
  it('keeps marker-only evidence distinct from recorded nulls', () => {
    expect(normalizeChanges({ status: { from: null, to: 'POSTED' }, name: { changed: true } })).toEqual({
      status: { from: null, to: 'POSTED' }, name: { from: null, to: null, changed: true },
    });
  });
  it('reads historical Notification field-list evidence without losing lifecycle values', () => {
    expect(normalizeChanges({ fields: ['status', 'credential_ref'], values: { status: 'ACTIVE' } })).toEqual({
      status: { from: null, to: 'ACTIVE', from_recorded: false }, credential_ref: { from: null, to: null, changed: true },
    });
  });
  it('keeps retained primitive evidence distinct from marker-only changes', () => {
    expect(normalizeChanges({ status: 'ACTIVE', count: 2, enabled: false, removed: null })).toEqual({
      status: { from: null, to: 'ACTIVE', from_recorded: false }, count: { from: null, to: '2', from_recorded: false },
      enabled: { from: null, to: 'false', from_recorded: false }, removed: { from: null, to: null, from_recorded: false },
    });
  });
  it('uses occurred_at for detail partition lookup', async () => {
    api.GET.mockResolvedValueOnce({ response: { ok: true }, data: { changes: {}, context: null } });
    await liveAuditDetailLoader()({ id: 'event', occurred_at: '2026-09-17T00:00:00Z' } as never, new AbortController().signal);
    expect(api.GET).toHaveBeenLastCalledWith('/v1/audit-events/{event_id}', expect.objectContaining({
      params: { path: { event_id: 'event' }, query: { occurred_at: '2026-09-17T00:00:00Z' } },
    }));
  });
  it('exports the server result with all filters and explicit truncation', async () => {
    api.POST.mockResolvedValueOnce({ response: { ok: true }, data: { export_id: 'run', count: 5, truncated: true, events: [] } });
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:export') });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    expect(await liveAuditExporter('company')({ category: 'money', cursor: 'old', limit: 2 })).toEqual({ count: 5, truncated: true });
    expect(api.POST).toHaveBeenLastCalledWith('/v1/audit-events/export', {
      params: { query: { company_id: 'company', entity_id: undefined, category: 'money' } },
    });
  });
});

it.each([true, false])('resolves optional actor names after authorized detail and tolerates denial: %s', async allowed => {
  api.GET.mockResolvedValueOnce({ response: { ok: true }, data: { changes: {}, context: null, actor_user_id: 'actor', on_behalf_of_user_id: 'effective' } });
  const fetcher = vi.fn().mockResolvedValue(allowed ? Response.json({ name: 'Alex' }) : new Response(null, { status: 403 }));
  // Each response has an independent body, as with real fetch.
  fetcher.mockImplementation(async () => allowed ? Response.json({ name: 'Alex' }) : new Response(null, { status: 403 }));
  vi.stubGlobal('fetch', fetcher);
  const result = await liveAuditDetailLoader()({ id: 'event', occurred_at: '2026-09-17T00:00:00Z' } as never, new AbortController().signal);
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(result.actor_name).toBe(allowed ? 'Alex' : null);
  expect(result.on_behalf_of_name).toBe(allowed ? 'Alex' : null);
  expect(fetcher).toHaveBeenCalledWith('/api/audit-actors/actor', expect.objectContaining({ cache: 'no-store', credentials: 'same-origin' }));
});
