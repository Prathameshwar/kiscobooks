import { expect, it } from 'vitest';
import { NextRequest } from 'next/server';
import { middleware } from '../middleware';
it('preserves the current page and replaces untrusted return-path headers', () => {
  const response = middleware(new NextRequest('https://console.test/vouchers?draft=1',
    { headers: { 'x-janso-return-path': '//evil.test' } }));
  expect(response.headers.get('x-middleware-request-x-janso-return-path')).toBe('/vouchers?draft=1');
});
it.each([['unavailable', 503], ['access', 403]])('renders recovery with an uncached refusal status: %s', (reason, status) => {
  const response = middleware(new NextRequest('https://console.test/session-recovery?reason=' + reason));
  expect(response.status).toBe(status);
  expect(response.headers.get('cache-control')).toBe('no-store');
  expect(response.headers.get('x-robots-tag')).toBe('noindex');
});
