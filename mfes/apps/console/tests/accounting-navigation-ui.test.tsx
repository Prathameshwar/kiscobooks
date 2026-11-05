import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountingConfigurationDirectory } from '../app/components/AccountingConfigurationDirectory';
import {
  AccountingConfigurationDetail,
  AccountingConfigurationHistory,
} from '../app/components/AccountingConfigurationDetail';
import { AccountingReference } from '../app/components/AccountingConfigurationCommon';
import { AccountingConfigurationEditor } from '../app/components/AccountingConfigurationEditor';
import { AccountingExchangeDirectory } from '../app/components/AccountingExchangeRates';
import { TaxNavigation } from '../app/components/TaxCommon';
import {
  accountingBack,
  accountingLink,
  accountingResource,
  type AccountingForm,
} from '../app/lib/accounting-configuration-resources';
import { taxReturn } from '../app/lib/tax-masters';
import { accountingRelatedRowActions } from '../app/lib/accounting-masters';
import { serviceCall } from '../app/lib/service-call';
import {
  COMPANY,
  ID,
  PARTY,
  response,
  record,
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
const directory = accountingLink(
  '/accounting/parties?status=ACTIVE',
  '/settings',
);
const detail = accountingLink('/accounting/parties/' + ID, directory);
const url = (value: string) => new URL(value, 'https://console.invalid');
it('returns from tax directories to the consolidated Masters hub with an accurate label', () => {
  render(<TaxNavigation title="Tax rates" back="/masters" />);
  expect(screen.getByRole('link', { name: 'Back to masters' })).toHaveAttribute(
    'href',
    '/masters',
  );
});

it('offers direct View, Edit and history links from a filtered row menu', async () => {
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('parties')!}
      canManage
      canHistory
      initialQuery={directory.split('?')[1]}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Actions for Retail supplier' }),
  );
  for (const [label, suffix] of [
    ['View details', ''],
    ['Edit', '/edit'],
    ['View history', '/history'],
  ]) {
    const href = screen
      .getByRole('menuitem', { name: label })
      .getAttribute('href')!;
    expect(url(href).pathname).toBe('/accounting/parties/' + ID + suffix);
    expect(url(href).searchParams.get('returnTo')).toBe(directory);
  }
});
it.each(['account-heads', 'charge-policies'])(
  'does not offer unsupported mutations for %s',
  async (resource) => {
    render(
      <AccountingConfigurationDirectory
        company={COMPANY}
        config={accountingResource(resource)!}
        canManage
        canHistory
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', { name: /Actions for/ }),
    );
    expect(
      screen.getByRole('menuitem', { name: 'View details' }),
    ).toBeVisible();
    expect(
      screen.queryByRole('menuitem', { name: 'Edit' }),
    ).not.toBeInTheDocument();
    if (resource === 'charge-policies')
      expect(
        screen.queryByRole('menuitem', { name: 'View history' }),
      ).not.toBeInTheDocument();
  },
);
it('withholds history and Edit without their company grants', async () => {
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('parties')!}
      canManage={false}
      canHistory={false}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: /Actions for/ }),
  );
  expect(screen.queryByRole('menuitem', { name: 'Edit' })).not.toBeInTheDocument();
  expect(screen.queryByRole('menuitem', { name: 'View history' })).not.toBeInTheDocument();
  expect(screen.getByRole('menuitem', { name: 'View details' })).toBeVisible();
});
it('links related accounts through the row kebab only with target read access', async () => {
  const view = render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('parties')!}
      canManage={false}
      availableResources={['accounts']}
      initialQuery="status=ACTIVE"
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: /Actions for/ }),
  );
  const href = screen
    .getByRole('menuitem', { name: 'View ledger accounts' })
    .getAttribute('href')!;
  expect(url(href).pathname).toBe('/accounting/accounts');
  expect(url(href).searchParams.get('party_id')).toBe(ID);
  expect(url(href).searchParams.get('returnTo')).toContain('status=ACTIVE');
  await userEvent.keyboard('{Escape}');
  view.rerender(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('parties')!}
      canManage={false}
      availableResources={[]}
    />,
  );
  await userEvent.click(screen.getByRole('button', { name: /Actions for/ }));
  expect(
    screen.queryByRole('menuitem', { name: 'View ledger accounts' }),
  ).not.toBeInTheDocument();
});
it('requires explicit clearing of a protected relationship filter before loading an unfiltered register', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    const data = response(request.path, request.method, request.body);
    if (request.path.includes('/configuration/accounts/field-set')) {
      const fields = data as AccountingForm;
      fields.filter_keys = (fields.filter_keys ?? []).filter(
        (key) => key !== 'party_id',
      );
      fields.fields.forEach((field) => {
        if (field.key === 'party_id') {
          field.readable = false;
          field.visible = false;
        }
      });
    }
    return data as never;
  });
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('accounts')!}
      canManage
      initialQuery={
        'party_id=' + PARTY + '&returnTo=%2Faccounting%2Fparties%2F' + ID
      }
    />,
  );
  expect(
    await screen.findByText(/requested relationship filter is unavailable/),
  ).toBeVisible();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(
    screen.queryByRole('link', { name: 'New account' }),
  ).not.toBeInTheDocument();
  expect(
    vi
      .mocked(serviceCall)
      .mock.calls.some(([, request]) => request.path.includes('/accounts?')),
  ).toBe(false);
  await waitFor(() => expect(window.location.search).toContain('party_id'));
  await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
  await screen.findByRole('table');
  expect(window.location.search).not.toContain('party_id');
});
it('blocks an invalid relationship identifier until filters are explicitly cleared', async () => {
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('accounts')!}
      canManage={false}
      initialQuery="party_id=bad-id"
    />,
  );
  expect(
    await screen.findByText(/requested relationship filter is unavailable/),
  ).toBeVisible();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(
    vi
      .mocked(serviceCall)
      .mock.calls.some(([, request]) => request.path.includes('/accounts?')),
  ).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
  await screen.findByRole('table');
});
it('uses the Suppliers directory in supplier editor breadcrumbs', async () => {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('parties')!}
      supplier
      returnTo="/accounting/suppliers?role=SUPPLIER"
    />,
  );
  await screen.findByRole('button', { name: 'Create supplier' });
  expect(
    within(screen.getByRole('navigation', { name: 'Breadcrumb' })).getByRole(
      'link',
      { name: 'Suppliers' },
    ),
  ).toHaveAttribute('href', '/accounting/suppliers?role=SUPPLIER');
  expect(
    screen.queryByRole('link', { name: 'Exchange rates' }),
  ).not.toBeInTheDocument();
});
it('keeps the filtered resource directory and saved details in history breadcrumbs', async () => {
  render(
    <AccountingConfigurationHistory
      company={COMPANY}
      config={accountingResource('parties')!}
      id={ID}
      returnTo={detail}
    />,
  );
  await screen.findByRole('table', { name: 'Configuration history' });
  const navigation = within(
    screen.getByRole('navigation', { name: 'Breadcrumb' }),
  );
  expect(navigation.getByRole('link', { name: 'Parties' })).toHaveAttribute(
    'href',
    directory,
  );
  expect(
    navigation.getByRole('link', { name: 'Party details' }),
  ).toHaveAttribute('href', detail);
  expect(
    screen.getByRole('link', { name: 'Back to party details' }),
  ).toHaveAttribute('href', detail);
});
it('opens a verified tax rule and returns to the Accounting origin', async () => {
  render(
    <AccountingReference
      company={COMPANY}
      source="catalog:tax-rules"
      label="Tax rule"
      value={ID}
      disabled
      onChange={() => {}}
      returnTo={detail}
    />,
  );
  const href = (
    await screen.findByRole('link', { name: 'Open tax rule' })
  ).getAttribute('href')!;
  expect(url(href).pathname).toBe('/tax/rules/' + ID);
  const parent = url(href).searchParams.get('returnTo')!;
  expect(taxReturn(parent)).toBe(detail);
});
it('labels a tax page return to Accounting correctly', () => {
  render(<TaxNavigation title="Tax rule details" back={detail} />);
  expect(
    screen.getByRole('link', { name: 'Back to party details' }),
  ).toHaveAttribute('href', detail);
});
it('does not expose a reference link before hydration or after a denied lookup', async () => {
  vi.mocked(serviceCall).mockRejectedValue({
    status: 403,
    message: 'Reference access denied',
  });
  render(
    <AccountingReference
      company={COMPANY}
      source="catalog:tax-rules"
      label="Tax rule"
      value={ID}
      disabled
      onChange={() => {}}
      returnTo={detail}
    />,
  );
  expect(
    screen.queryByRole('link', { name: 'Open tax rule' }),
  ).not.toBeInTheDocument();
  expect(await screen.findByText('Reference access denied')).toBeVisible();
  expect(
    screen.queryByRole('link', { name: 'Open tax rule' }),
  ).not.toBeInTheDocument();
});
it('hydrates historical references without create-time ACTIVE eligibility filters', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_, request) =>
    request.path.endsWith('/accounts/' + ID)
      ? ({
          ...record('accounts'),
          party_id: PARTY,
          kind: 'PARTY',
          party_role: 'SUPPLIER',
        } as never)
      : (response(request.path, request.method, request.body) as never),
  );
  render(
    <AccountingConfigurationDetail
      company={COMPANY}
      config={accountingResource('accounts')!}
      id={ID}
      canManage={false}
      canHistory={false}
      availableResources={[]}
    />,
  );
  await screen.findByRole('link', { name: 'Open party' });
  const calls = vi
    .mocked(serviceCall)
    .mock.calls.filter(
      ([, request]) =>
        request.path.includes('/configuration/options/parties') &&
        request.path.includes('value='),
    );
  expect(calls.length).toBeGreaterThan(0);
  expect(url(calls[0][1].path).searchParams.has('status')).toBe(false);
});
it('provides an explicit commercial type assignment with a safe return', async () => {
  render(
    <AccountingConfigurationDetail
      company={COMPANY}
      config={accountingResource('party-commercial-types')!}
      id={ID}
      canManage
      canHistory={false}
      availableResources={['party-commercial-type-memberships']}
      returnTo="/accounting/party-commercial-types"
    />,
  );
  const href = (
    await screen.findByRole('link', { name: 'Assign to a party' })
  ).getAttribute('href')!;
  expect(url(href).pathname).toBe(
    '/accounting/party-commercial-type-memberships/new',
  );
  expect(url(href).searchParams.get('commercial_type_id')).toBe(ID);
  expect(accountingBack(url(href).searchParams.get('returnTo')!)).toContain(
    '/accounting/party-commercial-types/' + ID,
  );
});
it('only links chart setup for a permitted reader', async () => {
  const view = render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('account-heads')!}
      canManage={false}
      canSetup
    />,
  );
  await screen.findByRole('table');
  expect(
    await screen.findByRole('link', { name: 'Open company accounting setup' }),
  ).toHaveAttribute(
    'href',
    expect.stringContaining('/accounting/setup?returnTo='),
  );
  view.rerender(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('account-heads')!}
      canManage={false}
      canSetup={false}
    />,
  );
  expect(
    screen.queryByRole('link', { name: 'Open company accounting setup' }),
  ).not.toBeInTheDocument();
});
it.each([
  ['account-heads', 'account-groups', 'head_id'],
  ['account-groups', 'account-groups', 'parent_id'],
  ['account-groups', 'accounts', 'group_id'],
  ['accounts', 'charge-policies', 'account_id'],
  ['payment-terms', 'payment-term-lines', 'payment_term_id'],
  ['withholding-sections', 'withholding-rates', 'section_id'],
])(
  'uses the native related filter for %s to %s',
  (resource, target, filter) => {
    const actions = accountingRelatedRowActions(
      resource,
      ID,
      [target],
      directory,
    );
    const href = actions.find((action) =>
      url(action.href).searchParams.has(filter),
    )!.href;
    expect(url(href).pathname).toBe('/accounting/' + target);
    expect(url(href).searchParams.get(filter)).toBe(ID);
    expect(url(href).searchParams.get('returnTo')).toBe(directory);
    expect(accountingRelatedRowActions(resource, ID, [], directory)).toEqual(
      [],
    );
    expect(
      accountingRelatedRowActions(resource, 'bad-id', [target], directory),
    ).toEqual([]);
  },
);
it('synchronizes exchange register filters with a reusable URL', async () => {
  render(
    <AccountingExchangeDirectory
      company={COMPANY}
      canManage={false}
      initialQuery="status=CANDIDATE&returnTo=%2Fsettings"
    />,
  );
  await screen.findByRole('table');
  await waitFor(() =>
    expect(window.location.pathname).toBe('/accounting/exchange-rates'),
  );
  expect(url(window.location.href).searchParams.get('status')).toBe(
    'CANDIDATE',
  );
  expect(url(window.location.href).searchParams.get('returnTo')).toBe(
    '/settings',
  );
  await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
  await waitFor(() => expect(window.location.search).not.toContain('status'));
});
it.each([
  '/accounting/setup/' + ID,
  '/accounting/charge-policies/' + ID + '/history',
  '/accounting/exchange-rates/' + ID + '/history',
  '/accounting/accounts/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaz',
])('rejects a return path with no implemented page: %s', (path) =>
  expect(accountingBack(path)).toBe('/accounting'),
);
it.each([
  '//outside.example',
  '/accounting/../users',
  '/accounting/accounts/%2e%2e',
  '/accounting/parties?returnTo=https%3A%2F%2Foutside.example',
])(
  'keeps foreign tax returns within the implemented Accounting workflow: %s',
  (path) => {
    const target = taxReturn(path);
    expect(target).not.toContain('outside.example');
    expect(target).not.toContain('/users');
  },
);
