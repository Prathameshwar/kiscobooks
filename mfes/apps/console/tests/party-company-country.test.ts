import { beforeEach, expect, it, vi } from 'vitest';
import { identityFetch } from '../app/identity-session';
import { partyCompanyCountry } from '../app/lib/party-company-country';
import { COMPANY } from './accounting-configuration-fixtures';

vi.mock('../app/identity-session', () => ({ identityFetch: vi.fn() }));
beforeEach(() => vi.clearAllMocks());

it('reads company country from the scoped company detail', async () => {
  vi.mocked(identityFetch).mockResolvedValue(Response.json({ country_code: 'US' }));
  expect(await partyCompanyCountry(COMPANY)).toBe('US');
  expect(identityFetch).toHaveBeenCalledWith(`/v1/companies/${COMPANY}`);
});
it.each([null, {}, { country_code: '' }, { country_code: 'INVALID' }])(
  'uses India when the company country is absent or invalid: %j', async (body) => {
    vi.mocked(identityFetch).mockResolvedValue(Response.json(body));
    expect(await partyCompanyCountry(COMPANY)).toBe('IN');
  },
);
it.each([403, 404, 503])('uses India when company detail returns %s', async (status) => {
  vi.mocked(identityFetch).mockResolvedValue(new Response(null, { status }));
  expect(await partyCompanyCountry(COMPANY)).toBe('IN');
});
