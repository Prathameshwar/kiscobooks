import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountingConfigurationDetail } from '../app/components/AccountingConfigurationDetail';
import { AccountingConfigurationEditor } from '../app/components/AccountingConfigurationEditor';
import { AccountingConfigurationDirectory } from '../app/components/AccountingConfigurationDirectory';
import {
  accountingLink,
  accountingResource,
  accountingResources,
  type AccountingForm,
} from '../app/lib/accounting-configuration-resources';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';
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
vi.mock('../app/lib/navigate', async (original) => ({
  ...(await original<typeof import('../app/lib/navigate')>()),
  goTo: vi.fn(),
}));
const accountHere = accountingLink(
  '/accounting/accounts/' + ID,
  '/accounting/accounts?status=DRAFT',
);
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/accounting');
  vi.mocked(serviceCall).mockImplementation(
    async (_, request) =>
      response(request.path, request.method, request.body) as never,
  );
});
function detail(
  props: Partial<
    React.ComponentProps<typeof AccountingConfigurationDetail>
  > = {},
) {
  return (
    <AccountingConfigurationDetail
      company={COMPANY}
      config={accountingResource('accounts')!}
      id={ID}
      canManage
      canHistory
      availableResources={accountingResources.map((config) => config.resource)}
      returnTo="/accounting/accounts?status=DRAFT"
      {...props}
    />
  );
}
it('offers a shared account split button and account-scoped management links', async () => {
  render(detail());
  const split = await screen.findByRole('group', { name: 'Account actions' });
  expect(
    within(split).getByRole('link', { name: 'Edit account' }),
  ).toHaveAttribute(
    'href',
    accountingLink('/accounting/accounts/' + ID + '/edit', accountHere),
  );
  await userEvent.click(
    within(split).getByRole('button', { name: 'Account actions' }),
  );
  const aliases = screen
    .getByRole('menuitem', { name: 'Manage account aliases' })
    .getAttribute('href')!;
  const url = new URL(aliases, 'https://console.invalid');
  expect(url.pathname).toBe('/accounting/account-aliases');
  expect(url.searchParams.get('account_id')).toBe(ID);
  expect(url.searchParams.get('returnTo')).toBe(accountHere);
  expect(
    screen.getByRole('menuitem', { name: 'View history' }),
  ).toHaveAttribute(
    'href',
    accountingLink('/accounting/accounts/' + ID + '/history', accountHere),
  );
});
it('locks the originating account in a contextual supplementary creation form', async () => {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('account-aliases')!}
      prefills={{ account_id: ID }}
      returnTo={accountHere}
    />,
  );
  const account = await screen.findByRole('combobox', { name: /Account/ });
  expect(account).toBeDisabled();
  expect(
    screen.getByText(/This record belongs to the account you opened/),
  ).toBeVisible();
  expect(screen.getByRole('link', { name: 'Cancel' })).toHaveAttribute(
    'href',
    accountHere,
  );
});
it('blocks an account prefill that conflicts with its account return context', async () => {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('account-aliases')!}
      prefills={{ account_id: PARTY }}
      returnTo={accountHere}
    />,
  );
  await screen.findByRole('button', { name: 'Create account alias' });
  expect(
    screen.getByRole('button', { name: 'Create account alias' }),
  ).toBeDisabled();
  expect(screen.getByText(/The account context does not match/)).toBeVisible();
  expect(
    vi
      .mocked(serviceCall)
      .mock.calls.some(([, request]) => request.method === 'POST'),
  ).toBe(false);
});
it('offers only the independently manageable child creation links', async () => {
  render(
    detail({
      manageableResources: ['account-aliases', 'account-bank-profiles'],
    }),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Account actions' }),
  );
  const create = screen.getByRole('menuitem', { name: 'Create account alias' });
  const url = new URL(create.getAttribute('href')!, 'https://console.invalid');
  expect(url.pathname).toBe('/accounting/account-aliases/new');
  expect(url.searchParams.get('account_id')).toBe(ID);
  expect(url.searchParams.get('returnTo')).toBe(accountHere);
  expect(
    screen.queryByRole('menuitem', { name: 'Create tax profile' }),
  ).not.toBeInTheDocument();
  const bank = screen.getByRole('menuitem', { name: /Create bank profile/ });
  expect(bank).toHaveAttribute('aria-disabled', 'true');
  expect(bank).not.toHaveAttribute('href');
  await userEvent.click(bank);
  expect(
    vi
      .mocked(serviceCall)
      .mock.calls.every(
        ([, request]) => !request.method || request.method === 'GET',
      ),
  ).toBe(true);
});
it('allows a related master manager when the account itself is read-only', async () => {
  render(
    detail({
      canManage: false,
      availableResources: ['account-aliases'],
      manageableResources: ['account-aliases'],
    }),
  );
  const split = await screen.findByRole('group', { name: 'Account actions' });
  expect(
    within(split).getByRole('button', { name: 'Related configuration' }),
  ).toBeVisible();
  expect(
    screen.queryByRole('link', { name: 'Edit account' }),
  ).not.toBeInTheDocument();
  await userEvent.click(
    within(split).getByRole('button', { name: 'Related configuration' }),
  );
  expect(
    screen.getByRole('region', { name: 'Related account configuration' }),
  ).toHaveFocus();
  await userEvent.click(
    within(split).getByRole('button', { name: 'Account actions' }),
  );
  expect(
    screen.getByRole('menuitem', { name: 'Create account alias' }),
  ).toHaveAttribute('href');
  expect(
    screen.queryByRole('menuitem', { name: 'Activate' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('menuitem', { name: 'Manage account bank profiles' }),
  ).not.toBeInTheDocument();
});
it('uses a history link without an empty dropdown when no other action is permitted', async () => {
  render(detail({ canManage: false, availableResources: [] }));
  const split = await screen.findByRole('group', { name: 'Account actions' });
  expect(
    within(split).getByRole('link', { name: 'View history' }),
  ).toBeVisible();
  expect(within(split).queryByRole('button')).not.toBeInTheDocument();
});
it('withholds the split button until both record and field metadata are verified', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    if (request.path.includes('/field-set'))
      throw { status: 403, message: 'No field access' };
    return response(request.path, request.method, request.body) as never;
  });
  render(detail());
  await screen.findByText(/No field access/);
  expect(
    screen.queryByRole('group', { name: 'Account actions' }),
  ).not.toBeInTheDocument();
});
it('requires native manage hints for account edit and lifecycle actions', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    const value = response(request.path, request.method, request.body);
    if (request.path.includes('/configuration/accounts/field-set'))
      (value as AccountingForm).can_manage = false;
    return value as never;
  });
  render(detail({ manageableResources: ['account-aliases'] }));
  await userEvent.click(
    await screen.findByRole('button', { name: 'Account actions' }),
  );
  expect(
    screen.queryByRole('menuitem', { name: 'Activate' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('link', { name: 'Edit account' }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole('menuitem', { name: 'Create account alias' }),
  ).toHaveAttribute('href');
});
it('activates through the existing confirmed versioned command and updates available actions', async () => {
  render(detail({ manageableResources: ['posting-mappings'] }));
  await userEvent.click(
    await screen.findByRole('button', { name: 'Account actions' }),
  );
  expect(
    screen.getByRole('menuitem', { name: /Create posting default/ }),
  ).toHaveAttribute('aria-disabled', 'true');
  await userEvent.click(screen.getByRole('menuitem', { name: 'Activate' }));
  const dialog = screen.getByRole('dialog', { name: 'Activate this record?' });
  expect(
    screen.queryByRole('link', { name: 'Edit account' }),
  ).not.toBeInTheDocument();
  await userEvent.click(
    within(dialog).getByRole('button', { name: 'Activate record' }),
  );
  await screen.findByText('Record activated successfully.');
  const writes = vi
    .mocked(serviceCall)
    .mock.calls.filter(([, request]) => request.method === 'POST');
  expect(writes).toHaveLength(1);
  expect(writes[0][1].path).toBe(
    '/v1/companies/' + COMPANY + '/accounts/' + ID + '/activate',
  );
  expect(writes[0][1].body).toEqual({ expected_version: 3 });
  await userEvent.click(
    screen.getByRole('button', { name: 'Account actions' }),
  );
  expect(
    screen.getByRole('menuitem', { name: 'Create posting default' }),
  ).toHaveAttribute('href');
  expect(screen.getByRole('menuitem', { name: 'Retire' })).toBeVisible();
});
it('submits the protected account using native metadata and returns the saved child to the account', async () => {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('account-aliases')!}
      prefills={{ account_id: ID }}
      returnTo={accountHere}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Create account alias' }),
  );
  expect(
    vi
      .mocked(serviceCall)
      .mock.calls.filter(([, request]) => request.method === 'POST'),
  ).toHaveLength(0);
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Alias' }),
    'Retail sales',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create account alias' }),
  );
  await waitFor(() => expect(goTo).toHaveBeenCalled());
  const write = vi
    .mocked(serviceCall)
    .mock.calls.find(([, request]) => request.method === 'POST')![1];
  expect(write.body).toEqual({ account_id: ID, alias: 'Retail sales' });
  expect(write.key).toBeTruthy();
  expect(goTo).toHaveBeenCalledWith(
    accountingLink('/accounting/account-aliases/' + ID, accountHere),
  );
});
it('preserves account filters through a directory New action and its creation return chain', async () => {
  const list = accountingLink(
    '/accounting/account-aliases?account_id=' + ID,
    accountHere,
  );
  const view = render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('account-aliases')!}
      canManage
      initialQuery={new URL(list, 'https://console.invalid').search.slice(1)}
    />,
  );
  const create = await screen.findByRole('link', { name: 'New account alias' });
  const url = new URL(create.getAttribute('href')!, 'https://console.invalid');
  expect(url.searchParams.get('account_id')).toBe(ID);
  const back = url.searchParams.get('returnTo')!;
  expect(
    new URL(back, 'https://console.invalid').searchParams.get('account_id'),
  ).toBe(ID);
  view.unmount();
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('account-aliases')!}
      prefills={{ account_id: ID }}
      returnTo={back}
    />,
  );
  expect(
    await screen.findByRole('combobox', { name: /Account/ }),
  ).toBeDisabled();
  expect(screen.getByRole('link', { name: 'Cancel' })).toHaveAttribute(
    'href',
    back,
  );
  expect(screen.getByRole('link', { name: 'Back to account' })).toHaveAttribute(
    'href',
    accountHere,
  );
});
it('keeps the account selector editable for ordinary unscoped creation', async () => {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('account-aliases')!}
      returnTo="/accounting/account-aliases"
    />,
  );
  expect(
    await screen.findByRole('combobox', { name: /Account/ }),
  ).not.toBeDisabled();
  expect(
    screen.queryByRole('link', { name: 'Back to account' }),
  ).not.toBeInTheDocument();
});
it('preserves native owner field restrictions in contextual creation', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    const value = response(request.path, request.method, request.body);
    if (request.path.includes('/configuration/account-aliases/field-set')) {
      const owner = (value as AccountingForm).fields.find(
        (field) => field.key === 'account_id',
      )!;
      owner.editable = false;
      owner.writable = false;
      owner.readable = false;
      owner.visible = false;
    }
    return value as never;
  });
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('account-aliases')!}
      prefills={{ account_id: ID }}
      returnTo={accountHere}
    />,
  );
  expect(
    await screen.findByRole('button', { name: 'Create account alias' }),
  ).toBeDisabled();
  expect(
    screen.queryByRole('combobox', { name: /Account/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText(/A required field is hidden or protected/),
  ).toBeVisible();
});
it('keeps the related region correctly named for supplementary party pages', async () => {
  render(detail({ config: accountingResource('parties')! }));
  expect(
    await screen.findByRole('region', { name: 'Related configuration' }),
  ).toBeVisible();
  expect(
    screen.queryByRole('group', { name: 'Account actions' }),
  ).not.toBeInTheDocument();
});
