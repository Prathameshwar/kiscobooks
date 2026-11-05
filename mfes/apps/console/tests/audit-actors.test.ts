import { afterEach, expect, it, vi } from 'vitest';
vi.mock('../app/identity-session', () => ({ identityFetch: vi.fn() }));
import { identityFetch } from '../app/identity-session';
import { GET } from '../app/api/audit-actors/[id]/route';

const id = '00000000-0000-0000-0000-000000000001';
const request = new Request('http://console.test/api/audit-actors/' + id);
const context = { params: Promise.resolve({ id }) };
afterEach(() => vi.resetAllMocks());

it('returns only a name from an authorized active Identity record, without caching', async () => {
  vi.mocked(identityFetch).mockResolvedValueOnce(Response.json({ id, status: 'active', anonymized_at: null, display_name: 'Alex', email: 'private@example.test' }));
  const response = await GET(request, context);
  expect(identityFetch).toHaveBeenCalledWith('/v1/users/' + id);
  expect(response.headers.get('cache-control')).toBe('no-store');
  expect(await response.json()).toEqual({ name: 'Alex' });
});
it.each([401, 403, 404, 503])('keeps the ID fallback when Identity returns %s', async status => {
  vi.mocked(identityFetch).mockResolvedValueOnce(new Response(null, { status }));
  expect(await (await GET(request, context)).json()).toEqual({ name: null });
});
it.each([{ anonymized_at: '2026-01-01' }, { status: 'deactivated' }, { id: 'different' }])('does not return an anonymized, inactive or mismatched name: %j', async change => {
  vi.mocked(identityFetch).mockResolvedValueOnce(Response.json({ id, status: 'active', display_name: 'Hidden', ...change }));
  expect(await (await GET(request, context)).json()).toEqual({ name: null });
});
it('rejects path injection before calling Identity', async () => {
  expect((await GET(request, { params: Promise.resolve({ id: '../users' }) })).status).toBe(422);
  expect(identityFetch).not.toHaveBeenCalled();
});
it('contains optional upstream and session failures', async () => {
  vi.mocked(identityFetch).mockRejectedValueOnce(new Error('private connection'));
  expect(await (await GET(request, context)).json()).toEqual({ name: null });
});
