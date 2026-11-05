import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SignInPage, { dynamic as signInDynamic, metadata as signInMetadata } from '../../app/signin/page';
import ResetPage, { dynamic as resetDynamic, metadata as resetMetadata } from '../../app/reset/page';
import RecoveryPage from '../../app/recover/page';
import ChangePasswordPage, { dynamic as changeDynamic } from '../../app/change-password/page';
import { LocalChangePassword } from '../../app/change-password/LocalChangePassword';
import { ProviderChangePassword } from '../../app/change-password/ProviderChangePassword';
import { REQUEST_ID, TOKEN, localEnv } from './local-support';

beforeEach(() => localEnv({ NEXT_PUBLIC_CONSOLE_URL: 'https://books.test' }));
afterEach(() => vi.unstubAllEnvs());
const query = (value: Record<string, string | string[]>) => ({ searchParams: Promise.resolve(value) });

describe('sign-in page', () => {
  it('hands a well-formed request id to the form and is private and dynamic', async () => {
    expect((await SignInPage(query({ request: REQUEST_ID }))).props).toEqual({ requestId: REQUEST_ID, available: true });
    expect(signInDynamic).toBe('force-dynamic');
    expect(signInMetadata.referrer).toBe('no-referrer');
    expect(signInMetadata.robots).toEqual({ index: false, follow: false });
  });
  it.each([['no query', undefined], ['a repeated parameter', { request: [REQUEST_ID, REQUEST_ID] }], ['a short id', { request: 'abc' }],
    ['a path-like id', { request: '../../etc/passwd/........' }], ['an id with spaces', { request: 'aaaa bbbb cccc dddd eeee' }],
    ['an oversized id', { request: 'a'.repeat(300) }], ['another parameter', { token: TOKEN }]])('drops an unusable request id: %s', async (_name, value) => {
    const page = await SignInPage(value ? query(value as Record<string, string | string[]>) : {});
    expect(page.props.requestId).toBeNull();
  });
  it('is unavailable for the Authentik provider and for a bad provider value', async () => {
    vi.stubEnv('AUTH_PROVIDER', 'authentik');
    expect((await SignInPage(query({ request: REQUEST_ID }))).props.available).toBe(false);
    vi.stubEnv('AUTH_PROVIDER', 'nonsense');
    expect((await SignInPage(query({ request: REQUEST_ID }))).props.available).toBe(false);
  });
});

describe('reset page', () => {
  it('hands a well-formed token to the form and is private and dynamic', async () => {
    expect((await ResetPage(query({ token: TOKEN }))).props).toEqual({ token: TOKEN, available: true });
    expect(resetDynamic).toBe('force-dynamic');
    expect(resetMetadata.referrer).toBe('no-referrer');
    expect(resetMetadata.robots).toEqual({ index: false, follow: false });
  });
  it.each([['no query', undefined], ['a repeated token', { token: [TOKEN, TOKEN] }], ['a short token', { token: 'abc' }],
    ['a tampered token', { token: `${TOKEN}<script>` }]])('drops an unusable token: %s', async (_name, value) => {
    const page = await ResetPage(value ? query(value as Record<string, string | string[]>) : {});
    expect(page.props.token).toBeNull();
  });
  it('is unavailable for the Authentik provider', async () => {
    vi.stubEnv('AUTH_PROVIDER', 'authentik');
    expect((await ResetPage(query({ token: TOKEN }))).props.available).toBe(false);
  });
});

describe('forgot-password page', () => {
  it('offers only administrator-issued links with the local provider, even when Authentik recovery is configured', async () => {
    vi.stubEnv('AUTHENTIK_ISSUER', 'https://authentik.test/application/o/janso/');
    vi.stubEnv('AUTHENTIK_SELF_SERVICE_RECOVERY_ENABLED', 'true');
    const page = await RecoveryPage({ searchParams: Promise.resolve({ returnTo: 'https://books.test/reports' }) });
    expect(page.props).toEqual({ destination: null, local: true, signInHref: '/login?returnTo=' + encodeURIComponent('https://books.test/reports') });
  });
  it('keeps the Authentik destination under the Authentik provider', async () => {
    vi.stubEnv('AUTH_PROVIDER', 'authentik');
    vi.stubEnv('AUTHENTIK_ISSUER', 'https://authentik.test/application/o/janso/');
    vi.stubEnv('AUTHENTIK_SELF_SERVICE_RECOVERY_ENABLED', 'true');
    const page = await RecoveryPage({});
    expect(page.props).toEqual({ destination: 'https://authentik.test/if/flow/bill-self-service-recovery/', signInHref: '/login' });
  });
});

describe('change-password page', () => {
  it('chooses the in-app form for the local provider and the provider hand-off otherwise, per request', () => {
    expect(changeDynamic).toBe('force-dynamic');
    expect(ChangePasswordPage().type).toBe(LocalChangePassword);
    vi.stubEnv('AUTH_PROVIDER', 'authentik');
    expect(ChangePasswordPage().type).toBe(ProviderChangePassword);
    vi.stubEnv('AUTH_PROVIDER', 'nonsense');
    expect(ChangePasswordPage().type).toBe(ProviderChangePassword);
  });
});
