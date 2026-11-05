import { beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { GET, POST } from '../../app/api/onboarding/route';
const { token } = vi.hoisted(() => ({ token: vi.fn() }));
vi.mock('next-auth/jwt', () => ({ getToken: token }));
beforeEach(() => { vi.stubEnv('NEXTAUTH_SECRET', 'unit-test'); vi.stubEnv('NEXTAUTH_URL', 'http://localhost:4310'); vi.stubEnv('IDENTITY_URL', 'http://localhost:8001'); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ linked: false, email_verified: true }))); token.mockResolvedValue({ accessToken: 'unit-test-opaque', accessTokenExpires: Date.now() + 60000 }); });
const req = (body: unknown = {}, origin = 'http://localhost:4310') => new NextRequest('http://localhost:4310/api/onboarding', { method: 'POST', headers: { origin, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
it('reads provider-owned status using server-held credentials', async () => { expect((await GET(new NextRequest('http://localhost:4310/api/onboarding'))).status).toBe(200); expect(fetch).toHaveBeenCalledWith(new URL('http://localhost:8001/v1/onboarding/status'), expect.objectContaining({ redirect: 'error' })); });
it('denies an absent or expired session', async () => { token.mockResolvedValue(null); expect((await GET(new NextRequest('http://localhost:4310/api/onboarding'))).status).toBe(401); expect(fetch).not.toHaveBeenCalled(); });
it('rejects cross-origin writes', async () => { expect((await POST(req({}, 'https://evil.invalid'))).status).toBe(403); expect(fetch).not.toHaveBeenCalled(); });
it('bounds the submitted workspace body', async () => { expect((await POST(req({ data: 'x'.repeat(5000) }))).status).toBe(422); expect(fetch).not.toHaveBeenCalled(); });
it('forwards creation to a fixed endpoint and preserves validation errors', async () => { vi.mocked(fetch).mockResolvedValue(Response.json({ error: { code: 'validation_failed', message: 'Unknown country' } }, { status: 422 })); const response = await POST(req({ name: 'Books' })); expect(response.status).toBe(422); expect((await response.json()).error.message).toBe('Unknown country'); expect(fetch).toHaveBeenCalledWith(new URL('http://localhost:8001/v1/onboarding/tenant'), expect.objectContaining({ method: 'POST' })); });
it('offers only a matching active saved region to a verified unlinked account', async () => {
  token.mockResolvedValue({ accessToken: 'unit-test-opaque', accessTokenExpires: Date.now() + 60000,
    registrationRegion: { country_code: 'IN', state_code: 'IN-MH' } });
  const value = { linked: false, email_verified: true, options: { countries: [{ code: 'IN', name: 'India' }],
    states: [{ code: 'IN-MH', name: 'Maharashtra', country_code: 'IN' }] } };
  vi.mocked(fetch).mockImplementation(async () => Response.json(value));
  const result = await (await GET(new NextRequest('http://localhost:4310/api/onboarding'))).json();
  expect(result.registration_region).toEqual({ country_code: 'IN', state_code: 'IN-MH' });
  token.mockResolvedValue({ accessToken: 'unit-test-opaque', accessTokenExpires: Date.now() + 60000,
    registrationRegion: { country_code: 'IN', state_code: 'US-CA' } });
  expect(await (await GET(new NextRequest('http://localhost:4310/api/onboarding'))).json()).not.toHaveProperty('registration_region');
});
