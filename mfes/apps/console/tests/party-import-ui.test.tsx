import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PartyImport } from '../app/components/PartyImport';
import { serviceCall } from '../app/lib/service-call';
import { downloadPartyImport } from '../app/lib/party-import';
import { accountingResource } from '../app/lib/accounting-configuration-resources';
import { AccountingConfigurationDirectory } from '../app/components/AccountingConfigurationDirectory';
import { response as accountingResponse } from './accounting-configuration-fixtures';
import { readiness } from './financial-opening-fixtures';
import {
  COMPANY,
  JOB,
  TEMPLATE,
  importResponse,
  job,
  template,
} from './product-import-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/party-import', async (original) => ({
  ...(await original<typeof import('../app/lib/party-import')>()),
  downloadPartyImport: vi.fn(),
}));
const api = vi.mocked(serviceCall);
let current = { ...job(), definition: 'parties' };
let blockers: string[] = [];
const partyTemplate = {
  ...template,
  definition: 'parties',
  snapshot: {
    schemas: Object.fromEntries(
      [
        'supplier:CREATE',
        'customer:CREATE',
        'party:CREATE',
        'party:UPDATE',
        'party_role:CREATE',
      ].map((key) => [
        key,
        {
          properties: {
            code: { type: 'string' },
            name: { type: 'string' },
            legal_name: { type: 'string' },
            country_code: { type: 'string' },
          },
          required: ['code', 'name', 'legal_name', 'country_code'],
        },
      ]),
    ),
  },
};
beforeEach(() => {
  vi.clearAllMocks();
  blockers = [];
  current = { ...job(), definition: 'parties' };
  window.history.replaceState(null, '', '/accounting/suppliers/import');
  api.mockImplementation(async (_, request) => {
    if (request.path.endsWith('/opening-batches/readiness'))
      return { ...readiness, blockers } as never;
    if (request.path.includes('/import-definitions'))
      return {
        items: [{ key: 'parties', label: 'Customers and suppliers' }],
        formats: ['CSV', 'TSV', 'XLSX'],
        maximum_commands: 200,
      } as never;
    if (request.path.includes('/import-templates'))
      return partyTemplate as never;
    if (request.path.endsWith('/validate'))
      current = { ...job('READY', 2), definition: 'parties' };
    if (request.path.endsWith('/commit'))
      current = { ...job('SUCCEEDED', 3), definition: 'parties' };
    const result = importResponse(request.path, current);
    if (request.path.includes('/records'))
      return {
        ...result,
        items: [
          {
            id: TEMPLATE,
            logical_key: 'supplier-1',
            resource: 'supplier',
            source_file: 'suppliers.csv',
            source_sheet: 'Records',
            source_row: 3,
            status: current.state === 'SUCCEEDED' ? 'APPLIED' : 'VALID',
            business_id: current.state === 'SUCCEEDED' ? TEMPLATE : null,
          },
        ],
      } as never;
    return result as never;
  });
});
it.each([false, true])(
  'uses Accounting templates and the shared layout for party/supplier (%s)',
  async (supplier) => {
    render(<PartyImport company={COMPANY} canManage supplier={supplier} />);
    expect(
      await screen.findByRole('heading', {
        name: supplier
          ? '1. Choose a supplier template'
          : '1. Choose a party template',
      }),
    ).toBeVisible();
    // A party is only ever created with its role and ledger account, so both pages open on a
    // ready-to-use resource: the party page on customers, the supplier page on suppliers.
    expect(
      screen.getByRole('combobox', { name: 'Import content' }),
    ).toHaveValue(supplier ? 'supplier' : 'customer');
    await userEvent.click(
      screen.getByRole('button', { name: 'Download template' }),
    );
    await waitFor(() => expect(downloadPartyImport).toHaveBeenCalled());
    const templateCall = api.mock.calls.find(([, request]) =>
      request.path.endsWith('/import-templates'),
    )!;
    expect(templateCall[0]).toBe('/api/party-import');
    expect(templateCall[1]).toMatchObject({
      service: 'accounting',
      body: {
        definition: 'parties',
        parameters: {
          resource: supplier ? 'supplier' : 'customer',
          role: supplier ? 'SUPPLIER' : 'CUSTOMER',
        },
      },
    });
    // Ready customers and suppliers only create: updating is not offered for them.
    expect(
      screen
        .getByRole('option', {
          name: supplier
            ? 'Update existing suppliers only'
            : 'Update existing parties only',
        })
        .hasAttribute('disabled'),
    ).toBe(true);
    expect(
      screen
        .getByRole('option', {
          name: supplier
            ? 'Create new suppliers only'
            : 'Create new parties only',
        })
        .hasAttribute('disabled'),
    ).toBe(false);
  },
);
it.each([
  { page: 'party page', supplier: false, resource: 'customer', role: 'CUSTOMER' },
  { page: 'supplier page', supplier: true, resource: 'supplier', role: 'SUPPLIER' },
])(
  'opens the $page on the ready $resource resource and prepares its role-matched template',
  async ({ supplier, resource, role }) => {
    render(<PartyImport company={COMPANY} canManage supplier={supplier} />);
    const content = await screen.findByRole('combobox', {
      name: 'Import content',
    });
    expect(content).toHaveValue(resource);
    expect(
      within(content).getByRole('option', {
        name: resource === 'customer'
          ? 'Ready-to-use customers'
          : 'Ready-to-use suppliers',
      }),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole('button', { name: 'Download template' }),
    );
    await waitFor(() => expect(downloadPartyImport).toHaveBeenCalled());
    const templateCall = api.mock.calls.find(([, request]) =>
      request.path.endsWith('/import-templates'),
    )!;
    expect(templateCall[1].body).toMatchObject({
      parameters: { resource, role },
    });
    expect(
      (templateCall[1].body as { parameters: { resource: string } }).parameters
        .resource,
    ).not.toBe('party');
  },
);
it('tells the reader that ready customers and suppliers create the role and its ledger account together', async () => {
  render(<PartyImport company={COMPANY} canManage />);
  await screen.findByRole('combobox', { name: 'Import content' });
  expect(
    screen.getByText(
      'Use one stable row key and group key per party. Ready-to-use suppliers and customers create and activate the identity, its matching role and its ledger account together. Related records can reference staged party IDs with $ref.',
    ),
  ).toBeVisible();
});
it('labels the plain party resource as update only and offers the update operation for it', async () => {
  render(<PartyImport company={COMPANY} canManage />);
  const content = await screen.findByRole('combobox', {
    name: 'Import content',
  });
  expect(
    within(content).getByRole('option', {
      name: 'Existing party identities (update only)',
    }),
  ).toBeInTheDocument();
  expect(
    within(content).queryByRole('option', { name: 'Party identities' }),
  ).not.toBeInTheDocument();
  await userEvent.selectOptions(content, 'party');
  expect(
    screen
      .getByRole('option', { name: 'Update existing parties only' })
      .hasAttribute('disabled'),
  ).toBe(false);
});
it('imports a reviewed supplier and links the resulting party identity', async () => {
  render(<PartyImport company={COMPANY} canManage supplier />);
  await userEvent.click(
    await screen.findByRole('button', { name: 'Download template' }),
  );
  await waitFor(() => expect(downloadPartyImport).toHaveBeenCalled());
  await userEvent.upload(
    document.querySelector<HTMLInputElement>('input[type=file]')!,
    new File(['supplier input'], 'suppliers.csv', { type: 'text/csv' }),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Upload and prepare validation' }),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Validate files' }),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Review import' }),
  );
  // The review says what the lifecycle is: the role and ledger account come with the identity.
  expect(
    screen.getByText(
      /Ready-to-use suppliers and customers become active together with their role and ledger account\. Plain party rows can only update, activate or deactivate an existing identity; activating a party role also creates its ledger account\./,
    ),
  ).toBeVisible();
  await userEvent.click(
    within(
      await screen.findByRole('dialog', {
        name: 'Import validated suppliers?',
      }),
    ).getByRole('button', { name: 'Import suppliers' }),
  );
  await screen.findByText(
    'Party import completed successfully. Review each imported identity and its roles. Opening balances in the file are held for Account and party openings; nothing is posted.',
  );
  expect(
    await screen.findByRole('link', { name: 'Open record' }),
  ).toHaveAttribute(
    'href',
    expect.stringContaining('/accounting/parties/' + TEMPLATE),
  );
  expect(
    api.mock.calls.every(
      ([endpoint, request]) =>
        request.service === 'accounting' &&
        (endpoint === '/api/party-import' ||
          // The opening guide only reads whether balances can still be added.
          (endpoint === '/api/financial-opening' &&
            request.path.endsWith('/opening-batches/readiness'))),
    ),
  ).toBe(true);
});
it('keeps shared Accounting history available without party write authority', async () => {
  current = { ...job('SUCCEEDED', 3), definition: 'parties' };
  render(
    <PartyImport company={COMPANY} canManage={false} supplier initialHistory />,
  );
  await screen.findByRole('table', {
    name: 'Party and supplier import history',
  });
  expect(screen.getByRole('link', { name: /Open import/ })).toHaveAttribute(
    'href',
    expect.stringContaining('job=' + JOB),
  );
  expect(
    screen.queryByRole('button', { name: 'Download template' }),
  ).not.toBeInTheDocument();
});
it('does not request detailed party records or offer downloads without native party management', async () => {
  current = { ...job('SUCCEEDED', 3), definition: 'parties' };
  render(
    <PartyImport
      company={COMPANY}
      canManage={false}
      supplier
      initialJob={JOB}
    />,
  );
  await screen.findByText(
    'Party import completed successfully. Review each imported identity and its roles. Opening balances in the file are held for Account and party openings; nothing is posted.',
  );
  expect(
    screen.queryByRole('button', { name: 'Download results' }),
  ).not.toBeInTheDocument();
  expect(
    api.mock.calls.some(
      ([, request]) =>
        request.path.includes('/records') ||
        request.path.includes('/history/attempts'),
    ),
  ).toBe(false);
});

it('keeps supplier policy roles restricted to supplier templates', async () => {
  render(<PartyImport company={COMPANY} canManage supplier />);
  await userEvent.selectOptions(
    await screen.findByRole('combobox', { name: 'Import content' }),
    'party_credit_policy',
  );
  const role = screen.getByRole('combobox', { name: 'Party role' });
  expect(
    within(role).getByRole('option', { name: 'Supplier' }),
  ).toBeInTheDocument();
  expect(
    within(role).queryByRole('option', { name: 'Customer' }),
  ).not.toBeInTheDocument();
});

it('recovers an uncertain supplier upload using the same Accounting request', async () => {
  let lost = true;
  const normal = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    const request = args[1];
    if (
      request.method === 'POST' &&
      request.path.endsWith('/import-jobs') &&
      lost
    )
      throw { status: 503, message: 'Result unavailable' };
    return normal(...args);
  });
  render(<PartyImport company={COMPANY} canManage supplier />);
  await userEvent.click(
    await screen.findByRole('button', { name: 'Download template' }),
  );
  await waitFor(() => expect(downloadPartyImport).toHaveBeenCalled());
  await userEvent.upload(
    document.querySelector<HTMLInputElement>('input[type=file]')!,
    new File(['supplier'], 'supplier.csv', { type: 'text/csv' }),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Upload and prepare validation' }),
  );
  await screen.findByRole('button', { name: 'Retry same action' });
  expect(
    screen.getByRole('combobox', { name: 'Import content' }),
  ).toBeDisabled();
  lost = false;
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same action' }),
  );
  await screen.findByRole('button', { name: 'Validate files' });
  const writes = api.mock.calls.filter(
    ([, request]) =>
      request.method === 'POST' && request.path.endsWith('/import-jobs'),
  );
  expect(writes).toHaveLength(2);
  expect(writes[0]![1].key).toBe(writes[1]![1].key);
  expect(writes[0]![1].body).toEqual(writes[1]![1].body);
  expect(
    writes.every(
      ([endpoint, request]) =>
        endpoint === '/api/party-import' && request.service === 'accounting',
    ),
  ).toBe(true);
});
it.each([false, true])(
  'enables the permitted directory import link after New (%s)',
  async (supplier) => {
    api.mockImplementation(
      async (_, request) =>
        accountingResponse(request.path, request.method, request.body) as never,
    );
    render(
      <AccountingConfigurationDirectory
        company={COMPANY}
        config={accountingResource('parties')!}
        canManage
        canImport
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
    expect(link).toHaveAttribute(
      'href',
      expect.stringContaining(
        '/accounting/' + (supplier ? 'suppliers' : 'parties') + '/import',
      ),
    );
  },
);
it('explains the optional opening columns for ready customers and suppliers only', async () => {
  const view = render(<PartyImport company={COMPANY} canManage supplier />);
  expect(await screen.findByRole('heading', { name: 'Optional opening balances' })).toBeVisible();
  expect(screen.getByText(/DR or TO_RECEIVE is a debit balance: they owe you/)).toBeVisible();
  expect(screen.getByText(/CR or TO_PAY is a credit balance: you owe them/)).toBeVisible();
  expect(screen.getByText(/Nothing is posted/)).toBeVisible();
  expect(screen.getByRole('link', { name: 'Account and party openings' })).toHaveAttribute('href', '/accounting/opening');
  expect(screen.queryByText(/rows with opening columns will be rejected/)).not.toBeInTheDocument();
  view.unmount();
  render(<PartyImport company={COMPANY} canManage />);
  const content = await screen.findByRole('combobox', { name: 'Import content' });
  // The party page opens on ready customers, which carry the optional opening columns.
  expect(content).toHaveValue('customer');
  expect(await screen.findByRole('heading', { name: 'Optional opening balances' })).toBeVisible();
  // Rows that only update, activate or deactivate an existing identity carry none.
  await userEvent.selectOptions(content, 'party');
  expect(screen.queryByRole('heading', { name: 'Optional opening balances' })).not.toBeInTheDocument();
  await userEvent.selectOptions(content, 'customer');
  expect(await screen.findByRole('heading', { name: 'Optional opening balances' })).toBeVisible();
});
it('warns before upload that rows with opening columns would be rejected once the opening is closed', async () => {
  blockers = ['OPENING_ALREADY_FINALIZED'];
  render(<PartyImport company={COMPANY} canManage supplier />);
  expect(await screen.findByText(/rows with opening columns will be rejected/)).toBeVisible();
  expect(screen.getByText(/The financial opening is already finalized/)).toBeVisible();
});
it('keeps the guide quiet when opening readiness cannot be read', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    if (args[1].path.endsWith('/opening-batches/readiness')) throw { status: 403, message: 'Not permitted.' };
    return original(...args);
  });
  render(<PartyImport company={COMPANY} canManage supplier />);
  expect(await screen.findByRole('heading', { name: 'Optional opening balances' })).toBeVisible();
  expect(screen.queryByText(/rows with opening columns will be rejected/)).not.toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
