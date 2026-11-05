import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GET as providerRoute } from '../../app/api/provider/route';
import { authOrigin, authProvider, localBff, providerEndpoints, safeAuthProvider } from '../../app/lib/provider';
import { BFF_SECRET, ISSUER, localEnv } from './local-support';

beforeEach(() => localEnv());
afterEach(() => vi.unstubAllEnvs());

describe('AUTH_PROVIDER resolution', () => {
  it('defaults to the local provider when unset or blank', () => {
    expect(authProvider()).toBe('local');
    vi.stubEnv('AUTH_PROVIDER', '');
    expect(authProvider()).toBe('local');
    vi.stubEnv('AUTH_PROVIDER', '   ');
    expect(authProvider()).toBe('local');
  });
  it.each([['local', 'local'], ['authentik', 'authentik'], [' authentik ', 'authentik']])('accepts %j', (value, expected) => {
    vi.stubEnv('AUTH_PROVIDER', value);
    expect(authProvider()).toBe(expected);
  });
  it.each(['LOCAL', 'Authentik', 'okta', 'local,authentik', 'oidc', 'true', '0'])('treats %j as a configuration error', value => {
    vi.stubEnv('AUTH_PROVIDER', value);
    expect(() => authProvider()).toThrow('Invalid authentication provider configuration');
    expect(() => providerEndpoints()).toThrow();
    expect(safeAuthProvider()).toBeNull();
  });
  it('reports the provider on the public route and fails closed on a bad value', async () => {
    const ok = await providerRoute();
    expect(await ok.json()).toEqual({ provider: 'local' });
    expect(ok.headers.get('cache-control')).toBe('no-store');
    vi.stubEnv('AUTH_PROVIDER', 'authentik');
    expect(await (await providerRoute()).json()).toEqual({ provider: 'authentik' });
    vi.stubEnv('AUTH_PROVIDER', 'bogus');
    const bad = await providerRoute();
    expect(bad.status).toBe(503);
    expect(await bad.text()).not.toContain('bogus');
  });
});

describe('local endpoints', () => {
  it('derives discovery, token and revoke endpoints from the issuer', () => {
    expect(providerEndpoints()).toEqual({ id: 'local', name: 'KiscoBooks', issuer: ISSUER, clientId: 'auth-app',
      clientSecret: 'client-secret-for-tests', wellKnown: `${ISSUER}/.well-known/openid-configuration`,
      tokenUrl: `${ISSUER}/token`, revokeUrl: `${ISSUER}/revoke` });
  });
  it('ignores one trailing slash', () => {
    vi.stubEnv('AUTH_LOCAL_ISSUER', `${ISSUER}/`);
    expect(providerEndpoints().tokenUrl).toBe(`${ISSUER}/token`);
    expect(providerEndpoints().wellKnown).toBe(`${ISSUER}/.well-known/openid-configuration`);
  });
  it('needs no Authentik setting', () => {
    for (const name of ['AUTHENTIK_ISSUER', 'AUTHENTIK_CLIENT_ID', 'AUTHENTIK_CLIENT_SECRET']) expect(process.env[name]).toBeUndefined();
    expect(() => providerEndpoints()).not.toThrow();
  });
  it.each(['AUTH_LOCAL_ISSUER', 'AUTH_LOCAL_CLIENT_ID', 'AUTH_LOCAL_CLIENT_SECRET'])('requires %s', name => {
    vi.stubEnv(name, '');
    expect(() => providerEndpoints()).toThrow(`Missing authentication configuration: ${name}`);
  });
  it.each(['https://bill.example.com/identity/oidc', 'http://localhost:8001/oidc', 'http://127.0.0.1:8001/oidc',
    'http://[::1]:8001/oidc', 'http://localhost/oidc'])('accepts the local issuer %s', issuer => {
    vi.stubEnv('AUTH_LOCAL_ISSUER', issuer);
    expect(providerEndpoints().issuer).toBe(issuer);
  });
  it.each(['http://evil.example', 'http://evil.example/oidc', 'http://localhost.evil.example/oidc',
    'http://127.0.0.1.evil.example/oidc', 'http://notlocalhost/oidc', 'http://10.0.0.5/oidc', 'http://0.0.0.0/oidc',
    'http://localhost@evil.example/oidc', 'https://user:pw@bill.test/oidc', 'https://bill.test/oidc?x=1',
    'https://bill.test/oidc#frag', 'ftp://bill.test/oidc', 'javascript:alert(1)', 'not a url'])('rejects the local issuer %s', issuer => {
    vi.stubEnv('AUTH_LOCAL_ISSUER', issuer);
    expect(() => providerEndpoints()).toThrow();
  });
});

describe('Authentik endpoints are unchanged', () => {
  beforeEach(() => {
    vi.stubEnv('AUTH_PROVIDER', 'authentik');
    vi.stubEnv('AUTHENTIK_ISSUER', 'https://id.test/application/o/billing/');
    vi.stubEnv('AUTHENTIK_CLIENT_ID', 'client');
    vi.stubEnv('AUTHENTIK_CLIENT_SECRET', 'secret');
  });
  it('uses the application/o paths on the issuer origin', () => {
    expect(providerEndpoints()).toEqual({ id: 'authentik', name: 'Authentik', issuer: 'https://id.test/application/o/billing/',
      clientId: 'client', clientSecret: 'secret', wellKnown: 'https://id.test/application/o/billing/.well-known/openid-configuration',
      tokenUrl: 'https://id.test/application/o/token/', revokeUrl: 'https://id.test/application/o/revoke/' });
  });
  it('keeps its HTTPS-only rule even for loopback', () => {
    vi.stubEnv('AUTHENTIK_ISSUER', 'http://localhost:9000/application/o/billing/');
    expect(() => providerEndpoints()).toThrow('requires HTTPS');
  });
  it.each(['AUTHENTIK_ISSUER', 'AUTHENTIK_CLIENT_ID', 'AUTHENTIK_CLIENT_SECRET'])('still requires %s', name => {
    vi.stubEnv(name, '');
    expect(() => providerEndpoints()).toThrow();
  });
});

describe('shared origin and BFF configuration', () => {
  it('resolves the Auth app origin and refuses unsafe forms', () => {
    expect(authOrigin()).toBe('https://auth.test');
    vi.stubEnv('NEXTAUTH_URL', 'http://localhost:4310');
    expect(authOrigin()).toBe('http://localhost:4310');
    for (const value of ['http://auth.test', 'https://u:p@auth.test', 'https://auth.test/app', 'https://auth.test/?a=1', '', 'nonsense'])
      { vi.stubEnv('NEXTAUTH_URL', value); expect(() => authOrigin()).toThrow(); }
  });
  it('requires a long BFF secret and an HTTPS or loopback Identity origin', () => {
    expect(localBff().secret).toBe(BFF_SECRET);
    expect(localBff().identityUrl.href).toBe('https://identity.test/');
    vi.stubEnv('IDENTITY_URL', 'http://127.0.0.1:8001');
    expect(localBff().identityUrl.origin).toBe('http://127.0.0.1:8001');
    for (const value of ['http://identity.internal:8001', 'https://identity.test/v1', 'https://u:p@identity.test', '']) {
      vi.stubEnv('IDENTITY_URL', value);
      expect(() => localBff()).toThrow();
    }
    vi.stubEnv('IDENTITY_URL', 'https://identity.test');
    for (const value of ['', 'short-secret']) { vi.stubEnv('AUTH_LOCAL_BFF_SECRET', value); expect(() => localBff()).toThrow(); }
  });
});

describe('describe the loopback rule exactly', () => {
  it('compares the whole hostname, not a prefix, suffix or substring', () => {
    for (const host of ['localhost.evil.example', 'evil-localhost', '127.0.0.10', '127.0.0.1.nip.io', 'xlocalhost']) {
      vi.stubEnv('AUTH_LOCAL_ISSUER', `http://${host}/oidc`);
      expect(() => providerEndpoints()).toThrow();
    }
  });
});
