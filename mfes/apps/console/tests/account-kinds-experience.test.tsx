import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountingConfigurationDirectory } from '../app/components/AccountingConfigurationDirectory';
import { AccountingConfigurationEditor } from '../app/components/AccountingConfigurationEditor';
import { AccountingConfigurationDetail } from '../app/components/AccountingConfigurationDetail';
import { accountingResource } from '../app/lib/accounting-configuration-resources';
import { serviceCall } from '../app/lib/service-call';
import {
  COMPANY,
  GROUP,
  ID,
  form,
  response,
} from './accounting-configuration-fixtures';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  signInUrl: () => '/signin',
}));
const api = vi.mocked(serviceCall),
  config = accountingResource('accounts')!;
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/accounting');
  api.mockImplementation(
    async (_, request) =>
      response(request.path, request.method, request.body) as never,
  );
});

it('does not offer bank creation from a protected bank-profile edit', async () => {
  api.mockImplementation(async (_, request) => {
    if (request.path.includes('/configuration/account-bank-profiles')) {
      const metadata = form('account-bank-profiles', 'update');
      metadata.fields.forEach((field) => {
        field.editable = false;
      });
      return metadata as never;
    }
    return response(request.path, request.method, request.body) as never;
  });
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('account-bank-profiles')!}
      id={ID}
      canCreateCompanyBank
    />,
  );
  await screen.findByRole('button', { name: 'Save changes' });
  expect(
    screen.queryByRole('link', { name: 'Add company bank' }),
  ).not.toBeInTheDocument();
});

it('preserves the selected account kind and group when creating from the directory', async () => {
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={config}
      canManage
      initialQuery={'kind=BANK&group_id=' + GROUP}
    />,
  );
  const link = await screen.findByRole('link', { name: 'New account' });
  await screen.findByRole('table');
  const target = new URL(link.getAttribute('href')!, 'https://console.invalid');
  expect(target.searchParams.get('kind')).toBe('BANK');
  expect(target.searchParams.get('group_id')).toBe(GROUP);
});

it('keeps linked-party creation consistent even with a conflicting kind filter', async () => {
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={config}
      canManage
      initialQuery={'kind=BANK&party_id=' + ID}
    />,
  );
  await screen.findByRole('table');
  const target = new URL(
    screen.getByRole('link', { name: 'New account' }).getAttribute('href')!,
    'https://console.invalid',
  );
  expect(target.searchParams.get('kind')).toBe('PARTY');
  expect(target.searchParams.get('party_id')).toBe(ID);
});

it.each([
  'GENERAL',
  'CASH',
  'BANK',
  'TAX',
  'INVENTORY_CONTROL',
  'ASSET_CONTROL',
])(
  'creates %s through the shared form without party attributes',
  async (kind) => {
    render(
      <AccountingConfigurationEditor
        company={COMPANY}
        config={config}
        prefills={{ kind, group_id: GROUP }}
      />,
    );
    fireEvent.change(await screen.findByRole('textbox', { name: 'Code' }), {
      target: { value: 'REVIEW-' + kind },
    });
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), {
      target: { value: kind + ' review' },
    });
    await userEvent.click(
      screen.getByRole('button', { name: 'Create account' }),
    );
    await waitFor(() =>
      expect(api.mock.calls.some(([, r]) => r.method === 'POST')).toBe(true),
    );
    const body = api.mock.calls.find(([, r]) => r.method === 'POST')![1].body;
    expect(body).toMatchObject({
      kind,
      group_id: GROUP,
      party_id: null,
      party_role: null,
    });
  },
);

it.each(['BANK', 'TAX'])(
  'surfaces the permitted %s profile area on a draft account',
  async (kind) => {
    api.mockImplementation(async (_, request) => {
      const result = response(request.path, request.method, request.body);
      if (request.path.endsWith('/accounts/' + ID))
        return { ...result, kind, used_at: null } as never;
      return result as never;
    });
    const resource =
      kind === 'BANK' ? 'account-bank-profiles' : 'account-tax-profiles';
    render(
      <AccountingConfigurationDetail
        company={COMPANY}
        config={config}
        id={ID}
        canManage
        canHistory
        availableResources={[resource]}
        manageableResources={[resource]}
      />,
    );
    const link = await screen.findByRole('link', {
      name: 'Review ' + kind.toLowerCase() + ' profile',
    });
    const target = new URL(
      link.getAttribute('href')!,
      'https://console.invalid',
    );
    expect(target.pathname).toBe('/accounting/' + resource);
    expect(target.searchParams.get('account_id')).toBe(ID);
  },
);

it('does not expose a bank profile route without permission to read it', async () => {
  api.mockImplementation(async (_, request) => {
    const result = response(request.path, request.method, request.body);
    return (
      request.path.endsWith('/accounts/' + ID)
        ? { ...result, kind: 'BANK', used_at: null }
        : result
    ) as never;
  });
  render(
    <AccountingConfigurationDetail
      company={COMPANY}
      config={config}
      id={ID}
      canManage
      canHistory
      availableResources={[]}
    />,
  );
  await screen.findByRole('heading', { name: 'Record details' });
  expect(
    screen.queryByRole('link', { name: 'Review bank profile' }),
  ).not.toBeInTheDocument();
});

it.each([true, false])(
  'offers company-bank creation only with its own company authority (%s)',
  async (canCreateCompanyBank) => {
    render(
      <AccountingConfigurationEditor
        company={COMPANY}
        config={accountingResource('account-bank-profiles')!}
        canCreateCompanyBank={canCreateCompanyBank}
        prefills={{ account_id: ID }}
        returnTo={'/accounting/accounts/' + ID}
      />,
    );
    await screen.findByRole('button', { name: 'Create bank profile' });
    const link = screen.queryByRole('link', { name: 'Add company bank' });
    if (canCreateCompanyBank) {
      expect(link).toBeInTheDocument();
      const target = new URL(
        link!.getAttribute('href')!,
        'https://console.invalid',
      );
      expect(target.pathname).toBe(
        '/companies/' + COMPANY + '/bank-accounts/new',
      );
      expect(
        new URL(target.searchParams.get('returnTo')!, target).searchParams.get(
          'account_id',
        ),
      ).toBe(ID);
    } else expect(link).not.toBeInTheDocument();
  },
);
