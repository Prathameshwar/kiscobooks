import { expect, it } from 'vitest';
import { allowedVoucherRequest } from '../app/lib/voucher-request-policy';
const id = '10000000-0000-7000-8000-000000000001';
const path = `/v1/companies/${id}/vouchers/${id}/revisions/${id}`;
it('permits only GET for company-scoped immutable voucher revisions', () => {
  expect(allowedVoucherRequest('GET', path)).toBe(true);
  for (const method of ['POST', 'PUT', 'DELETE', 'PATCH']) expect(allowedVoucherRequest(method, path)).toBe(false);
});
it.each(['/extra', '/..', '/%2f', '#fragment'])('refuses malformed historical revision paths: %s', suffix => expect(allowedVoucherRequest('GET', path + suffix)).toBe(false));
