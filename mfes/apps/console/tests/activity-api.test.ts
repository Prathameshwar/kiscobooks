import { beforeEach, expect, it, vi } from 'vitest';
const api = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('@janso/api-client', () => ({ createAuditClient: () => api }));
import { activityLoader } from '../app/lib/activity-api';

beforeEach(() => vi.clearAllMocks());

it.each(['company', null])('retains server evidence and cursor for scope %s', async company => {
  const data = { items: [{ actor_type: 'system', source_service: 'catalog' }], page: { has_more: true, next_cursor: 'native-signed' } };
  api.GET.mockResolvedValue({ response: { ok: true }, data });
  const signal = new AbortController().signal;
  expect(await activityLoader(company)('previous-signed', signal)).toBe(data);
  expect(api.GET).toHaveBeenLastCalledWith('/v1/activity', { params: { query: { company_id: company ?? undefined, limit: 50, sort: '-occurred_at', cursor: 'previous-signed' } }, signal });
});

it.each([401, 403, 422, 500, 503])('preserves native failure %s without displaying stale data', async status => {
  api.GET.mockResolvedValue({ response: { ok: false, status }, data: { items: ['must not render'] } });
  await expect(activityLoader('company')(null, new AbortController().signal)).rejects.toMatchObject({ status });
});
