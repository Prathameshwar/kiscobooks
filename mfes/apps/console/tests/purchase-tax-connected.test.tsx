import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseEntryConnected } from '../app/components/PurchaseEntryConnected';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';
import { purchaseSource, supplierPayables } from '../app/lib/purchase-entry';
import { purchaseInput, type PurchaseBinding, type PurchaseVoucher } from '../app/lib/purchase-api';
import { blankPurchaseLine, newPurchaseWorkspace } from '../app/lib/purchase-workspace';
import { blankPurchaseTax, noTaxFacts } from '../app/lib/purchase-tax';
import { company, draft as sources, metadata as fixture } from './purchase-entry-fixtures';
import type { PurchaseWorkspaceController } from '../app/components/PurchaseWorkspace';
import type { FieldSet } from '../app/lib/voucher-fields';

vi.mock('../app/lib/service-call', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/purchase-entry', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/purchase-entry')>(), purchaseSource: vi.fn(), supplierPayables: vi.fn(), purchaseLookup: vi.fn(() => vi.fn()) }));
vi.mock('../app/components/AccountingConfigurationCommon', async importOriginal => ({
  ...await importOriginal<typeof import('../app/components/AccountingConfigurationCommon')>(),
  AccountingReference: ({ label, value, onChange }: { label: string; value: string | null; onChange: (value: string | null) => void }) =>
    <input aria-label={label} value={value ?? ''} onChange={event => onChange(event.target.value || null)} />,
}));
vi.mock('../app/components/PurchaseWorkspace', () => ({ PurchaseWorkspace: ({ controller: c }: { controller: PurchaseWorkspaceController }) => <section>{c.header}{c.banner(null)}
  <button onClick={() => c.dispatch({ type: 'supplier', value: sources.party!.id, policy: {} as never })}>Choose supplier</button>
  <button onClick={() => c.dispatch({ type: 'subject', key: c.draft.lines[0]!.key, subject: { id: sources.supplies[0]!.account!.id, label: 'Expense', kind: 'ACCOUNT', unit: '', meta: '' } })}>Choose expense</button>
  <input aria-label="Invoice" value={c.draft.invoice} onChange={e => c.dispatch({ type: 'header', field: 'invoice', value: e.target.value })} />
  <input aria-label="Invoice date" value={c.draft.invoiceDate} onChange={e => c.dispatch({ type: 'header', field: 'invoiceDate', value: e.target.value })} />
  <input aria-label="Amount" value={c.draft.lines[0]!.amount} onChange={e => c.dispatch({ type: 'line', key: c.draft.lines[0]!.key, patch: { amount: e.target.value } })} />
  <span>{c.note}</span><span data-testid="lines-label">{c.linesLabel}</span>{c.sections}{c.actions({ validate: () => true, review: () => undefined })}</section> }));

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const base = '/v1/companies/' + company;
const permissions = ['vouchers.read', 'vouchers.create', 'vouchers.edit', 'vouchers.submit', 'vouchers.approve', 'vouchers.reject', 'vouchers.cancel'];
const withTax = [...permissions, 'accounting.tax.read'];
const props = { company, currency: 'INR', actor: id(12), year: id(13), canCreate: true, permissions };
const MINE = id(20), THEIRS = id(30), RULE_DEFAULT = id(40);
type Server = { companies: unknown[] | Error; supplier: unknown[]; defaults: unknown[]; reverse: boolean; calls: string[]; unsupported?: boolean };
let metadata: FieldSet, saved: Record<string, unknown>, writes: { request: ServiceRequest }[], server: Server;
const registration = (patch: Record<string, unknown> = {}) => ({ id: MINE, is_primary: true, jurisdiction_code: 'IN-MH', number: '27AAAAA0000A1Z5', tax_system: 'gst_in', valid_from: '2020-04-01', valid_to: null, ...patch });
const supplierRegistration = (patch: Record<string, unknown> = {}) => ({ id: THEIRS, company_id: company, party_id: sources.party!.id, scheme: 'GST_IN', registration_type: 'REGULAR', state_code: 'IN-GJ', registration_number: '24BBBBB1111B1Z6', valid_from: '2019-07-01', valid_to: null, ...patch });

beforeEach(() => {
  sessionStorage.clear(); vi.mocked(serviceCall).mockReset(); vi.mocked(purchaseSource).mockReset(); vi.mocked(supplierPayables).mockReset(); writes = [];
  server = { companies: [registration()], supplier: [supplierRegistration()], defaults: [{ id: RULE_DEFAULT, company_id: company, account_id: sources.supplies[0]!.account!.id, direction: 'PURCHASE' }], reverse: false, calls: [] };
  metadata = structuredClone(fixture); Object.assign(metadata.native.properties!, Object.fromEntries(['document_date', 'currency', 'narration', 'mode', 'lines', 'attachments', 'links', 'custom_fields'].map(key => [key, {}])));
  metadata.configuration.policy.invoice = { allowed_supply_kinds: ['ACCOUNT', 'SERVICE'] };
  saved = {};
  vi.mocked(purchaseSource).mockImplementation(async (_company, resource) => resource === 'suppliers' ? sources.party! : resource === 'payables' ? sources.payable! : sources.supplies[0]!.account!);
  // Choosing a supplier reads its one payable account (a supplier is never asked for it); purchase-supplier-account holds the real read.
  vi.mocked(supplierPayables).mockImplementation(async () => [sources.payable!]);
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    server.calls.push(request.service + ' ' + request.path);
    if (request.path.includes('/voucher-types?')) return { items: [{ id: id(2), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', name: 'Account purchases' }], page: { next_cursor: null } };
    if (request.path.endsWith('/voucher-capabilities')) return { financial_execution: false, invoice_execution: false, kinds: [{ kind: 'PURCHASE', execution_ready: false }] };
    if (request.path.includes('/field-set')) return metadata;
    if (request.service === 'identity' && request.path.endsWith('/tax-registrations?limit=50')) { if (server.companies instanceof Error) throw server.companies; return { items: server.companies, page: { next_cursor: null } }; }
    if (request.service === 'accounting') {
      if (request.path.includes('/party-tax-registrations?')) return { items: server.supplier.map(row => ({ id: (row as { id: string }).id, company_id: company, party_id: sources.party!.id, scheme: (row as { scheme: string }).scheme })), page: { next_cursor: null } };
      if (request.path.includes('/party-tax-registrations/')) return server.supplier.find(row => request.path.endsWith((row as { id: string }).id));
      if (request.path.includes('/account-tax-defaults?')) return { items: server.defaults, page: { next_cursor: null } };
      if (request.path.includes('/account-tax-defaults/')) return { id: RULE_DEFAULT, company_id: company, account_id: sources.supplies[0]!.account!.id, direction: 'PURCHASE', code: '998399', code_system: 'SAC', supply_kind: 'SERVICE', treatment: 'TAXABLE', rcm_applicable: server.reverse };
      return { id: request.path.split('/').at(-1), company_id: company, name: request.path.includes('/parties/') ? 'Supplier' : 'Expense' };
    }
    if (request.path.endsWith('/invoice-preview')) return { calculation_version: 1, calculation_hash: 'a'.repeat(64), currency: 'INR', commercial_total: '1000.0000', tax_total: '180.0000', charged_tax_total: '180.0000', rounding: '0.0000', payable: '1180.0000', supplier_difference: null,
      lines: [{ key: (saved.invoice as { supplies: { line_key: string }[] }).supplies[0]!.line_key, entered: '1000.0000', commercial: '1000.0000', taxable: '1000.0000', price_rounding: '0.0000', payable: '1180.0000', taxes: [{ key: 'a', code: 'CGST', basis: '1000.0000', amount: '90.0000', supplier_charged: true }, { key: 'b', code: 'SGST', basis: '1000.0000', amount: '90.0000', supplier_charged: true }] }],
      components: [], allocations: [], tax_evidence: [] };
    if (request.method === 'POST' || request.method === 'PUT') {
      writes.push({ request: structuredClone(request) });
      const body = request.body as Record<string, unknown>;
      saved = { ...((body.content ?? body) as object), id: id(90), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', status: 'DRAFT', row_version: 7, revision_number: 3, revision_id: id(91), lines: [], attachments: [], links: [], custom_fields: {} };
      return saved;
    }
    if (request.path.includes('/vouchers/')) return saved;
    throw Error('Unexpected test route ' + request.path);
  });
});

/** The bill filled in, supplier and expense chosen, up to the point of deciding about tax. */
async function fill() {
  await screen.findByRole('heading', { name: 'New purchase' });
  fireEvent.click(await screen.findByRole('button', { name: 'Choose supplier' }));
  await waitFor(() => expect(supplierPayables).toHaveBeenCalledWith(company, sources.party!.id));
  await waitFor(() => expect(screen.getByRole('button', { name: /^(Create|Update)$/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button', { name: 'Choose expense' }));
  await waitFor(() => expect(purchaseSource).toHaveBeenCalledWith(company, 'expenses', sources.supplies[0]!.account!.id));
  await waitFor(() => expect(screen.getByRole('button', { name: /^(Create|Update)$/ })).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText('Invoice'), { target: { value: 'SUP-NEW' } });
  fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '1000' } });
}
const section = () => screen.findByRole('group', { name: 'GST on this bill' });
const box = () => screen.getByRole('checkbox', { name: 'This bill carries no tax' });
/** Everything the section reads has arrived: the supplier's registration and the account's tax default. */
const ready = async () => { await section(); await screen.findByText('SAC 998399 · Taxable'); await screen.findByText(/24BBBBB1111B1Z6/); };
const save = () => fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));

describe('a Purchase bill that carries GST', () => {
  it('starts as one, once the company’s registration is known, and is not made "unsaved" by it', async () => {
    render(<PurchaseEntryConnected {...props} permissions={withTax} />);
    await section();
    expect(box()).not.toBeChecked();
    expect(box()).toHaveAccessibleDescription('Tick this if the bill carries no GST.');
    expect(screen.getByText('Not saved yet')).toBeVisible();
    expect(server.calls).toContain('identity ' + base + '/tax-registrations?limit=50');
    // Nothing about a supplier or an account is read until there is one.
    expect(server.calls.some(call => /party-tax-registrations|account-tax-defaults/.test(call))).toBe(false);
  });

  it('reads the supplier’s registration and each account’s tax default, and says what they are', async () => {
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill(); await ready();
    expect(screen.getByText('Regular registration, read from the supplier’s tax registrations.')).toBeVisible();
    expect(screen.getByText('Your GST registration').closest('dl')).toHaveTextContent('27AAAAA0000A1Z5 · MH');
    const row = within(screen.getByRole('list')).getByRole('listitem');
    expect(row).toHaveTextContent('Expense'); expect(row).toHaveTextContent('Line 1'); expect(row).toHaveTextContent('SAC 998399 · Taxable');
    expect(server.calls).toContain('accounting ' + base + '/account-tax-defaults?account_id=' + sources.supplies[0]!.account!.id + '&direction=PURCHASE&as_of=' + (screen.getByLabelText('Invoice date') as HTMLInputElement).value + '&limit=5');
  });

  it('saves with the GST context, and bills each line as a service', async () => {
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill(); await ready();
    save(); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    const invoice = (writes[0]!.request.body as { invoice: { tax: Record<string, unknown>; supplies: { supply_kind: string; amount: string }[] } }).invoice;
    expect(invoice.tax).toEqual({
      profile: 'INDIA_DOMESTIC_SERVICE', company_registration_id: MINE, party_registration_id: THEIRS, place_of_supply: 'IN-MH',
      service_completion_date: (screen.getByLabelText('Invoice date') as HTMLInputElement).value, supplier_invoice_number: 'SUP-NEW', supplier_invoice_date: (screen.getByLabelText('Invoice date') as HTMLInputElement).value,
    });
    expect(invoice.supplies.map(line => [line.supply_kind, line.amount])).toEqual([['SERVICE', '1000']]);
  });

  it('keeps the section, with what was saved, when the saved bill is opened again', async () => {
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill(); await ready();
    fireEvent.change(screen.getByRole('textbox', { name: /Place of supply/ }), { target: { value: 'IN-KA' } });
    save(); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    expect(box()).not.toBeChecked();
    expect(screen.getByRole('textbox', { name: /Place of supply/ })).toHaveValue('IN-KA');
    // Opened again, nothing is pending: saving again needs a change.
    expect(screen.getByRole('button', { name: /^(Create|Update)$/ })).toBeDisabled();
  });

  it('calls the footer figure "Lines before GST" while the bill carries GST, and plain again when it carries none', async () => {
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill(); await section();
    expect(screen.getByTestId('lines-label')).toHaveTextContent('Lines before GST');
    fireEvent.click(box());
    expect(screen.getByTestId('lines-label')).toBeEmptyDOMElement();
  });

  it('records reverse charge when that is chosen', async () => {
    server.reverse = true;
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill(); await section();
    await waitFor(() => expect(screen.getAllByRole('listitem')[0]).toHaveTextContent(/set to reverse charge/));
    fireEvent.change(screen.getByRole('combobox', { name: /How GST is charged/ }), { target: { value: 'REVERSE' } });
    await waitFor(() => expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('SAC 998399 · Taxable'));
    save(); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    expect((writes[0]!.request.body as { invoice: { tax: { profile: string } } }).invoice.tax.profile).toBe('INDIA_DOMESTIC_SERVICE_RCM');
  });

  it('warns about an account that disagrees with the bill, without stopping the person saving a draft', async () => {
    server.reverse = true;
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill(); await section();
    await waitFor(() => expect(screen.getAllByRole('listitem')[0]).toHaveTextContent(/set to reverse charge/));
    save(); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    expect(writes).toHaveLength(1);
  });

  it('stops a save that cannot say which supplier registration it is under, and says why beside the field', async () => {
    server.supplier = [];
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill(); await section();
    await screen.findByText('The supplier has no GST registration on record');
    save();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Read the tax details again' })).toHaveFocus());
    expect(screen.getByText(/This supplier has no GST registration on record/)).toBeVisible();
    // The refusal is about GST: it is not dressed up as an unticked "no tax" box.
    expect(screen.queryByText(/Confirm that this is an untaxed/)).toBeNull();
    expect(box()).not.toHaveAttribute('aria-invalid');
    expect(writes).toHaveLength(0);
  });

  it.each([['COMPOSITION'], ['UNREGISTERED']])('does not let a %s supplier be taxed, and offers the bill without tax instead', async type => {
    server.supplier = [supplierRegistration({ registration_type: type })];
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill(); await section();
    await screen.findByText('GST can only be recorded for a regular GST supplier');
    save();
    await waitFor(() => expect(writes).toHaveLength(0));
    fireEvent.click(box());
    save(); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    expect((writes[0]!.request.body as { invoice: { tax: unknown } }).invoice.tax).toEqual({ profile: 'UNTAXED_ACCOUNT' });
  });

  it('moves to the field that needs attention', async () => {
    server.supplier = [supplierRegistration(), supplierRegistration({ id: id(31), state_code: 'IN-KA', registration_number: '29BBBBB1111B1Z6' })];
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill(); await section();
    const select = await screen.findByRole('combobox', { name: /Supplier’s GST registration/ });
    save();
    await waitFor(() => expect(select).toHaveFocus());
    expect(writes).toHaveLength(0);
    fireEvent.change(select, { target: { value: id(31) } });
    save(); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    expect((writes[0]!.request.body as { invoice: { tax: { party_registration_id: string } } }).invoice.tax.party_registration_id).toBe(id(31));
  });

  it('shows the GST Accounting calculated, line by line, once the saved bill is calculated', async () => {
    render(<PurchaseEntryConnected {...props} permissions={[...withTax]} />); await fill(); await ready();
    save(); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    fireEvent.click(screen.getByRole('button', { name: 'Calculate saved bill' }));
    const card = await screen.findByRole('region', { name: 'Accounting calculation' });
    expect(within(card).getByText('CGST')).toBeVisible();
    expect(within(card).getByText('SGST')).toBeVisible();
    const row = within(within(card).getByRole('table', { name: 'GST line by line' })).getByRole('row', { name: /Expense/ });
    expect(within(row).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['₹1,000.00', '₹180.00', '₹1,180.00']);
  });
});

describe('a Purchase bill with no tax', () => {
  it('hides the GST section while the box is ticked, and says no tax was recorded', async () => {
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill(); await section();
    fireEvent.click(box());
    expect(box()).toBeChecked();
    expect(screen.queryByRole('group', { name: 'GST on this bill' })).toBeNull();
    expect(box()).toHaveAccessibleDescription('Untick this if the bill includes GST.');
    save(); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    const invoice = (writes[0]!.request.body as { invoice: { tax: unknown; supplies: { supply_kind: string }[] } }).invoice;
    expect(invoice.tax).toEqual({ profile: 'UNTAXED_ACCOUNT' });
    expect(invoice.supplies[0]!.supply_kind).toBe('ACCOUNT');
  });

  it('brings the section back, with the choice as it was left, when the box is unticked again', async () => {
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill(); await ready();
    fireEvent.change(screen.getByRole('textbox', { name: /Place of supply/ }), { target: { value: 'IN-KA' } });
    fireEvent.click(box()); fireEvent.click(box());
    expect(screen.getByRole('textbox', { name: /Place of supply/ })).toHaveValue('IN-KA');
    expect(box()).toHaveAccessibleDescription('Tick this if the bill carries no GST.');
  });

  it('is still saved only when the person has said so', async () => {
    render(<PurchaseEntryConnected {...props} permissions={permissions} />); await fill();
    save(); await screen.findByText(/Confirm that this is an untaxed/);
    expect(writes).toHaveLength(0);
  });
});

describe('where GST cannot be recorded', () => {
  it('reads no tax master for someone without tax access, and says what is needed', async () => {
    render(<PurchaseEntryConnected {...props} permissions={permissions} />); await fill();
    expect(screen.queryByRole('group', { name: 'GST on this bill' })).toBeNull();
    expect(box()).toHaveAccessibleDescription('Required before saving. You need access to tax masters to record GST on a bill.');
    fireEvent.click(box()); expect(box()).toBeChecked();
    expect(server.calls.some(call => /tax-registrations|account-tax-defaults/.test(call))).toBe(false);
    save(); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    expect((writes[0]!.request.body as { invoice: { tax: unknown } }).invoice.tax).toEqual({ profile: 'UNTAXED_ACCOUNT' });
  });

  it('says so when the company has no GST registration in force on the bill’s date', async () => {
    server.companies = [registration({ valid_to: '2026-03-31' }), registration({ id: id(21), tax_system: 'vat' })];
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill();
    await waitFor(() => expect(box()).toHaveAccessibleDescription(/no GST registration in force on the invoice date/));
    expect(screen.queryByRole('group', { name: 'GST on this bill' })).toBeNull();
    save(); await screen.findByText(/Confirm that this is an untaxed/);
  });

  it('says so when the voucher type takes no service supplies', async () => {
    metadata.configuration.policy.invoice = { allowed_supply_kinds: ['ACCOUNT'] };
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill();
    expect(box()).toHaveAccessibleDescription(/does not allow service purchase lines.*purchase rules/);
    expect(server.calls.some(call => /tax-registrations/.test(call))).toBe(false);
  });

  it('says why when the company’s registrations could not be read, and the bill can still be recorded without tax', async () => {
    server.companies = Object.assign(new Error('Identity is unavailable.'), {});
    render(<PurchaseEntryConnected {...props} permissions={withTax} />); await fill();
    await waitFor(() => expect(box()).toHaveAccessibleDescription(/could not be read: Identity is unavailable\./));
    fireEvent.click(box()); save(); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    expect(writes).toHaveLength(1);
  });
});

describe('a saved bill that carries GST', () => {
  const taxedVoucher = () => {
    const wire = newPurchaseWorkspace('2026-10-30');
    Object.assign(wire, { mode: 'ACCOUNTS', supplier: sources.party!.id, payable: sources.payable!.id, invoice: 'SUP-42', lines: [{ ...blankPurchaseLine('p1', 'ACCOUNT'), subject: sources.supplies[0]!.account!.id, label: 'Expense', description: 'Consulting', amount: '1000' }] });
    wire.details.termsDays = '2'; wire.tax = { ...blankPurchaseTax(), choice: 'FORWARD' };
    const binding: PurchaseBinding = { company, currency: 'INR', metadata, keys: new Map(), partyKey: sources.partyLineKey, sources: new Map([sources.party!, sources.payable!, sources.supplies[0]!.account!].map(source => [source.id, source])) };
    const facts = { ...noTaxFacts(), companies: [{ id: MINE, number: '27AAAAA0000A1Z5', state: 'IN-MH', primary: true, from: '2020-04-01', to: null }], suppliers: new Map([[sources.party!.id, [{ id: THEIRS, type: 'REGULAR', state: 'IN-GJ', number: '24BBBBB1111B1Z6', from: '2019-07-01', to: null }]]]) };
    return { ...purchaseInput(wire, binding, facts), id: id(90), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', status: 'DRAFT', revision_id: id(91), row_version: 7, revision_number: 3, lines: [], attachments: [], links: [], custom_fields: {} } as unknown as PurchaseVoucher;
  };

  it('opens with the GST section filled from what was saved, and sends the same block back when something else changes', async () => {
    saved = taxedVoucher() as unknown as Record<string, unknown>;
    render(<PurchaseEntryConnected {...props} permissions={withTax} initialVoucherId={id(90)} />);
    await screen.findByRole('heading', { name: 'Purchase bill · revision 3' }); await section();
    expect(box()).not.toBeChecked();
    expect(screen.getByRole('textbox', { name: /Place of supply/ })).toHaveValue('IN-MH');
    await screen.findByText(/24BBBBB1111B1Z6/);
    const before = (saved.invoice as { tax: unknown }).tax;
    await waitFor(() => expect(screen.getByLabelText('Amount')).toBeVisible());
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '1200' } });
    await waitFor(() => expect(screen.getByRole('button', { name: /^(Create|Update)$/ })).not.toBeDisabled());
    save(); await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]!.request).toMatchObject({ method: 'PUT', body: { content: { invoice: { tax: before, supplies: [{ amount: '1200', supply_kind: 'SERVICE' }] } } } });
  });

  it('shows what the bill carries, but not its registrations, to someone without tax access, and will not re-save it', async () => {
    saved = taxedVoucher() as unknown as Record<string, unknown>;
    render(<PurchaseEntryConnected {...props} permissions={permissions} initialVoucherId={id(90)} />);
    await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    expect(await screen.findByText('This bill carries GST')).toBeVisible();
    expect(screen.getByText(/The supplier charged the GST\. Its registrations are not shown/)).toBeVisible();
    expect(screen.queryByRole('group', { name: 'GST on this bill' })).toBeNull();
    await waitFor(() => expect(screen.getByLabelText('Amount')).toBeVisible());
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '1200' } });
    await waitFor(() => expect(screen.getByRole('button', { name: /^(Create|Update)$/ })).not.toBeDisabled());
    save();
    expect(await screen.findByText(/changing it needs access to tax masters/)).toBeVisible();
    expect(writes).toHaveLength(0);
    expect(server.calls.some(call => /tax-registrations|account-tax-defaults/.test(call))).toBe(false);
  });
});

