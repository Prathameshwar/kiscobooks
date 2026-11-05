import { beforeEach, expect, it, vi } from 'vitest';
import { registrationChoices } from '../../app/lib/registration-regions-server';
import { parseChoices, parseRegion, regionErrors } from '../../app/lib/registration-regions';

const options = { countries: [{ code: 'IN', name: 'India' }],
  states: [{ code: 'IN-MH', name: 'Maharashtra', country_code: 'IN' }] };
beforeEach(() => { vi.stubEnv('IDENTITY_URL', 'http://localhost:8001');
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => Response.json(options))); });
it('reads only the fixed bounded public endpoint with no caller credentials', async () => {
  expect(await registrationChoices()).toEqual(options);
  expect(fetch).toHaveBeenCalledWith(new URL('http://localhost:8001/v1/registration/options'), expect.objectContaining({
    redirect: 'error', cache: 'no-store', headers: { Accept: 'application/json' },
  }));
});
it.each(['file:///private', 'http://database.internal/', 'https://user:secret@identity.test/', 'https://identity.test/?key=value'])('rejects unsafe server configuration (%s)', async url => {
  vi.stubEnv('IDENTITY_URL', url); await expect(registrationChoices()).rejects.toThrow(); expect(fetch).not.toHaveBeenCalled();
});
it.each([{}, { countries: [], states: [] }, { ...options, states: [{ ...options.states[0], country_code: 'US' }] },
  { ...options, countries: [...options.countries, ...options.countries] },
  { ...options, states: new Array(10001).fill(options.states[0]) }])('fails closed for malformed reference data', async value => {
  vi.mocked(fetch).mockResolvedValueOnce(Response.json(value)); await expect(registrationChoices()).rejects.toThrow();
});
it('accepts countries without subdivisions and rejects arbitrary region metadata', () => {
  expect(regionErrors({ country_code: 'IN', state_code: '' }, { countries: options.countries, states: [] })).toEqual({});
  expect(regionErrors({ country_code: 'IN', state_code: 'IN-MH' }, { countries: options.countries, states: [] })).toHaveProperty('state_code');
  expect(parseRegion({ country_code: 'in', state_code: 'IN-MH' })).toBeNull();
  expect(parseRegion({ country_code: 'IN', state_code: 'US-CA', admin: true })).toEqual({ country_code: 'IN', state_code: 'US-CA' });
  expect(parseChoices({ ...options, password: 'ignored' })).toEqual(options);
});
