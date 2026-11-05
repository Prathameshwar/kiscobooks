/**
 * W2 to W6 through the connected page, on a mocked service client (CLAUDE.md §7: never a live
 * service). The fake below answers the calls the page makes, and records the writes.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisplayConfigProvider, PageNavigation, PermissionProvider } from '@janso/ui';

vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));
vi.mock('../app/lib/sales-entry-api', async (original) => ({
  ...(await original<typeof import('../app/lib/sales-entry-api')>()),
  salesCall: vi.fn(),
}));

vi.setConfig({ testTimeout: 20_000 });

import { salesCall } from '../app/lib/sales-entry-api';
import { SalesEntryConnected } from '../app/components/SalesEntryConnected';

const COMPANY = '01990000-0000-7000-8000-000000000001';
const TYPE = '01990000-0000-7000-8000-0000000000t1'.replace('t', '0');
const PARTY = '01990000-0000-7000-8000-0000000000c1';
const ITEM = '01990000-0000-7000-8000-0000000000e9';
const BINDING = '01990000-0000-7000-8000-0000000000b1';
const VOUCHER = '01990000-0000-7000-8000-0000000000v1'.replace('v', '0');

type Call = { service: string; method: string; path: string; body?: unknown; key?: string };
const calls: Call[] = [];
let types: unknown[] = [];
let failCreate: { status: number; message: string } | null = null;
let version = 1;
const RECEIVABLE = { id: 'receivable', row_version: 3, party_role: 'CUSTOMER' };
let partyAccounts: unknown[] = [RECEIVABLE];

const page = (items: unknown[]) => ({ items, page: { next_cursor: null, has_more: false, limit: 50 } });

function respond(call: Call): unknown {
  const { service, method, path } = call;
  const route = path.split('?')[0]!.replace(`/v1/companies/${COMPANY}`, '');
  if (service === 'identity' && route === '') return { base_currency: 'INR', state_code: 'IN-KA' };
  if (service === 'identity' && route === '/tax-registrations')
    return page([{ id: 'gstin-1', is_primary: true, jurisdiction_code: 'IN-KA', tax_system: 'GST', valid_to: null }]);
  if (route === '/voucher-types') return page(types);
  if (route === '/voucher-types/' + TYPE) return types.find(row => (row as { id: string }).id === TYPE);
  if (route.endsWith('/effective-configuration'))
    return {
      type_revision_id: 'rev-1',
      class_id: null,
      kind: 'SALES',
      profile: 'STANDARD',
      digest: 'f'.repeat(64),
      policy: {
        invoice: {
          manual_discounts_allowed: true,
          sales_tender_modes: ['CASH', 'UPI'],
          sales_tax_profiles: ['INDIA_DOMESTIC_SERVICE'],
        },
      },
    };
  if (route === '/accounts') {
    const kind = new URLSearchParams(path.split('?')[1]).get('kind');
    if (kind === 'GENERAL')
      return page([
        { id: 'svc-rev', row_version: 1, system_key: 'SERVICE_REVENUE', name: 'Service revenue' },
        { id: 'gain', row_version: 1, system_key: 'ROUNDING_GAIN' },
        { id: 'loss', row_version: 1, system_key: 'ROUNDING_LOSS' },
      ]);
    if (kind === 'CASH') return page([{ id: 'cash', row_version: 1, system_key: 'CASH_MAIN' }]);
    if (kind === 'BANK') return page([{ id: 'bank', row_version: 1 }]);
    // The customer's receivable is its one CUSTOMER-role party account (a party that is also a supplier holds another).
    if (kind === 'PARTY') return page(partyAccounts);
  }
  if (route === '/price-levels') return page([{ id: 'level-1', name: 'Wholesale' }]);
  if (route === '/parties') return page([{ id: PARTY, name: 'Nandini Trading Company', code: 'NTC' }]);
  if (route === `/parties/${PARTY}`) return { id: PARTY, row_version: 4 };
  if (route === '/party-addresses') return page([{ id: 'addr-1', label: 'Head office', state_code: 'IN-KA' }]);
  if (route === '/party-address-uses') return page([{ address_id: 'addr-1', purpose: 'REGISTERED', is_default: true }]);
  if (route === '/credit/check') return { exposure: '0', limit: null, overdue: '0' };
  if (route === '/items') return page([{ id: ITEM, name: 'Installation visit', sku: 'SVC-1', base_unit_id: 'unit-1', row_version: 2 }]);
  if (route === `/items/${ITEM}`) return { id: ITEM, name: 'Installation visit', base_unit_id: 'unit-1', row_version: 2 };
  if (route === `/items/${ITEM}/unit-bindings`) return page([{ id: BINDING, unit_id: 'unit-1', usage_role: 'BASE' }]);
  if (route === `/item-unit-bindings/${BINDING}/revisions`) return page([{ id: 'unit-rev-1', valid_from: '2020-01-01', valid_to: null }]);
  if (route === '/prices/resolve') return { status: 'RESOLVED', amount: '1500', price_basis_quantity: '1' };
  if (route === '/tax-configurations/resolve')
    return { status: 'COMPLETE', classification_code: classification, rates: [{ components: [{ component: 'IGST', percentage: '18' }] }] };
  if (route === '/vouchers' && method === 'POST') {
    if (failCreate) throw failCreate;
    return { id: VOUCHER, row_version: version, status: 'DRAFT', revision_number: 1 };
  }
  if (route === `/vouchers/${VOUCHER}` && method === 'PUT') {
    version += 1;
    return { id: VOUCHER, row_version: version, status: 'DRAFT', revision_number: version };
  }
  if (route === `/vouchers/${VOUCHER}/invoice-preview`)
    return { calculation_hash: 'a'.repeat(64), currency: 'INR', commercial_total: '3000', tax_total: '540', rounding: '0', payable: '3540' };
  if (route === `/vouchers/${VOUCHER}/invoice-acceptance`) {
    version += 1;
    return { id: VOUCHER, row_version: version, status: 'DRAFT', revision_number: version };
  }
  if (route === `/vouchers/${VOUCHER}/submit`) return { id: VOUCHER, row_version: version + 1, status: 'SUBMITTED', revision_number: version };
  throw { status: 404, message: `unexpected ${service} ${method} ${route}` };
}

beforeEach(() => {
  calls.length = 0;
  types = [{ id: TYPE, name: 'Sales', kind: 'SALES' }];
  failCreate = null;
  version = 1;
  partyAccounts = [RECEIVABLE];
  vi.mocked(salesCall).mockReset();
  vi.mocked(salesCall).mockImplementation(async (service, request) => {
    const call = { service, method: request.method ?? 'GET', path: request.path, body: request.body, ...(request.key ? { key: request.key } : {}) };
    calls.push(call);
    return respond(call) as never;
  });
});

function mount(initialTypeId?: string, navigation?: React.ReactNode) {
  return render(
    <DisplayConfigProvider config={{ amountPrecision: 2, digitGrouping: 'indian', timezone: 'Asia/Kolkata' }}>
      <PermissionProvider permissions={['vouchers.create', 'vouchers.edit', 'vouchers.read', 'vouchers.submit']}>
        <SalesEntryConnected company={COMPANY} canCreate initialTypeId={initialTypeId} navigation={navigation} />
      </PermissionProvider>
    </DisplayConfigProvider>,
  );
}

type User = ReturnType<typeof userEvent.setup>;
let classification = '998719';
async function fill(user: User, code = '998719') {
  classification = code;
  await user.type(await screen.findByRole('combobox', { name: /Customer/ }), 'nan');
  await user.click(await screen.findByRole('option', { name: /Nandini/ }));
  await user.type(screen.getByRole('combobox', { name: /^Item, line 1$/ }), 'ins');
  await user.click(await screen.findByRole('option', { name: /Installation visit/ }));
  // The price arrives from the service, after the choice.
  await waitFor(() => expect(screen.getByRole('textbox', { name: /^Rate, line 1/ })).toHaveValue('1,500.0000'));
  await user.type(screen.getByRole('textbox', { name: /^Actual, line 1/ }), '2');
}
const writes = () => calls.filter((call) => call.method !== 'GET' && !/resolve|credit/.test(call.path));

describe('W2 loading the bill type', () => {
  it('opens a specific type from voucher navigation without choosing another type', async () => {
    types = [{ id: TYPE, company_id: COMPANY, name: 'Specific sales', kind: 'SALES', profile: 'STANDARD', status: 'ACTIVE' }];
    const back = '/operate/income/sales/sales?type_id=' + TYPE;
    mount(TYPE, <PageNavigation back={{ href: back, label: 'voucher list' }} />);
    await screen.findByRole('heading', { name: 'New sales bill' });
    expect(calls.some(call => call.path.endsWith('/voucher-types/' + TYPE))).toBe(true);
    expect(calls.some(call => call.path.split('?')[0].endsWith('/voucher-types'))).toBe(false);
    expect(screen.getByRole('link', { name: 'Back to voucher list' })).toHaveAttribute('href', back);
    expect(screen.queryByRole('link', { name: 'Back to voucher drafts' })).not.toBeInTheDocument();
  });
  it('renders the bill from the service’s policy', async () => {
    mount();
    expect(await screen.findByRole('heading', { name: 'New sales bill' })).toBeInTheDocument();
    // The policy took two tender modes and the service's price levels.
    expect(screen.getByRole('option', { name: 'Wholesale' })).toBeInTheDocument();
  });

  it('says so when no Sales type is set up', async () => {
    types = [];
    mount();
    expect(await screen.findByText('No Sales bill type is set up')).toBeInTheDocument();
  });

  it('says what failed and offers to try again', async () => {
    const user = userEvent.setup({ delay: null });
    vi.mocked(salesCall).mockRejectedValueOnce({ status: 403, message: 'permission denied' });
    mount();
    expect(await screen.findByText("You don't have access to this")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'New sales bill' })).toBeInTheDocument();
  });
});

describe('a goods bill', () => {
  it('is kept on the page and says why the service cannot take it yet', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await fill(user, '1006');
    await user.click(screen.getByRole('button', { name: /Save draft/ }));
    expect(
      await screen.findByText(/goods cannot be billed through the service yet/),
    ).toBeInTheDocument();
    expect(calls.some((call) => call.method === 'POST' && call.path.endsWith('/vouchers'))).toBe(false);
  });
});

describe('the customer’s receivable is its one customer-role account', () => {
  const NEEDS_ONE =
    'This customer needs exactly one receivable account to be billed to, and has none or several. An administrator can repair it with the party ledger repair.';
  const customerLookup = () =>
    calls.find((call) => call.path.includes('/accounts?') && call.path.includes('kind=PARTY'))!;

  it('asks Accounting for the customer-role account of the chosen party only', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await fill(user);
    const params = new URLSearchParams(customerLookup().path.split('?')[1]);
    expect(Object.fromEntries(params)).toEqual({
      party_id: PARTY,
      kind: 'PARTY',
      role: 'CUSTOMER',
      status: 'ACTIVE',
      limit: '50',
    });
  });

  it.each([
    ['has no active party account', []],
    ['has two customer accounts', [RECEIVABLE, { ...RECEIVABLE, id: 'second-receivable' }]],
    ['has only a supplier-role payable', [{ id: 'payable', row_version: 2, party_role: 'SUPPLIER' }]],
    ['has an account that carries no role', [{ id: 'unroled', row_version: 1 }]],
  ])('keeps the bill unsaved and says the customer needs exactly one receivable when it %s', async (_why, rows) => {
    const user = userEvent.setup({ delay: null });
    partyAccounts = rows;
    mount();
    await fill(user);
    await user.click(screen.getByRole('button', { name: /Save draft/ }));
    expect(await screen.findByText(NEEDS_ONE)).toBeInTheDocument();
    expect(screen.queryByText(/has no receivable account to bill to/)).not.toBeInTheDocument();
    expect(calls.some((call) => call.method === 'POST' && call.path.endsWith('/vouchers'))).toBe(false);
    // Without a receivable there is no account to ask Accounting's credit check about.
    expect(calls.some((call) => call.path.endsWith('/credit/check'))).toBe(false);
  });

  it('bills the customer-role account, never the payable, of a party that is also a supplier', async () => {
    const user = userEvent.setup({ delay: null });
    partyAccounts = [{ id: 'payable', row_version: 2, party_role: 'SUPPLIER' }, RECEIVABLE];
    mount();
    await fill(user);
    await user.click(screen.getByRole('button', { name: /Save draft/ }));
    expect(await screen.findByText('Saved as a draft, revision 1.')).toBeInTheDocument();
    const create = writes().find((call) => call.method === 'POST' && call.path.endsWith('/vouchers'))!;
    expect(create.body).toMatchObject({ invoice: { party_account_id: 'receivable', party_account_version: 3 } });
    expect(JSON.stringify(create.body)).not.toContain('payable');
  });
});

describe('W3 to W6 a services bill, end to end', () => {
  it('saves, calculates, accepts and submits', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await fill(user);

    await user.click(screen.getByRole('button', { name: /Save draft/ }));
    expect(await screen.findByText('Saved as a draft, revision 1.')).toBeInTheDocument();
    const create = writes().find((call) => call.method === 'POST' && call.path.endsWith('/vouchers'))!;
    expect(create.key).toMatch(/[0-9a-f-]{36}/);
    expect(create.body).toMatchObject({
      type_revision_id: 'rev-1',
      parties: [{ role: 'CUSTOMER', party_id: PARTY, source_version: 4 }],
      invoice: {
        party_account_id: 'receivable',
        tax: { profile: 'INDIA_DOMESTIC_SERVICE', company_registration_id: 'gstin-1', place_of_supply: 'IN-KA' },
        supplies: [expect.objectContaining({ supply_kind: 'SERVICE', account_id: 'svc-rev', amount: '3000', unit_price: '1500' })],
      },
    });
    // Stored: the leave guard lets go.
    expect(screen.getByText(/1 line · saved/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Calculate' }));
    const card = await screen.findByRole('group', { name: 'Service calculation' });
    expect(within(card).getByText('₹3,540.00')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Accept calculation' }));
    expect(await screen.findByText(/with its calculation accepted/)).toBeInTheDocument();
    const acceptance = calls.find((call) => call.path.endsWith('/invoice-acceptance'))!;
    expect(acceptance.body).toEqual({ expected_version: 1, calculation_hash: 'a'.repeat(64) });
    expect(acceptance.key).toBeTruthy();

    await user.click(screen.getByRole('button', { name: 'Submit' }));
    expect(await screen.findByText(/Submitted for approval/)).toBeInTheDocument();
  });

  it('saves an edit as a revision, with the version it edits', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await fill(user);
    await user.click(screen.getByRole('button', { name: /Save draft/ }));
    await screen.findByText('Saved as a draft, revision 1.');

    await user.type(screen.getByRole('textbox', { name: /^Description, line 1/ }), 'On site');
    await user.click(screen.getByRole('button', { name: /Save draft/ }));
    expect(await screen.findByText('Saved as a draft, revision 2.')).toBeInTheDocument();
    const edit = calls.find((call) => call.method === 'PUT')!;
    expect(edit.body).toMatchObject({ expected_version: 1, reason: 'Edited on the sales bill', content: { lines: [expect.objectContaining({ description: 'On site' })] } });
  });

  it('keeps the bill and says why when the service refuses the save', async () => {
    const user = userEvent.setup({ delay: null });
    failCreate = { status: 409, message: 'voucher version changed; reload before retrying' };
    mount();
    await fill(user);
    await user.click(screen.getByRole('button', { name: /Save draft/ }));
    expect(await screen.findByText('This draft was changed elsewhere since it was opened. Reload it before saving again.')).toBeInTheDocument();
    expect(screen.getByText(/not saved yet/)).toBeInTheDocument();
  });

  it('reuses the idempotency key when a failed save is retried', async () => {
    const user = userEvent.setup({ delay: null });
    failCreate = { status: 503, message: 'busy' };
    mount();
    await fill(user);
    await user.click(screen.getByRole('button', { name: /Save draft/ }));
    await screen.findByText(/busy/);
    failCreate = null;
    await user.click(screen.getByRole('button', { name: /Save draft/ }));
    await screen.findByText('Saved as a draft, revision 1.');
    const creates = calls.filter((call) => call.method === 'POST' && call.path.endsWith('/vouchers'));
    expect(creates).toHaveLength(2);
    // The same request, the same key: a retried create is one draft, not two.
    expect(creates[0]!.key).toBe(creates[1]!.key);
  });
});
