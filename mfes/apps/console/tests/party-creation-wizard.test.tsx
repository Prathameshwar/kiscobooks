import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountingConfigurationEditor } from '../app/components/AccountingConfigurationEditor';
import { accountingResource } from '../app/lib/accounting-configuration-resources';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';
import { allowedAccountingConfigurationRequest } from '../app/lib/accounting-configuration-policy';
import {capture} from './master-opening-fixture';
import {
  COMPANY,
  ID,
  PARTY,
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
const api = vi.mocked(serviceCall);
// A party is created with its role and that role's ledger account, so 'accounts' is part of the
// ordinary grant: the wizard refuses to create without permission to create accounts.
const resources = [
  'parties',
  'party-roles',
  'accounts',
  'party-addresses',
  'party-address-uses',
  'party-contacts',
  'party-contact-uses',
  'party-tax-registrations',
];
const writes = () =>
  api.mock.calls.filter(([, request]) => request.method === 'POST');
const roleSelect = () => screen.getByRole('combobox', { name: 'Party role' });

it.each([
  ['POST', '', true],
  ['GET', '', false],
  ['PATCH', '', false],
  ['POST', '?role=SUPPLIER', false],
  ['POST', '/extra', false],
])('bounds the aggregate proxy route: %s %s', (method, suffix, allowed) => {
  expect(
    allowedAccountingConfigurationRequest(
      method,
      `/v1/companies/${COMPANY}/parties/create-with-details${suffix}`,
    ),
  ).toBe(allowed);
});
function show(
  supplier = false,
  available = resources,
  companyCountry?: string,
  manageable = available,
) {
  return render(
    <AccountingConfigurationEditor
      company={COMPANY}
      companyCountry={companyCountry}
      config={accountingResource('parties')!}
      supplier={supplier}
      availableResources={available}
      manageableResources={manageable}
    />,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  api.mockImplementation(async (_, request) => {
    const value = response(request.path, request.method, request.body);
    return (
      request.path.endsWith('/parties/create-with-details')
        ? { ...value, status: 'ACTIVE' }
        : value
    ) as never;
  });
});
/** Fills the identity and, on "New party", chooses the (required) role; "New supplier" has none to choose. */
async function fillParty(role: string | null = 'CUSTOMER') {
  await userEvent.type(
    await screen.findByRole('textbox', { name: 'Code' }),
    'TEST',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Name' }),
    'Test party',
  );
  await userEvent.clear(screen.getByRole('textbox', { name: 'Legal name' }));
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Legal name' }),
    'Test party LLP',
  );
  await userEvent.click(screen.getByRole('combobox', { name: 'Country code' }));
  await userEvent.click(await screen.findByRole('option', { name: /India/ }));
  if (role) await userEvent.selectOptions(roleSelect(), role);
}
async function step(label: string) {
  await userEvent.click(
    within(
      screen.getByRole('navigation', { name: 'Setup progress' }),
    ).getByRole('button', { name: new RegExp(label) }),
  );
}

function openingMetadata(){api.mockImplementation(async(_,request)=>request.path.endsWith('/master-balances/capture')?{...capture,company_id:COMPANY} as never:response(request.path,request.method,request.body) as never);}
it('retries the original party opening after the capture window changes',async()=>{
  let reads=0,posts=0,resolveCapture!:(value:typeof capture)=>void;
  api.mockImplementation(async(_,request)=>{
    if(request.path.endsWith('/master-balances/capture')){if(++reads===1)return {...capture,company_id:COMPANY} as never;return await new Promise<typeof capture>(resolve=>{resolveCapture=resolve;}) as never;}
    if(request.method==='POST'&&++posts===1)throw {status:503,message:'Outcome unknown'};
    return response(request.path,request.method,request.body) as never;
  });
  show();await fillParty();await step('Opening balance');await waitFor(()=>expect(screen.getByLabelText('Opening balance')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Opening balance'),{target:{value:'100.0001'}});await userEvent.selectOptions(screen.getByRole('combobox',{name:'Dr / Cr'}),'DEBIT');
  await step('Party details');await step('Opening balance');await waitFor(()=>expect(reads).toBe(2));
  await userEvent.click(screen.getByRole('button',{name:'Create party'}));await screen.findByRole('button',{name:'Retry same creation'});
  await act(async()=>resolveCapture({...capture,company_id:COMPANY,can_capture:false}));
  await userEvent.click(screen.getByRole('button',{name:'Retry same creation'}));await waitFor(()=>expect(posts).toBe(2));expect(writes()[1]![1]).toEqual(writes()[0]![1]);
});
it('adds opening as the optional last step and saves it atomically with the party',async()=>{
  openingMetadata();show();await fillParty();await step('Opening balance');
  await screen.findByLabelText('Opening date');await waitFor(()=>expect(screen.getByLabelText('Opening balance')).toBeEnabled());
  expect(screen.getByLabelText('Opening date')).toHaveValue('2026-04-01');
  await userEvent.type(screen.getByLabelText('Opening balance'),'125.0001');await userEvent.selectOptions(screen.getByRole('combobox',{name:'Dr / Cr'}),'DEBIT');
  await step('Party details');await userEvent.click(screen.getByRole('button',{name:'Create party'}));
  await waitFor(()=>expect(writes()).toHaveLength(1));expect(writes()[0]![1].body).toMatchObject({opening:{amount:'125.0001',side:'DEBIT',opening_date:'2026-04-01',documents:[]}});
});
it('requires Dr/Cr for a nonzero opening and sends no partial party creation',async()=>{
  openingMetadata();show();await fillParty();await step('Opening balance');await waitFor(()=>expect(screen.getByLabelText('Opening balance')).toBeEnabled());
  await userEvent.type(screen.getByLabelText('Opening balance'),'125');await step('Party details');await userEvent.click(screen.getByRole('button',{name:'Create party'}));
  expect(await screen.findByText('Choose Dr or Cr explicitly.')).toBeVisible();expect(writes()).toHaveLength(0);expect(screen.getByLabelText('Opening balance')).toHaveValue('125');
});
it('saves multiple purchase bills with original and pending values from the final step',async()=>{
  openingMetadata();show(true);await fillParty(null);await step('Opening balance');await waitFor(()=>expect(screen.getByLabelText('Opening balance')).toBeEnabled());
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Dr / Cr'}),'CREDIT');await userEvent.click(screen.getByRole('radio',{name:'Bill-wise'}));
  for(const [index,pending] of [[1,'60.0001'],[2,'39.9999']] as const){
    if(index===2)await userEvent.click(screen.getByRole('button',{name:'Add another bill'}));
    for(const [label,value] of [['Bill number','B-'+index],['Bill amount','200'],['Pending amount',pending],['Bill date','2026-03-01'],['Due date','2026-04-10']])fireEvent.change(screen.getByLabelText(label!),{target:{value}});
    await userEvent.click(screen.getByRole('button',{name:'Add bill'}));
  }
  await userEvent.click(screen.getByRole('button',{name:'Create supplier'}));await waitFor(()=>expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({opening:{amount:'100.0000',side:'CREDIT',documents:[{reference:'B-1',original_amount:'200',amount:'60.0001',document_kind:'BILL'},{reference:'B-2',original_amount:'200',amount:'39.9999',document_kind:'BILL'}]}});
});

it('follows the name until legal name is edited, then keeps the override', async () => {
  show();
  const name = await screen.findByRole('textbox', { name: 'Name' });
  const legal = screen.getByRole('textbox', { name: 'Legal name' });
  await userEvent.type(name, 'Trading');
  expect(legal).toHaveValue('Trading');
  await userEvent.clear(name);
  await userEvent.type(name, 'New trading');
  expect(legal).toHaveValue('New trading');
  await userEvent.clear(legal);
  await userEvent.type(legal, 'Trading LLP');
  await userEvent.type(name, ' branch');
  await step('Address and contact');
  await step('Party details');
  expect(legal).toHaveValue('Trading LLP');
});

it.each([undefined, 'US'])('uses company country %s or India by default', async (country) => {
  show(false, resources, country);
  await userEvent.type(await screen.findByRole('textbox', { name: 'Code' }), 'DEFAULTS');
  await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'Default party');
  await userEvent.selectOptions(roleSelect(), 'CUSTOMER');
  await userEvent.click(screen.getByRole('button', { name: 'Create party' }));
  await waitFor(() => expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({
    legal_name: 'Default party', country_code: country ?? 'IN', role: 'CUSTOMER',
  });
});

it('copies address state and party country into tax and submits without a start date', async () => {
  show();
  await fillParty();
  await step('Address and contact');
  await userEvent.click(screen.getByRole('checkbox', { name: 'Add default address' }));
  await userEvent.type(screen.getByRole('textbox', { name: 'Line1' }), 'Road');
  await userEvent.type(screen.getByRole('textbox', { name: 'City' }), 'Mumbai');
  await userEvent.click(screen.getByRole('combobox', { name: 'State code' }));
  await userEvent.click(await screen.findByRole('option', { name: /General reference/ }));
  await step('Tax and other details');
  await userEvent.click(screen.getByRole('checkbox', { name: 'Add tax registration' }));
  expect(screen.getByLabelText('Valid from')).not.toBeRequired();
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Scheme' }), 'VAT');
  await userEvent.type(screen.getByRole('textbox', { name: 'Registration number' }), 'VAT-1');
  await userEvent.click(screen.getByRole('button', { name: 'Create party' }));
  await waitFor(() => expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({
    address: { label: 'Billing address', state_code: 'MH', country_code: 'IN' },
    tax_registration: { country_code: 'IN', state_code: 'MH', valid_from: null },
  });
});

it('keeps edited tax state and address label when earlier defaults change', async () => {
  api.mockImplementation(async (_, request) => {
    if (request.path.includes('/configuration/options/states')) {
      const options = [
        { value: 'IN-MH', label: 'Maharashtra' },
        { value: 'IN-KA', label: 'Karnataka' },
      ];
      const value = new URL(request.path, 'https://console.invalid').searchParams.get('value');
      return { items: value ? options.filter((item) => item.value === value) : options,
        page: { limit: 25, has_more: false, next_cursor: null } } as never;
    }
    const value = response(request.path, request.method, request.body);
    return (request.path.endsWith('/parties/create-with-details')
      ? { ...value, status: 'ACTIVE' } : value) as never;
  });
  show();
  await fillParty();
  await step('Address and contact');
  await userEvent.click(screen.getByRole('checkbox', { name: 'Add default address' }));
  await userEvent.clear(screen.getByRole('textbox', { name: 'Label' }));
  await userEvent.type(screen.getByRole('textbox', { name: 'Label' }), 'Head office');
  await userEvent.type(screen.getByRole('textbox', { name: 'Line1' }), 'Road');
  await userEvent.type(screen.getByRole('textbox', { name: 'City' }), 'Mumbai');
  await userEvent.click(screen.getByRole('combobox', { name: 'State code' }));
  await userEvent.click(await screen.findByRole('option', { name: 'Maharashtra' }));
  await step('Tax and other details');
  await userEvent.click(screen.getByRole('checkbox', { name: 'Add tax registration' }));
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'State code' })).toHaveValue('Maharashtra'));
  await userEvent.click(screen.getByRole('combobox', { name: 'State code' }));
  await userEvent.click(await screen.findByRole('option', { name: 'Karnataka' }));
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Scheme' }), 'VAT');
  await userEvent.type(screen.getByRole('textbox', { name: 'Registration number' }), 'VAT-2');
  await step('Address and contact');
  await userEvent.click(screen.getByRole('combobox', { name: 'State code' }));
  await userEvent.click(await screen.findByRole('option', { name: 'Karnataka' }));
  await userEvent.click(screen.getByRole('combobox', { name: 'State code' }));
  await userEvent.click(await screen.findByRole('option', { name: 'Maharashtra' }));
  await userEvent.click(screen.getByRole('checkbox', { name: 'Add default address' }));
  await userEvent.click(screen.getByRole('checkbox', { name: 'Add default address' }));
  expect(screen.getByRole('textbox', { name: 'Label' })).toHaveValue('Head office');
  await userEvent.click(screen.getByRole('button', { name: 'Create party' }));
  await waitFor(() => expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({
    address: { label: 'Head office', state_code: 'IN-MH' },
    tax_registration: { state_code: 'IN-KA' },
  });
});

it.each(['Party details', 'Address and contact', 'Tax and other details'])(
  'creates directly from %s in one request',
  async (label) => {
    show();
    await fillParty();
    await step(label);
    expect(writes()).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: 'Create party' }));
    await waitFor(() =>
      expect(goTo).toHaveBeenCalledWith(
        expect.stringContaining('/accounting/parties/' + ID),
      ),
    );
    expect(writes()).toHaveLength(1);
    expect(writes()[0]![1]).toMatchObject({
      path: `/v1/companies/${COMPANY}/parties/create-with-details`,
      body: { code: 'TEST', country_code: 'IN', role: 'CUSTOMER' },
    });
  },
);
it('validates all required identity fields and returns to their step', async () => {
  show();
  await screen.findByRole('textbox', { name: 'Code' });
  await step('Tax and other details');
  await userEvent.click(screen.getByRole('button', { name: 'Create party' }));
  expect(await screen.findByRole('textbox', { name: 'Code' })).toHaveAttribute(
    'aria-invalid',
    'true',
  );
  expect(writes()).toHaveLength(0);
});
it('saves entered defaults and later-step notes in the same command', async () => {
  show(true);
  await fillParty(null);
  await step('Address and contact');
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Add default address' }),
  );
  const address = within(
    screen.getByRole('region', { name: 'Address and contact' }),
  );
  expect(address.getByRole('textbox', { name: 'Mailing name' })).toHaveValue(
    'Test party LLP',
  );
  expect(address.getByRole('textbox', { name: 'Label' })).toHaveValue('Billing address');
  await userEvent.clear(address.getByRole('textbox', { name: 'Label' }));
  await userEvent.type(
    address.getByRole('textbox', { name: 'Label' }),
    'Primary',
  );
  await userEvent.type(
    address.getByRole('textbox', { name: 'Line1' }),
    'Road 1',
  );
  await userEvent.type(
    address.getByRole('textbox', { name: 'City' }),
    'Mumbai',
  );
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Add default contact' }),
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Name' }),
    'Accounts',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Email' }),
    'accounts@example.test',
  );
  await step('Tax and other details');
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Notes' }),
    'Call before delivery',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create supplier' }),
  );
  await waitFor(() => expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({
    role: 'SUPPLIER',
    notes: 'Call before delivery',
    address: {
      mailing_name: 'Test party LLP',
      country_code: 'IN',
      city: 'Mumbai',
    },
    contact: { name: 'Accounts', email: 'accounts@example.test' },
  });
  expect(JSON.stringify(writes()[0]![1].body)).not.toContain('party_id');
});
it('retains optional drafts when visiting steps and validates them from another step', async () => {
  show();
  await fillParty();
  await step('Address and contact');
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Add default contact' }),
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Email' }),
    'accounts@example.test',
  );
  await step('Party details');
  await userEvent.click(screen.getByRole('button', { name: 'Create party' }));
  expect(await screen.findByRole('textbox', { name: 'Email' })).toHaveValue(
    'accounts@example.test',
  );
  expect(screen.getByRole('textbox', { name: 'Name' })).toHaveAttribute(
    'aria-invalid',
    'true',
  );
  expect(writes()).toHaveLength(0);
});
it('omits disabled optional sections without erasing their draft', async () => {
  show();
  await fillParty();
  await step('Address and contact');
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Add default contact' }),
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Name' }),
    'Kept draft',
  );
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Add default contact' }),
  );
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Add default contact' }),
  );
  expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue(
    'Kept draft',
  );
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Add default contact' }),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Create party' }));
  await waitFor(() => expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).not.toHaveProperty('contact');
});
it('does not fetch optional metadata without resource access', async () => {
  show(false, ['parties']);
  await screen.findByRole('textbox', { name: 'Code' });
  // The party role is mandatory, so its metadata is always read; the optional sections still are not.
  expect(api.mock.calls.map(([, request]) => request.path).filter((path) => path.includes('/field-set'))).toEqual([
    expect.stringContaining('/configuration/parties/'),
    expect.stringContaining('/configuration/party-roles/'),
  ]);
  await step('Address and contact');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
});
it('fails closed when required metadata is denied', async () => {
  api.mockRejectedValue({ status: 403, message: 'Denied' });
  show();
  expect(await screen.findByText('Denied')).toBeVisible();
  expect(
    screen.queryByRole('button', { name: 'Create party' }),
  ).not.toBeInTheDocument();
});
it('requires supplier role creation access before submitting', async () => {
  api.mockImplementation(async (_, request) => {
    if (request.path.includes('/configuration/party-roles/'))
      return { ...form('party-roles'), can_create: false } as never;
    return response(request.path, request.method, request.body) as never;
  });
  show(true);
  expect(
    await screen.findByRole('button', { name: 'Create supplier' }),
  ).toBeDisabled();
});
it('freezes uncertain requests and retries with the same key and body', async () => {
  api.mockImplementation(async (_, request) => {
    if (request.method === 'POST')
      throw { status: 500, message: 'Result unknown' };
    return response(request.path, request.method, request.body) as never;
  });
  show();
  await fillParty();
  await userEvent.click(screen.getByRole('button', { name: 'Create party' }));
  await userEvent.click(
    await screen.findByRole('button', { name: 'Retry same creation' }),
  );
  expect(writes()).toHaveLength(2);
  expect(writes()[1]![1]).toEqual(writes()[0]![1]);
  // The same key and the same body, role included: a replay of an uncertain create is one party.
  expect(writes()[0]![1].key).toBeTruthy();
  expect(writes()[1]![1].key).toBe(writes()[0]![1].key);
  expect(writes()[1]![1].body).toMatchObject({ role: 'CUSTOMER' });
  expect(screen.getByRole('textbox', { name: 'Name' })).toBeDisabled();
  expect(roleSelect()).toBeDisabled();
  expect(roleSelect()).toHaveValue('CUSTOMER');
});

it('returns to the related step for native validation errors and allows correction', async () => {
  api.mockImplementation(async (_, request) => {
    if (request.method === 'POST')
      throw {
        status: 422,
        message: 'Invalid contact email',
        fields: { 'contact.section': 'Invalid contact email' },
      };
    return response(request.path, request.method, request.body) as never;
  });
  show();
  await fillParty();
  await step('Address and contact');
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Add default contact' }),
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Name' }),
    'Accounts',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Email' }),
    'invalid',
  );
  await step('Party details');
  await userEvent.click(screen.getByRole('button', { name: 'Create party' }));
  const email = await screen.findByRole('textbox', { name: 'Email' });
  expect(email).toHaveValue('invalid');
  expect(screen.getByText('Invalid contact email')).toBeVisible();
  await userEvent.clear(email);
  await userEvent.type(email, 'accounts@example.test');
  expect(screen.queryByText('Invalid contact email')).not.toBeInTheDocument();
});
it('offers non-party account kinds on general creation and preserves contextual party ledgers', async () => {
  const view = render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('accounts')!}
    />,
  );
  await userEvent.click(await screen.findByRole('combobox', { name: 'Kind' }));
  expect(
    screen.queryByRole('option', { name: 'Party' }),
  ).not.toBeInTheDocument();
  view.unmount();
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('accounts')!}
      prefills={{ kind: 'PARTY', party_id: PARTY, party_role: 'SUPPLIER' }}
    />,
  );
  expect(
    await screen.findByRole('combobox', { name: 'Kind' }),
  ).toHaveTextContent('Party');
});

/* ------------------------------------------------ the role and its ledger account are mandatory */

const ROLES = ['CUSTOMER', 'SUPPLIER', 'OTHER', 'BROKER'];
const create = (supplier = false) =>
  screen.getByRole('button', { name: supplier ? 'Create supplier' : 'Create party' });
/** The value beside a label in the creation summary. */
const summary = (label: string) =>
  screen.getByText(label, { selector: 'dt' }).nextElementSibling as HTMLElement;
/** `party-roles` metadata with the role field changed, as a narrower grant or field policy would send it. */
function roleForm(change: (field: Record<string, unknown>) => void, top: object = {}) {
  const value = form('party-roles');
  change(value.fields.find((field) => field.key === 'role') as unknown as Record<string, unknown>);
  return { ...value, ...top };
}
function withRoleForm(value: unknown) {
  api.mockImplementation(async (_, request) => {
    if (request.path.includes('/configuration/party-roles/')) return value as never;
    return response(request.path, request.method, request.body) as never;
  });
}

it('asks for the role as a required choice that starts unchosen and says what it decides', async () => {
  show();
  await screen.findByRole('textbox', { name: 'Code' });
  const select = roleSelect();
  expect(select).toBeRequired();
  expect(select).toHaveValue('');
  expect(within(select).getAllByRole('option').map((option) => option.textContent)).toEqual([
    'Choose a role',
    'Customer',
    'Supplier',
    'Other',
    'Broker',
  ]);
  expect(within(select).queryByRole('option', { name: 'No role yet' })).not.toBeInTheDocument();
  expect(
    screen.getByText('The role decides the ledger account created with the party.'),
  ).toBeVisible();
});

it('will not create a party without a role: it names the error, returns to step 1 and sends nothing', async () => {
  show();
  await fillParty(null);
  await step('Tax and other details');
  // The role lives on the first step: it is not on screen from here.
  expect(screen.queryByRole('combobox', { name: 'Party role' })).not.toBeInTheDocument();
  await userEvent.click(create());
  const select = await screen.findByRole('combobox', { name: 'Party role' });
  expect(screen.getByRole('region', { name: 'Party details' })).toBeVisible();
  expect(select).toHaveAttribute('aria-invalid', 'true');
  expect(
    screen.getByText('Choose the party role. It decides which ledger account is created.'),
  ).toBeVisible();
  expect(
    within(screen.getByRole('navigation', { name: 'Setup progress' })).getByText('Needs attention'),
  ).toBeVisible();
  // Focus is back in the first step (on its panel or on the invalid role control), not left on a hidden step.
  const panel = screen.getByRole('region', { name: 'Party details' });
  await waitFor(() => expect(panel.contains(document.activeElement)).toBe(true));
  expect(writes()).toHaveLength(0);
  // Choosing the role clears the error, and the same form then creates the party.
  await userEvent.selectOptions(select, 'SUPPLIER');
  expect(
    screen.queryByText('Choose the party role. It decides which ledger account is created.'),
  ).not.toBeInTheDocument();
  await userEvent.click(create());
  await waitFor(() => expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({ role: 'SUPPLIER' });
});

it('blocks a roleless submit from the first step too, whatever else is filled in', async () => {
  show();
  await fillParty(null);
  await userEvent.click(create());
  expect(await screen.findByText(/Choose the party role/)).toBeVisible();
  expect(roleSelect()).toHaveAttribute('aria-invalid', 'true');
  expect(writes()).toHaveLength(0);
});

it.each(ROLES)('sends the chosen role %s in the one create-with-details request', async (role) => {
  show();
  await fillParty(role);
  await userEvent.click(create());
  await waitFor(() => expect(writes()).toHaveLength(1));
  expect(writes()[0]![1]).toMatchObject({
    path: `/v1/companies/${COMPANY}/parties/create-with-details`,
    method: 'POST',
    body: { code: 'TEST', role },
  });
  // One request creates the party, its role and its account: nothing else is written.
  expect(writes().every(([, request]) => request.path.endsWith('/parties/create-with-details'))).toBe(true);
});

it.each(ROLES)('never sends a ledger choice for %s: the server takes its defaults', async (role) => {
  show();
  await fillParty(role);
  await userEvent.click(create());
  await waitFor(() => expect(writes()).toHaveLength(1));
  const body = writes()[0]![1].body as Record<string, unknown>;
  expect(body).not.toHaveProperty('ledger');
  expect(JSON.stringify(body)).not.toMatch(/ledger|account_id|group_id/);
});

it('always sends SUPPLIER from New supplier, which has no role to choose', async () => {
  show(true);
  await fillParty(null);
  expect(screen.queryByRole('combobox', { name: 'Party role' })).not.toBeInTheDocument();
  expect(
    screen.getByText('The supplier role and its payable account are created and activated with this supplier.'),
  ).toBeVisible();
  expect(summary('Role')).toHaveTextContent('Supplier');
  expect(summary('Ledger account')).toHaveTextContent('Created under Sundry Creditors');
  await userEvent.click(create(true));
  await waitFor(() => expect(writes()).toHaveLength(1));
  const body = writes()[0]![1].body as Record<string, unknown>;
  expect(body.role).toBe('SUPPLIER');
  expect(body).not.toHaveProperty('ledger');
});

it('summarises the role and the ledger account it creates, before and after a role is chosen', async () => {
  show();
  await screen.findByRole('textbox', { name: 'Code' });
  expect(summary('Role')).toHaveTextContent('Choose a role');
  expect(summary('Ledger account')).toHaveTextContent('Created with the role');
  const expected: Record<string, [string, string]> = {
    CUSTOMER: ['Customer', 'Created under Sundry Debtors'],
    SUPPLIER: ['Supplier', 'Created under Sundry Creditors'],
    OTHER: ['Other', 'Created under Sundry Creditors'],
    BROKER: ['Broker', 'Created under Sundry Creditors'],
  };
  for (const [role, [label, ledger]] of Object.entries(expected)) {
    await userEvent.selectOptions(roleSelect(), role);
    expect(summary('Role')).toHaveTextContent(label);
    expect(summary('Ledger account')).toHaveTextContent(ledger);
  }
  // Going back to "Choose a role" restores the neutral summary.
  await userEvent.selectOptions(roleSelect(), '');
  expect(summary('Role')).toHaveTextContent('Choose a role');
  expect(summary('Ledger account')).toHaveTextContent('Created with the role');
});

it('says the party, its role and its ledger account are created together', async () => {
  show();
  await screen.findByRole('textbox', { name: 'Code' });
  expect(
    screen.getByText(
      'The party, its role and its ledger account are created together and become active. Entered addresses and contacts become active defaults. Payment policies can be configured from the saved party.',
    ),
  ).toBeVisible();
  expect(screen.queryByText(/Ledger accounts and payment policies can be configured/)).not.toBeInTheDocument();
});

const withoutAccounts = resources.filter((name) => name !== 'accounts');
it.each([
  ['accounts not offered', false, withoutAccounts, withoutAccounts],
  ['accounts offered but not manageable', false, resources, withoutAccounts],
  ['accounts not offered', true, withoutAccounts, withoutAccounts],
  ['accounts offered but not manageable', true, resources, withoutAccounts],
] as const)(
  'warns and refuses to create when %s (supplier: %s)',
  async (_why, supplier, available, manageable) => {
    show(supplier, [...available], undefined, [...manageable]);
    await screen.findByRole('textbox', { name: 'Code' });
    expect(
      screen.getByText('Every party is created with its ledger account, which needs permission to create accounts.'),
    ).toBeVisible();
    expect(create(supplier)).toBeDisabled();
    // The guard is in the submit handler too, not only on the button.
    await userEvent.type(screen.getByRole('textbox', { name: 'Code' }), 'TEST');
    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'Test party');
    fireEvent.submit(create(supplier).closest('form')!);
    expect(writes()).toHaveLength(0);
  },
);

it('does not warn about accounts when the user can create them', async () => {
  show();
  await screen.findByRole('textbox', { name: 'Code' });
  expect(screen.queryByText(/needs permission to create accounts/)).not.toBeInTheDocument();
  expect(create()).toBeEnabled();
});

it('requires permission to create the party role before creating a plain party', async () => {
  withRoleForm({ ...form('party-roles'), can_create: false });
  show();
  await screen.findByRole('textbox', { name: 'Code' });
  expect(screen.getByText('Creating a party requires permission to create its role.')).toBeVisible();
  expect(screen.queryByRole('combobox', { name: 'Party role' })).not.toBeInTheDocument();
  expect(create()).toBeDisabled();
  fireEvent.submit(create().closest('form')!);
  expect(writes()).toHaveLength(0);
});

it('keeps the supplier notice unchanged when the supplier role cannot be created', async () => {
  withRoleForm({ ...form('party-roles'), can_create: false });
  show(true);
  await screen.findByRole('textbox', { name: 'Code' });
  expect(
    screen.getByText('Supplier creation requires permission to create its supplier role.'),
  ).toBeVisible();
  expect(screen.queryByText('Creating a party requires permission to create its role.')).not.toBeInTheDocument();
});

it('disables creation when the role field is protected, so there is no role to choose', async () => {
  withRoleForm(roleForm((field) => { field.editable = false; }));
  show();
  await screen.findByRole('textbox', { name: 'Code' });
  expect(screen.queryByRole('combobox', { name: 'Party role' })).not.toBeInTheDocument();
  expect(screen.getByText('Creating a party requires permission to create its role.')).toBeVisible();
  expect(create()).toBeDisabled();
  expect(writes()).toHaveLength(0);
});

it('disables creation when the role field offers no choices', async () => {
  withRoleForm(roleForm((field) => {
    (field.control as { choices: string[] }).choices = [];
  }));
  show();
  await screen.findByRole('textbox', { name: 'Code' });
  expect(screen.queryByRole('combobox', { name: 'Party role' })).not.toBeInTheDocument();
  expect(create()).toBeDisabled();
});

it('offers only the roles the metadata allows and creates with one of them', async () => {
  withRoleForm(roleForm((field) => {
    (field.control as { choices: string[] }).choices = ['CUSTOMER', 'OTHER'];
  }));
  show();
  await fillParty(null);
  expect(within(roleSelect()).getAllByRole('option').map((option) => option.textContent)).toEqual([
    'Choose a role',
    'Customer',
    'Other',
  ]);
  await userEvent.selectOptions(roleSelect(), 'OTHER');
  await userEvent.click(create());
  await waitFor(() => expect(writes()).toHaveLength(1));
  expect(writes()[0]![1].body).toMatchObject({ role: 'OTHER' });
});

it('disables New supplier when the supplier role is not among the role choices', async () => {
  withRoleForm(roleForm((field) => {
    (field.control as { choices: string[] }).choices = ['CUSTOMER'];
  }));
  show(true);
  await screen.findByRole('textbox', { name: 'Code' });
  expect(
    screen.getByText('Supplier creation requires permission to create its supplier role.'),
  ).toBeVisible();
  expect(create(true)).toBeDisabled();
});
