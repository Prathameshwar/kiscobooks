import { randomBytes } from 'node:crypto';
import { beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { POST } from '../../app/api/change-password/route';
const { token } = vi.hoisted(() => ({ token: vi.fn() }));
vi.mock('next-auth/jwt', () => ({ getToken: token }));
beforeEach(() => {
 vi.stubEnv('AUTH_PROVIDER', 'authentik'); vi.stubEnv('NEXTAUTH_URL', 'https://auth.test'); vi.stubEnv('NEXTAUTH_SECRET', randomBytes(32).toString('hex')); vi.stubEnv('AUTHENTIK_ISSUER', 'https://id.test/application/o/bill/');
 token.mockResolvedValue({ accessToken: randomBytes(32).toString('hex'), accessTokenExpires: Date.now()+300000 });
});
const req = (origin='https://auth.test') => new NextRequest('https://auth.test/api/change-password', { method:'POST',headers:{origin} });
it('returns only a configured secure provider destination and no tokens', async () => { const result=await POST(req()); expect(result.status).toBe(200); expect(await result.json()).toEqual({destination:'https://id.test/if/flow/bill-password-change/'}); });
it('refuses cross-origin and expired sessions', async () => { expect((await POST(req('https://evil.test'))).status).toBe(403); token.mockResolvedValue(null); expect((await POST(req())).status).toBe(401); });
it('fails safely on provider configuration', async () => { vi.stubEnv('AUTHENTIK_ISSUER','http://id.test/'); const result=await POST(req()); expect(result.status).toBe(503); expect(await result.text()).not.toContain('secret'); });
