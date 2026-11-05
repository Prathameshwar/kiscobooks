import { expect, it, vi } from 'vitest';
import { allowedPurchasePrintRequest as allowed } from '../app/lib/purchase-print-policy';
import { purchasePrintHref, purchasePrintRequest, verifiedPurchasePdf } from '../app/lib/purchase-print';
import { sessionFetch } from '../app/lib/session-fetch';

vi.mock('../app/lib/session-fetch', () => ({ sessionFetch: vi.fn() }));

const id = '01990000-0000-7000-8000-000000000001';
const root = `/v1/companies/${id}`;
const job = `${root}/voucher-print-jobs/${id}`;

it.each([
  ['POST', `${root}/vouchers/${id}/print-jobs`], ['GET', job], ['GET', `${job}/download?token=abc.A_B-2`],
])('allows only the native print contract: %s %s', (method, path) => expect(allowed('vouchers', method, path)).toBe(true));

it.each([
  `${root}/vouchers/${id}/post`, `${job}/download`, `${job}/download?token=`,
  `${job}/download?token=abc&token=def`, `${job}/download?token=abc&company_id=${id}`,
  `${job}/download?token=abc#fragment`, `${job}/../${id}`, `${job}/%2e%2e`,
  `${job}?layout=anything`, `${job}?token=abc`, `https://host.invalid${job}`,
])('refuses widened or ambiguous paths: %s', path => expect(allowed('vouchers', 'GET', path)).toBe(false));

it('never permits another service, method or supplied HTML', () => {
  expect(allowed('design', 'GET', job)).toBe(false);
  expect(allowed('vouchers', 'DELETE', job)).toBe(false);
  expect(purchasePrintHref({ voucherId: id, revisionId: id, version: 3 })).toBe(`/vouchers/${id}/print?revision=${id}&version=3`);
});

it('verifies downloaded PDF bytes against the protected job digest and size', async () => {
  const data = new TextEncoder().encode('%PDF-1.7\nverified\n%%EOF');
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', data)), n => n.toString(16).padStart(2, '0')).join('');
  const info = { content_hash: hash, size_bytes: data.length } as Parameters<typeof verifiedPurchasePdf>[1];
  const response = () => new Response(data, { headers: { 'Content-Type': 'application/pdf' } });
  expect((await verifiedPurchasePdf(response(), info)).size).toBe(data.length);
  await expect(verifiedPurchasePdf(response(), { ...info, content_hash: 'a'.repeat(64) })).rejects.toThrow(/integrity/);
  await expect(verifiedPurchasePdf(new Response('html'), info)).rejects.toThrow(/format/);
});

it.each([[401, /session has expired/], [403, /access.*changed/], [409, /changed/],
  [422, /cannot be printed/], [500, /unavailable/]])('explains HTTP %s with a recovery action', async (status, message) => {
  vi.mocked(sessionFetch).mockResolvedValueOnce(new Response('{}', { status: status as number }));
  await expect(purchasePrintRequest(job, 'GET', new AbortController().signal)).rejects.toThrow(message as RegExp);
});
