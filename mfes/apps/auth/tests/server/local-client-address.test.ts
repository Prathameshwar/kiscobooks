import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { POST as login } from '../../app/api/local/login/route';
import { POST as recover } from '../../app/api/local/recover/route';
import { clientAddress } from '../../app/lib/local-auth-server';
import { AUTH_URL, REQUEST_ID, TOKEN, localEnv, post } from './local-support';

/**
 * The address Identity throttles on. `X-Forwarded-For` is only believable at its end, and only as far
 * as this installation says it runs proxies: with none configured nothing is forwarded, so a client
 * cannot rotate its address to dodge a limit or borrow another person's to spend their budget.
 */
const seen = (headers: Record<string, string>) =>
  clientAddress(new NextRequest(AUTH_URL, { headers }));

beforeEach(() => localEnv());
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('clientAddress', () => {
  it('is not used at all unless proxies are configured, whatever the headers say', () => {
    expect(seen({ 'x-forwarded-for': '203.0.113.9', 'x-real-ip': '203.0.113.9' })).toBeUndefined();
    vi.stubEnv('AUTH_TRUSTED_PROXY_HOPS', '0');
    expect(seen({ 'x-forwarded-for': '203.0.113.9' })).toBeUndefined();
  });

  it('with one proxy takes the last entry, which the proxy appended itself', () => {
    vi.stubEnv('AUTH_TRUSTED_PROXY_HOPS', '1');
    expect(seen({ 'x-forwarded-for': '198.51.100.1, 203.0.113.9' })).toBe('203.0.113.9');
    // A client that claims an address of its own only ever adds to the front.
    expect(seen({ 'x-forwarded-for': '10.0.0.1, 10.0.0.2, 203.0.113.9' })).toBe('203.0.113.9');
  });

  it('with two proxies takes the entry before the last', () => {
    vi.stubEnv('AUTH_TRUSTED_PROXY_HOPS', '2');
    expect(seen({ 'x-forwarded-for': '198.51.100.1, 203.0.113.9, 192.0.2.7' })).toBe('203.0.113.9');
  });

  it('gives up when the chain is shorter than the proxies configured, rather than guessing', () => {
    vi.stubEnv('AUTH_TRUSTED_PROXY_HOPS', '2');
    expect(seen({ 'x-forwarded-for': '203.0.113.9' })).toBeUndefined();
  });

  it('falls back to X-Real-IP only when there is no forwarded chain at all', () => {
    vi.stubEnv('AUTH_TRUSTED_PROXY_HOPS', '1');
    expect(seen({ 'x-real-ip': '203.0.113.9' })).toBe('203.0.113.9');
    expect(seen({ 'x-forwarded-for': 'not-an-ip', 'x-real-ip': '203.0.113.9' })).toBeUndefined();
  });

  it('accepts IPv6 and refuses anything that is not an address', () => {
    vi.stubEnv('AUTH_TRUSTED_PROXY_HOPS', '1');
    expect(seen({ 'x-forwarded-for': '2001:db8::1' })).toBe('2001:db8::1');
    for (const bad of ['unknown', '203.0.113.9:443', '203.0.113.9; drop table', '', ' , ']) {
      expect(seen({ 'x-forwarded-for': bad })).toBeUndefined();
    }
  });

  it.each(['-1', '4', '1.5', 'many', ''])('treats %j as no proxies', (hops) => {
    vi.stubEnv('AUTH_TRUSTED_PROXY_HOPS', hops);
    expect(seen({ 'x-forwarded-for': '203.0.113.9' })).toBeUndefined();
  });
});

describe('what the routes tell Identity', () => {
  const calls = () => {
    const fetcher = vi.fn(async () => Response.json({ redirect_to: `${AUTH_URL}/api/auth/callback/local?code=a&state=b`, valid: true }));
    vi.stubGlobal('fetch', fetcher);
    return fetcher;
  };
  const header = (fetcher: ReturnType<typeof vi.fn>) => fetcher.mock.calls[0][1].headers['X-Client-Address'];
  const forwarded = { 'x-forwarded-for': '198.51.100.1, 203.0.113.9' };

  it('sign-in and recovery pass the person\'s address along when a proxy vouches for it', async () => {
    vi.stubEnv('AUTH_TRUSTED_PROXY_HOPS', '1');
    for (const send of [
      () => login(post('/api/local/login', { request_id: REQUEST_ID, email: 'a@b.test', password: 'x'.repeat(8) }, forwarded)),
      () => recover(post('/api/local/recover', { action: 'inspect', token: TOKEN }, forwarded)),
      () => recover(post('/api/local/recover', { action: 'redeem', token: TOKEN, new_password: 'A Brand New Passphrase 42!' }, forwarded)),
    ]) {
      const fetcher = calls();
      await send();
      expect(header(fetcher)).toBe('203.0.113.9');
    }
  });

  it('send no address at all when none is trusted, however the request is dressed', async () => {
    for (const send of [
      () => login(post('/api/local/login', { request_id: REQUEST_ID, email: 'a@b.test', password: 'x'.repeat(8) }, forwarded)),
      () => recover(post('/api/local/recover', { action: 'inspect', token: TOKEN }, forwarded)),
    ]) {
      const fetcher = calls();
      await send();
      expect(header(fetcher)).toBeUndefined();
    }
  });
});
