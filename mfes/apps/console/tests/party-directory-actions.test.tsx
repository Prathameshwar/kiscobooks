import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountingConfigurationDirectory } from '../app/components/AccountingConfigurationDirectory';
import { accountingResource } from '../app/lib/accounting-configuration-resources';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, ID, response } from './accounting-configuration-fixtures';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
const api = vi.mocked(serviceCall);
let enabled: string[], configurationCompany: string, unavailable: boolean;
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/accounting');
  enabled = ['inventory', 'multi_price_levels', 'credit_limits'];
  configurationCompany = COMPANY;
  unavailable = false;
  api.mockImplementation(async (_, request) => {
    if (request.path.endsWith('/setup-readiness')) {
      if (unavailable)
        throw { status: 503, message: 'Configuration unavailable' };
      return {
        company_id: configurationCompany,
        features: ['inventory', 'multi_price_levels', 'credit_limits'].map(
          (feature_key) => ({
            feature_key,
            state: enabled.includes(feature_key) ? 'ENABLED' : 'DISABLED',
          }),
        ),
      } as never;
    }
    return response(request.path, request.method, request.body) as never;
  });
});
async function directory(
  options: {
    supplier?: boolean;
    readConfiguration?: boolean;
    manage?: boolean;
    credit?: boolean;
    pricing?: boolean;
  } = {},
) {
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('parties')!}
      canManage={false}
      supplier={options.supplier}
      initialQuery="q=Retail"
      availableResources={
        options.credit === false ? [] : ['party-credit-policies']
      }
      manageableResources={
        options.manage === false ? [] : ['party-credit-policies']
      }
      canReadCompanyConfiguration={options.readConfiguration !== false}
      canManagePartyPricing={options.pricing !== false}
    />,
  );
  await screen.findByRole('table');
  await userEvent.click(
    screen.getByRole('button', { name: /Actions for Retail supplier/ }),
  );
}
it.each([false, true])(
  'opens the selected party credit limits and preserves the list (%s)',
  async (supplier) => {
    await directory({ supplier });
    const action = await screen.findByRole('menuitem', {
      name: 'Manage credit limits',
    });
    await waitFor(() => expect(action).toHaveAttribute('href'));
    const target = new URL(
      action.getAttribute('href')!,
      'https://console.invalid',
    );
    expect(target.pathname).toBe('/accounting/party-credit-policies');
    expect(target.searchParams.get('party_id')).toBe(ID);
    expect(target.searchParams.get('returnTo')).toContain(
      supplier ? '/accounting/suppliers?' : '/accounting/parties?',
    );
    expect(target.searchParams.get('returnTo')).toContain('q=Retail');
    expect(
      screen.queryByRole('menuitem', { name: 'Edit' }),
    ).not.toBeInTheDocument();
  },
);
it('uses read authority independently of permission to edit a party', async () => {
  await directory({ manage: false });
  expect(
    await screen.findByRole('menuitem', { name: 'View credit limits' }),
  ).toHaveAttribute('href');
  expect(
    screen.queryByRole('menuitem', { name: 'Manage credit limits' }),
  ).not.toBeInTheDocument();
});
it('hides management actions when their target permissions are absent', async () => {
  await directory({ credit: false, pricing: false });
  expect(
    screen.queryByRole('menuitem', { name: /credit limits/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('menuitem', { name: 'Manage pricing' }),
  ).not.toBeInTheDocument();
  expect(
    api.mock.calls.some(([, request]) =>
      request.path.endsWith('/setup-readiness'),
    ),
  ).toBe(false);
});
it.each(['inventory', 'multi_price_levels'])(
  'hides pricing when %s is disabled',
  async (feature) => {
    enabled = enabled.filter((key) => key !== feature);
    await directory();
    await waitFor(() =>
      expect(
        screen.queryByRole('menuitem', { name: 'Manage pricing' }),
      ).not.toBeInTheDocument(),
    );
  },
);
it('disables credit limits when company enforcement is disabled', async () => {
  enabled = enabled.filter((key) => key !== 'credit_limits');
  await directory();
  expect(
    screen.getByRole('menuitem', { name: /Manage credit limits/ }),
  ).toHaveAttribute('aria-disabled', 'true');
  expect(
    screen.getByText(/Enable credit limits in Company Config/),
  ).toBeVisible();
});
it.each(['other-company', 'outage', 'unreadable'])(
  'fails closed for %s configuration',
  async (scenario) => {
    if (scenario === 'other-company') configurationCompany = ID;
    if (scenario === 'outage') unavailable = true;
    await directory({ readConfiguration: scenario !== 'unreadable' });
    const action = screen.getByRole('menuitem', {
      name: /Manage credit limits/,
    });
    expect(action).toHaveAttribute('aria-disabled', 'true');
    expect(action).not.toHaveAttribute('href');
    expect(
      screen.getByRole('menuitem', { name: /Manage pricing/ }),
    ).toHaveAttribute('aria-disabled', 'true');
    if (scenario === 'unreadable')
      expect(
        api.mock.calls.some(([, request]) =>
          request.path.endsWith('/setup-readiness'),
        ),
      ).toBe(false);
  },
);
it('keeps pricing, ledger and bill adjustment unavailable without inventing destinations or writes', async () => {
  await directory();
  for (const label of [
    'Manage pricing',
    'Check ledger',
    'Pending bills for adjustment',
  ]) {
    const action = screen.getByRole('menuitem', { name: new RegExp(label) });
    expect(action).toHaveAttribute('aria-disabled', 'true');
    expect(action).not.toHaveAttribute('href');
    await userEvent.click(action);
  }
  expect(
    api.mock.calls.every(
      ([, request]) => !request.method || request.method === 'GET',
    ),
  ).toBe(true);
  expect(
    screen.getByText('Party-specific pricing management is not available yet.'),
  ).toBeVisible();
});
it('refreshes configuration after an outage without blocking the directory', async () => {
  unavailable = true;
  await directory();
  expect(
    screen.getByRole('menuitem', { name: /Manage credit limits/ }),
  ).toHaveAttribute('aria-disabled', 'true');
  await userEvent.keyboard('{Escape}');
  unavailable = false;
  await userEvent.click(
    screen.getByRole('button', { name: 'Refresh' }),
  );
  await waitFor(() =>
    expect(
      api.mock.calls.filter(([, request]) =>
        request.path.endsWith('/setup-readiness'),
      ).length,
    ).toBe(2),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: /Actions for Retail supplier/ }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole('menuitem', { name: 'Manage credit limits' }),
    ).toHaveAttribute('href'),
  );
});
