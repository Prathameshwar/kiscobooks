import { expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
vi.mock('../app/identity-session', () => ({ auditFetch: vi.fn() }));
import { auditFetch } from '../app/identity-session';
import { GET, POST } from '../app/api/audit/[...segments]/route';

const context = (segments: string[]) => ({ params: Promise.resolve({ segments }) });

it('forwards platform history and timestamp details and denies evidence writes', async () => {
  for (const segments of [['v1', 'platform-events'], ['v1', 'platform-events', '00000000-0000-4000-8000-000000000001']]) {
    vi.mocked(auditFetch).mockResolvedValueOnce(Response.json({items:[]}));
    const result=await GET(new NextRequest('http://console.test/api/audit/' + segments.join('/') + '?occurred_at=2026-10-22T00:00:00Z'), context(segments));
    expect(result.status).toBe(200);
    expect(result.headers.get('cache-control')).toBe('no-store');
    expect((await POST(new NextRequest('http://console.test/api/audit/' + segments.join('/'),{method:'POST'}),context(segments))).status).toBe(405);
  }
});

it('forwards only the allowed Audit path and safe query, with no cached data', async () => {
  vi.mocked(auditFetch).mockResolvedValueOnce(Response.json({ items: [] }));
  const result = await GET(new NextRequest('http://console.test/api/audit/v1/audit-events?limit=2'), context(['v1', 'audit-events']));
  expect(result.status).toBe(200);
  expect(result.headers.get('cache-control')).toBe('no-store');
  expect(auditFetch).toHaveBeenCalledWith('/v1/audit-events?limit=2', 'GET');
});
it('rejects duplicate and unknown query keys', async () => {
  for (const query of ['limit=2&limit=3', 'target=http://evil.test']) {
    const result = await GET(new NextRequest('http://console.test/api/audit/v1/audit-events?' + query), context(['v1', 'audit-events']));
    expect(result.status).toBe(422);
  }
});
it('requires the current origin for export and refuses arbitrary upstream paths', async () => {
  const request = new NextRequest('http://console.test/api/audit/v1/audit-events/export', { method: 'POST', headers: { Origin: 'http://other.test' } });
  expect((await POST(request, context(['v1', 'audit-events', 'export']))).status).toBe(403);
  expect((await GET(request, context(['internal', 'users']))).status).toBe(404);
});
it('returns an unavailable envelope rather than an internal exception', async () => {
  vi.mocked(auditFetch).mockRejectedValueOnce(new Error('private connection'));
  const result = await GET(new NextRequest('http://console.test/api/audit/v1/audit-events'), context(['v1', 'audit-events']));
  expect(result.status).toBe(503);
  expect(await result.text()).not.toContain('private');
});

it('accepts the real browser origin when Next normalizes a loopback URL', async () => {
  vi.mocked(auditFetch).mockResolvedValueOnce(Response.json({ count: 1 }));
  const request = new NextRequest('http://127.0.0.1:4320/api/audit/v1/audit-events/export', {
    method: 'POST', headers: { Origin: 'http://127.0.0.1:4320', Host: '127.0.0.1:4320' },
  });
  expect((await POST(request, context(['v1', 'audit-events', 'export']))).status).toBe(200);
});
