import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { getSession } from '../app/session';
import RecoveryPage from '../app/session-recovery/page';
import { recoveryPath } from '../app/lib/session-recovery';

const { read, go } = vi.hoisted(() => ({ read: vi.fn(), go: vi.fn() }));
vi.mock('../app/identity-session', () => ({ identityFetch: read }));
vi.mock('next/headers', () => ({
  cookies: async () => ({ get: () => undefined }),
  headers: async () => new Headers({ 'x-janso-return-path': '/masters?tab=items' }),
}));
vi.mock('next/navigation', () => ({ redirect: go }));
const detail = { user: { display_name: 'Reader', user_type: 'tenant_user' },
  tenant: { name: 'Tenant', slug: 'tenant' }, company: null, permissions: [], grants: [] };
beforeEach(() => { vi.clearAllMocks(); go.mockImplementation((url) => { throw Error('redirect:' + url); }); });
afterEach(() => vi.unstubAllEnvs());

it.each([403, 500, 502, 503])('fails closed into a recoverable page for refused bootstrap: %s', async (status) => {
  read.mockResolvedValue(Response.json({ error: { message: 'private details' } }, { status }));
  await expect(getSession()).rejects.toThrow('redirect:/session-recovery?');
  expect(go.mock.calls[0][0]).toContain(status === 403 ? 'reason=access' : 'reason=unavailable');
  expect(go.mock.calls[0][0]).toContain('returnTo=%2Fmasters%3Ftab%3Ditems');
  expect(go.mock.calls[0][0]).not.toContain('private');
});
it.each([null, {}, { ...detail, permissions: 'report.read' }])('rejects malformed successful session bodies', async (body) => {
  read.mockResolvedValue(Response.json(body));
  await expect(getSession()).rejects.toThrow('redirect:/session-recovery?');
});
it('handles invalid JSON without exposing parser or upstream details', async () => {
  read.mockResolvedValue(new Response('private upstream HTML'));
  await expect(getSession()).rejects.toThrow('redirect:/session-recovery?');
});
it('does not render a selected company with unavailable display settings', async () => {
  read.mockResolvedValueOnce(Response.json({ ...detail, company: { id: 'company', display_name: 'Books' } }))
    .mockResolvedValueOnce(Response.json({}, { status: 503 }));
  await expect(getSession()).rejects.toThrow('redirect:/session-recovery?');
});
it('rejects malformed display settings rather than applying currency/precision defaults', async () => {
  read.mockResolvedValueOnce(Response.json({ ...detail, company: { id: 'company', display_name: 'Books' } }))
    .mockResolvedValueOnce(Response.json({ amount_precision: '2' }));
  await expect(getSession()).rejects.toThrow('redirect:/session-recovery?');
});
it.each([
  { rounding_mode: 'unknown' }, { digit_grouping: 'unknown' }, { negative_format: 'unknown' },
  { currency_display: 'unknown' }, { currency_symbol_position: 'unknown' }, { decimal_separator: null },
])('rejects invalid formatting facts in an otherwise valid display response: %j', async (invalid) => {
  const display = { base_currency: 'INR', amount_precision: 2, quantity_precision: 3,
    timezone: 'Asia/Kolkata', locale: 'en', date_format: 'dd-MM-yyyy', datetime_format: 'dd-MM-yyyy HH:mm',
    rounding_mode: 'half_up', digit_grouping: 'indian', negative_format: 'minus',
    currency_display: 'symbol', currency_symbol_position: 'prefix', currency_symbol_override: null,
    decimal_separator: '.', thousands_separator: ',' };
  read.mockResolvedValueOnce(Response.json({ ...detail, company: { id: 'company', display_name: 'Books' } }))
    .mockResolvedValueOnce(Response.json({ ...display, ...invalid }));
  await expect(getSession()).rejects.toThrow('redirect:/session-recovery?');
});
it.each(['//evil.test', '/\\evil.test', '/%2f%2fevil.test', '/%5cevil.test', 'https://evil.test', '/session-recovery', '/%73ession-recovery', '/api/change', '/%61pi/change', '/bad%0apath'])('rejects unsafe or recursive recovery paths: %s', (path) => {
  expect(recoveryPath(path)).toBe('/');
});
it('renders safe retry and sign-in links without requesting private session data', async () => {
  render(await RecoveryPage({ searchParams: Promise.resolve({ reason: 'unavailable', returnTo: '/masters?tab=items' }) }));
  expect(screen.getByRole('heading', { name: 'Workspace temporarily unavailable' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Try again' })).toHaveAttribute('href', '/masters?tab=items');
  expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', expect.stringContaining('/login'));
  expect(read).not.toHaveBeenCalled();
});
