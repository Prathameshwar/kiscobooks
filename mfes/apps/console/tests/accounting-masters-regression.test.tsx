import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountingConfigurationDirectory } from '../app/components/AccountingConfigurationDirectory';
import { AccountingReference } from '../app/components/AccountingConfigurationCommon';
import { accountingBody } from '../app/lib/accounting-configuration';
import {
  accountingResource,
  type AccountingField,
} from '../app/lib/accounting-configuration-resources';
import { allowedAccountingConfigurationRequest as allowed } from '../app/lib/accounting-configuration-policy';
import { serviceCall } from '../app/lib/service-call';
import {
  COMPANY,
  ID,
  PARTY,
  response,
} from './accounting-configuration-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/accounting');
  vi.mocked(serviceCall).mockImplementation(
    async (_, request) =>
      response(request.path, request.method, request.body) as never,
  );
});
it('exposes the native FX and charge workflows through the closed bridge', () => {
  const base = `/v1/companies/${COMPANY}`;
  expect(allowed('GET', base + '/exchange-rates/context')).toBe(true);
  expect(allowed('POST', base + '/exchange-rates/candidates')).toBe(true);
  expect(allowed('POST', base + '/exchange-rates/' + ID + '/approve')).toBe(
    true,
  );
  expect(allowed('POST', base + '/charge-policies/' + ID + '/close')).toBe(
    true,
  );
  expect(allowed('PATCH', base + '/charge-policies/' + ID)).toBe(false);
});
it('sends native integer enum values as numbers', () => {
  const field = {
    key: 'day_basis',
    label: 'Day basis',
    editable: true,
    visible: true,
    readable: true,
    writable: true,
    required: true,
    definition: { type: 'integer', enum: [360, 365] },
    control: { kind: 'select', choices: ['360', '365'], nullable: false },
  } as AccountingField;
  expect(accountingBody([field], { day_basis: '365' }).body).toEqual({
    day_basis: 365,
  });
});
it('allows an inherited party filter to be cleared', async () => {
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('accounts')!}
      canManage
      initialQuery={'party_id=' + PARTY}
    />,
  );
  await screen.findByRole('table');
  await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
  await waitFor(() => expect(window.location.search).not.toContain('party_id'));
});
it('links only hydrated native references back to their originating page', async () => {
  render(
    <AccountingReference
      company={COMPANY}
      source="parties"
      label="Party"
      value={PARTY}
      disabled
      onChange={() => {}}
      returnTo={'/accounting/accounts/' + ID}
    />,
  );
  expect(
    await screen.findByRole('link', { name: 'Open party' }),
  ).toHaveAttribute(
    'href',
    expect.stringContaining('/accounting/parties/' + PARTY + '?returnTo='),
  );
});
