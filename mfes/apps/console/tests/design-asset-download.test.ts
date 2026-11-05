import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { GET } from '../app/api/design-asset/route';

vi.mock('next-auth/jwt', () => ({ getToken: vi.fn() }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), asset = id(2), token = 'signed-download-token';

beforeEach(() => {
  vi.stubEnv('AUTH_URL', 'http://auth.test');
  vi.stubEnv('NEXTAUTH_SECRET', 'test');
  vi.stubEnv('DESIGN_GATEWAY_URL', 'http://gateway.test/design');
  vi.mocked(getToken).mockResolvedValue({ accessToken: 'private-access', accessTokenExpires: Date.now() + 60000 });
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

function call(query = `company=${company}&asset=${asset}&token=${token}`, headers: Record<string, string> = {}) {
  return GET(new NextRequest('http://console.test/api/design-asset?' + query, { headers }));
}

it.each(['image/png', 'image/jpeg', 'image/webp'])('streams %s with private headers and no browser bearer grant', async media => {
  let output: ReadableStreamDefaultController<Uint8Array> | undefined;
  const stream = new ReadableStream<Uint8Array>({ start(controller) { output = controller; } });
  const upstream = new Response(stream, { headers: { 'Content-Type': media, 'Content-Length': '18' } });
  vi.spyOn(upstream, 'arrayBuffer').mockRejectedValue(new Error('Do not buffer'));
  vi.spyOn(upstream, 'text').mockRejectedValue(new Error('Do not buffer'));
  const fetch = vi.fn().mockResolvedValueOnce(upstream);
  vi.stubGlobal('fetch', fetch);
  const response = await call();
  expect(response.status).toBe(200);
  expect(response.headers.get('Content-Type')).toBe(media);
  expect(response.headers.get('Cache-Control')).toContain('no-store');
  expect(response.headers.get('Content-Security-Policy')).toContain('sandbox');
  expect(response.headers.get('Content-Length')).toBe('18');
  expect(fetch.mock.calls[0]![0]).toBe(`http://gateway.test/design/v1/companies/${company}/assets/${asset}/download?token=${token}`);
  expect(fetch.mock.calls[0]![1].headers.Authorization).toBe('Bearer private-access');
  output!.enqueue(new TextEncoder().encode('fake image bytes'));
  output!.close();
  expect(await response.text()).toBe('fake image bytes');
});

it.each([401, 403, 409, 500])('preserves denied/unavailable status %s before any body is read', async status => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status })));
  const response = await call();
  expect(response.status).toBe(status === 404 ? 404 : 502);
});

it('answers 404 for a response the service itself refused to serve', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 404 })));
  expect((await call()).status).toBe(404);
});

it('checks session, identifiers, origin and configuration', async () => {
  expect((await call(`company=not-a-uuid&asset=${asset}&token=${token}`)).status).toBe(422);
  expect((await call(`company=${company}&asset=${asset}&token=`)).status).toBe(422);
  expect((await call(`company=${company}&asset=${asset}&token=${token}&token=${token}`)).status).toBe(422);
  expect((await call(`company=${company}&asset=${asset}&token=${token}&extra=1`)).status).toBe(422);
  expect((await call(undefined, { 'sec-fetch-site': 'cross-site' })).status).toBe(403);
  vi.mocked(getToken).mockResolvedValue(null);
  expect((await call()).status).toBe(401);
  vi.mocked(getToken).mockResolvedValue({ accessToken: 'private-access', accessTokenExpires: Date.now() + 60000 });
  vi.stubEnv('DESIGN_GATEWAY_URL', '');
  expect((await call()).status).toBe(503);
});

it('refuses a token with characters outside its signed alphabet', async () => {
  expect((await call(`company=${company}&asset=${asset}&token=has space`)).status).toBe(422);
  expect((await call(`company=${company}&asset=${asset}&token=has/slash`)).status).toBe(422);
});

it('rejects an upstream content type this route does not serve', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<script>bad</script>', { headers: { 'Content-Type': 'text/html' } })));
  expect((await call()).status).toBe(502);
});

it('recovers a network error as unavailable, not a crash', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
  expect((await call()).status).toBe(503);
});
