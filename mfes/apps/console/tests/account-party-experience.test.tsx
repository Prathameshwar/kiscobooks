import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountingConfigurationDirectory } from '../app/components/AccountingConfigurationDirectory';
import { AccountingConfigurationEditor } from '../app/components/AccountingConfigurationEditor';
import { AccountingConfigurationDetail } from '../app/components/AccountingConfigurationDetail';
import { AccountingFields } from '../app/components/AccountingConfigurationCommon';
import { accountingResource } from '../app/lib/accounting-configuration-resources';
import { serviceCall } from '../app/lib/service-call';
import { accountingBody } from '../app/lib/accounting-configuration';
import { goTo } from '../app/lib/navigate';
import {
  COMPANY,
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
  config = (resource: string) => accountingResource(resource)!;
it.each(['accounts', 'parties'])(
  'shows a disabled merge placeholder on %s details without requiring edit access',
  async (resource) => {
    for (const canManage of [false, true]) {
      const view = render(
        <AccountingConfigurationDetail
          company={COMPANY}
          config={config(resource)}
          id={ID}
          canManage={canManage}
          canHistory={false}
          availableResources={[]}
        />,
      );
      const merge = await screen.findByRole('button', {
        name: resource === 'parties' ? 'Merge parties' : 'Merge accounts',
      });
      expect(merge).toBeDisabled();
      expect(merge).toHaveAccessibleDescription(
        'Merging duplicate ' +
          resource +
          ' will be available in a future update.',
      );
      await userEvent.click(merge);
      expect(
        api.mock.calls.every(
          ([, request]) => !request.method || request.method === 'GET',
        ),
      ).toBe(true);
      view.unmount();
    }
  },
);
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/accounting');
  api.mockImplementation(
    async (_, request) =>
      response(request.path, request.method, request.body) as never,
  );
});
it.each([false, true])(
  'shows disabled import beside New on the party/supplier directory (%s)',
  async (supplier) => {
    render(
      <AccountingConfigurationDirectory
        company={COMPANY}
        config={config('parties')}
        canManage
        supplier={supplier}
      />,
    );
    const create = await screen.findByRole('link', {
      name: supplier ? 'New supplier' : 'New party',
    });
    const link = screen.getByRole('link', {
      name: supplier ? 'Import suppliers' : 'Import parties',
    });
    expect(create.nextElementSibling).toBe(link);
    expect(link).toHaveAttribute('aria-disabled', 'true');
    expect(link).not.toHaveAttribute('href');
  },
);
it('uses a compact filter toolbar with secondary account reference filters', async () => {
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={config('accounts')}
      canManage
    />,
  );
  await screen.findByRole('table');
  expect(
    screen
      .getByRole('searchbox', { name: 'Search' })
      .closest('.janso-filter-bar'),
  ).not.toBeNull();
  expect(
    screen
      .getByRole('searchbox', { name: 'Search' })
      .closest('.janso-filter-bar')?.parentElement,
  ).toHaveClass('janso-flow');
  const summary = screen.getByText('More filters');
  expect(summary.closest('details')).not.toHaveAttribute('open');
  await userEvent.click(summary);
  expect(screen.getByRole('combobox', { name: 'Account group' })).toBeVisible();
});
it('gives parties readable status badges and both customer and supplier role choices', async () => {
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={config('parties')}
      canManage
    />,
  );
  const table = await screen.findByRole('table');
  expect(within(table).getByText('Draft')).toHaveClass('janso-badge');
  expect(screen.getByRole('option', { name: 'Brokers' })).toBeInTheDocument();
});
it('never says there are no accounts while the directory is loading', async () => {
  api.mockImplementation(async (_, request) =>
    request.path.includes('/accounts?')
      ? await new Promise<never>(() => {})
      : (response(request.path, request.method, request.body) as never),
  );
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={config('accounts')}
      canManage
    />,
  );
  await screen.findByRole('status', {
    name: 'Loading Accounting configuration',
  });
  expect(
    screen.queryByText('No accounts', { exact: true }),
  ).not.toBeInTheDocument();
});
it('gives account creation resource-specific sections and unique-code guidance', async () => {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={config('accounts')}
    />,
  );
  const code = await screen.findByRole('textbox', { name: 'Code' });
  expect(code).toHaveAccessibleDescription(expect.stringContaining('unique'));
  expect(
    screen.getByRole('heading', { name: 'Currency and rounding' }),
  ).toBeVisible();
  expect(
    screen.getByRole('heading', { name: 'Posting controls' }),
  ).toBeVisible();
});
it('places party identity and full-width notes in their respective wizard steps', async () => {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={config('parties')}
    />,
  );
  await screen.findByRole('textbox', { name: 'Legal name' });
  expect(screen.getByRole('heading', { name: 'Party details' })).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: /Tax and other details/ }));
  expect(
    screen
      .getByRole('textbox', { name: 'Notes' })
      .closest('.janso-form-grid__full'),
  ).not.toBeNull();
});
it('lets a duplicate party be corrected while preserving its other identity fields', async () => {
  let duplicate = true;
  api.mockImplementation(async (_, request) => {
    if (request.method === 'POST' && duplicate)
      throw { status: 409, message: 'Party code already exists.' };
    return response(request.path, request.method, request.body) as never;
  });
  // A party is created with its role and ledger account: the role is chosen and accounts can be created.
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={config('parties')}
      availableResources={['accounts']}
      manageableResources={['accounts']}
    />,
  );
  const code = await screen.findByRole('textbox', { name: 'Code' });
  fireEvent.change(code, { target: { value: 'DUPLICATE' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), {
    target: { value: 'Party review' },
  });
  fireEvent.change(screen.getByRole('textbox', { name: 'Legal name' }), {
    target: { value: 'Party review legal' },
  });
  await userEvent.click(screen.getByRole('combobox', { name: 'Country code' }));
  await userEvent.click(await screen.findByRole('option', { name: /India/ }));
  await userEvent.selectOptions(
    screen.getByRole('combobox', { name: 'Party role' }),
    'CUSTOMER',
  );
  await userEvent.click(screen.getByRole('button', { name: 'Create party' }));
  await screen.findByText('Party code already exists.');
  expect(code).toBeEnabled();
  duplicate = false;
  await userEvent.clear(code);
  await userEvent.type(code, 'UNIQUE');
  expect(screen.getByRole('textbox', { name: 'Legal name' })).toHaveValue(
    'Party review legal',
  );
  await userEvent.click(screen.getByRole('button', { name: 'Create party' }));
  await waitFor(() => expect(goTo).toHaveBeenCalled());
  const writes = api.mock.calls.filter(
    ([, request]) => request.method === 'POST',
  );
  expect(writes[0]![1].key).not.toBe(writes[1]![1].key);
  // The correction keeps the chosen role: the second request creates the same kind of party.
  expect(writes[1]![1].body).toMatchObject({ code: 'UNIQUE', role: 'CUSTOMER' });
});
it('presents party detail choices as facts rather than disabled selects', async () => {
  render(
    <AccountingConfigurationDetail
      company={COMPANY}
      config={config('parties')}
      id={ID}
      canManage
      canHistory
      availableResources={['parties', 'party-roles']}
      manageableResources={['party-roles']}
    />,
  );
  await screen.findByRole('heading', { level: 1, name: 'Retail supplier' });
  expect(
    screen.queryByRole('combobox', { name: 'Party type' }),
  ).not.toBeInTheDocument();
  expect(screen.getByText('Organisation', { exact: true })).toBeVisible();
});
it('associates textarea dependency guidance and errors with its control', () => {
  const field = form('accounts').fields.find(
    (field) => field.key === 'description',
  )!;
  render(
    <AccountingFields
      company={COMPANY}
      resource="accounts"
      fields={[
        {
          ...field,
          control: {
            ...field.control,
            disabled_reason: 'This description is protected.',
          },
        },
      ]}
      values={{ description: '' }}
      onChange={vi.fn()}
      errors={{ description: 'Check the description.' }}
    />,
  );
  expect(
    screen.getByRole('textbox', { name: 'Description' }),
  ).toHaveAccessibleDescription(
    'This description is protected. Check the description.',
  );
});

it('honours native create availability independently of manage authority', async () => {
  api.mockImplementation(async (_, request) => {
    const value = response(request.path, request.method, request.body);
    return request.path.includes('/configuration/parties/field-set')
      ? ({ ...(value as object), can_manage: true, can_create: false } as never)
      : (value as never);
  });
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={config('parties')}
      availableResources={['accounts']}
      manageableResources={['accounts']}
    />,
  );
  expect(
    await screen.findByRole('button', { name: 'Create party' }),
  ).toBeDisabled();
});

it('protects the parent party when adding a related role', async () => {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={config('party-roles')}
      prefills={{ party_id: ID, role: 'SUPPLIER' }}
      returnTo={'/accounting/parties/' + ID}
    />,
  );
  expect(await screen.findByRole('combobox', { name: 'Party' })).toBeDisabled();
  expect(
    screen.getByText(
      'This record belongs to the party you opened. The party selection is protected for this creation.',
    ),
  ).toBeVisible();
});
it('refuses conflicting party context rather than saving under another identity', async () => {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={config('party-roles')}
      prefills={{ party_id: COMPANY, role: 'SUPPLIER' }}
      returnTo={'/accounting/parties/' + ID}
    />,
  );
  expect(
    await screen.findByRole('button', { name: 'Create party role' }),
  ).toBeDisabled();
});
it('offers a primary party edit action and scoped role navigation', async () => {
  render(
    <AccountingConfigurationDetail
      company={COMPANY}
      config={config('parties')}
      id={ID}
      canManage
      canHistory
      availableResources={['parties', 'party-roles']}
      manageableResources={['party-roles']}
    />,
  );
  expect(await screen.findByRole('link', { name: 'Edit party' })).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Party actions' }));
  expect(
    screen.getByRole('menuitem', { name: 'Manage party roles' }),
  ).toHaveAttribute('href', expect.stringContaining('party_id=' + ID));
  expect(
    screen.queryByRole('menuitem', { name: 'Manage party contacts' }),
  ).not.toBeInTheDocument();
});

it('provides only permitted setup links from account creation', async () => {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={config('accounts')}
      availableResources={['accounts', 'account-groups', 'accounting-setup']}
    />,
  );
  expect(
    await screen.findByRole('link', { name: 'Review chart setup' }),
  ).toHaveAttribute('href', expect.stringContaining('/accounting/setup'));
  expect(
    screen.getByRole('link', { name: 'Manage account groups' }),
  ).toBeVisible();
  expect(
    screen.queryByRole('link', { name: 'Manage parties' }),
  ).not.toBeInTheDocument();
});
it('does not advertise a supplier-role write without its current grant', async () => {
  render(
    <AccountingConfigurationDetail
      company={COMPANY}
      config={config('parties')}
      id={ID}
      canManage={false}
      canHistory={false}
      availableResources={['parties']}
      supplierSetup
    />,
  );
  await screen.findByRole('heading', { level: 1, name: 'Retail supplier' });
  expect(
    screen.queryByRole('link', { name: 'add its supplier role' }),
  ).not.toBeInTheDocument();
});
it('keeps unavailable account navigation absent for a party-only reader', async () => {
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={config('parties')}
      canManage={false}
      availableResources={['parties']}
    />,
  );
  const nav = screen.getByRole('navigation', { name: 'Accounts and parties' });
  expect(within(nav).getByRole('link', { name: 'Parties' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  expect(
    within(nav).queryByRole('link', { name: 'Accounts' }),
  ).not.toBeInTheDocument();
  await screen.findByRole('table');
});

it('fails closed on Suppliers when role filtering is protected', async () => {
  api.mockImplementation(async (_, request) => {
    const value = response(request.path, request.method, request.body);
    return request.path.includes('/configuration/parties/field-set')
      ? ({
          ...(value as ReturnType<typeof form>),
          filter_keys: (value as ReturnType<typeof form>).filter_keys!.filter(
            (key) => key !== 'role',
          ),
        } as never)
      : (value as never);
  });
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={config('parties')}
      canManage
      supplier
    />,
  );
  await screen.findByText(
    'Supplier role filtering is unavailable with your field access.',
  );
  expect(
    api.mock.calls.some(([, request]) => request.path.includes('/parties?')),
  ).toBe(false);
  expect(
    screen.queryByRole('link', { name: 'Open Retail supplier' }),
  ).not.toBeInTheDocument();
});

it('accepts multiline notes and descriptions while rejecting non-printing control characters', () => {
  const note = form('parties').fields.find((field) => field.key === 'notes')!;
  expect(
    accountingBody([note], { notes: 'First line\nSecond line' }).errors,
  ).toEqual({});
  expect(
    accountingBody([note], { notes: 'First line\u0007Second line' }).errors
      .notes,
  ).toBeTruthy();
  const description = form('accounts').fields.find(
    (field) => field.key === 'description',
  )!;
  expect(
    accountingBody([description], { description: 'First line\nSecond line' })
      .errors,
  ).toEqual({});
});
