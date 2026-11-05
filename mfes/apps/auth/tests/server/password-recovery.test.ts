import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Page, { dynamic, metadata } from '../../app/recover/page';
import { passwordRecoveryDestination, recoverySignInHref } from '../../app/lib/password-recovery';

beforeEach(() => {
  vi.stubEnv('AUTH_PROVIDER', 'authentik');
  vi.stubEnv('AUTHENTIK_ISSUER', 'https://authentik.test/application/o/janso/');
  vi.stubEnv('AUTHENTIK_SELF_SERVICE_RECOVERY_ENABLED', 'true');
  vi.stubEnv('NEXTAUTH_URL', 'https://login.test');
  vi.stubEnv('NEXT_PUBLIC_CONSOLE_URL', 'https://books.test');
});
afterEach(() => vi.unstubAllEnvs());

it('builds the native public flow from the configured HTTPS issuer, without credentials or query data', () => {
  expect(passwordRecoveryDestination()).toBe('https://authentik.test/if/flow/bill-self-service-recovery/');
});
it.each(['', 'false', 'TRUE', '1'])('withholds recovery without explicit SMTP preparation: %s', flag => {
  vi.stubEnv('AUTHENTIK_SELF_SERVICE_RECOVERY_ENABLED', flag);
  expect(passwordRecoveryDestination()).toBeNull();
});
it.each(['', 'not a URL', 'http://authentik.test', 'https://user:password@authentik.test',
  'https://authentik.test/?token=private', 'https://authentik.test/#fragment', 'javascript:alert(1)'])('fails closed for an invalid issuer: %s', issuer => {
  vi.stubEnv('AUTHENTIK_ISSUER', issuer);
  expect(passwordRecoveryDestination()).toBeNull();
});
it.each([undefined, '', 'https://evil.test/path', '//evil.test/path', 'javascript:alert(1)',
  'https://user:password@books.test/path', 'https://login.test/logout', 'x'.repeat(2049)])('rejects unsafe login destinations: %s', candidate => {
  expect(recoverySignInHref(candidate)).toBe('/login');
});
it.each(['https://books.test/vouchers?draft=1', '/reports?year=2026', 'https://login.test/setup?administrator=1'])('retains an approved destination: %s', candidate => {
  const target = new URL(candidate, 'https://books.test');
  expect(recoverySignInHref(candidate)).toBe('/login?returnTo=' + encodeURIComponent(target.href));
});
it('renders dynamically with privacy metadata and no account-specific state', async () => {
  const page = await Page({ searchParams: Promise.resolve({ returnTo: 'https://books.test/reports' }) });
  expect(page.props).toEqual({ destination: 'https://authentik.test/if/flow/bill-self-service-recovery/',
    signInHref: '/login?returnTo=' + encodeURIComponent('https://books.test/reports') });
  expect(dynamic).toBe('force-dynamic');
  expect(metadata.referrer).toBe('no-referrer');
  expect(metadata.robots).toEqual({ index: false, follow: false });
});
it('handles empty, repeated and legacy callback queries safely', async () => {
  expect((await Page({})).props.signInHref).toBe('/login');
  expect((await Page({ searchParams: Promise.resolve({ returnTo: ['https://books.test', 'https://evil.test'] }) })).props.signInHref).toBe('/login');
  expect((await Page({ searchParams: Promise.resolve({ callbackUrl: 'https://books.test/users' }) })).props.signInHref)
    .toBe('/login?returnTo=' + encodeURIComponent('https://books.test/users'));
});
it('handles broken environment configuration without rendering a crash', () => {
  vi.stubEnv('NEXT_PUBLIC_CONSOLE_URL', 'invalid');
  expect(recoverySignInHref('/reports')).toBe('/login');
});
