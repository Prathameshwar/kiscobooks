import { describe, expect, it } from 'vitest';
import { allowedAccountingConfigurationRequest } from '../app/lib/accounting-configuration-policy';

const company = '10000000-0000-7000-8000-000000000001';
const base = `/v1/companies/${company}`;
const id = '10000000-0000-7000-8000-000000000009';

/** The console only forwards the Accounting calls it has named; the bill's two create-and-ready commands are among them. */
describe('the console bridge for creating an account that is ready to use', () => {
  it('forwards one POST to create-active, with no query', () => {
    expect(allowedAccountingConfigurationRequest('POST', `${base}/accounts/create-active`)).toBe(true);
  });

  it.each([
    ['GET', `${base}/accounts/create-active`],
    ['PATCH', `${base}/accounts/create-active`],
    ['DELETE', `${base}/accounts/create-active`],
    ['PUT', `${base}/accounts/create-active`],
    ['POST', `${base}/accounts/create-active?force=1`],
    ['POST', `${base}/accounts/create-active/extra`],
    ['POST', `${base}/accounts/CREATE-ACTIVE`],
    ['POST', `${base}/accounts/create%2dactive`],
    ['POST', `${base}/parties/create-active`],
    ['POST', `${base}/account-groups/create-active`],
    ['POST', `/v1/companies/not-a-company/accounts/create-active`],
  ])('refuses %s %s', (method, path) => {
    expect(allowedAccountingConfigurationRequest(method, path)).not.toBe(true);
  });

  it('leaves the ordinary account routes as they were', () => {
    expect(allowedAccountingConfigurationRequest('POST', `${base}/accounts`)).toBe(true);
    expect(allowedAccountingConfigurationRequest('POST', `${base}/accounts/${id}/activate`)).toBe(true);
    expect(allowedAccountingConfigurationRequest('GET', `${base}/accounts/${id}`)).toBe(true);
    expect(allowedAccountingConfigurationRequest('POST', `${base}/accounts/${id}`)).toBe(false);
    expect(allowedAccountingConfigurationRequest('POST', `${base}/parties/create-with-details`)).toBe(true);
  });
});
