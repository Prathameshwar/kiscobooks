import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExpenseAccountQuickCreate, SupplierQuickCreate } from '../app/components/PurchaseQuickCreate';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';
import {capture} from './master-opening-fixture';

vi.setConfig({ testTimeout: 20000 });
vi.mock('../app/lib/service-call', async original => ({ ...await original<object>(), serviceCall: vi.fn() }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1);
const page = (items: unknown[]) => ({ items, page: { limit: 200, has_more: false, next_cursor: null } });
const countries = page([{ value: 'IN', label: 'India', code: 'IN' }, { value: 'US', label: 'United States', code: 'US' }]);
const head = { id: id(10), company_id: company, name: 'Expenses', nature: 'EXPENSE' };
const expenseGroups = [{ id: id(20), company_id: company, name: 'Direct Expenses', head_id: id(10) }, { id: id(21), company_id: company, name: 'Indirect Expenses', head_id: id(10) }];
const otherGroup = { id: id(22), company_id: company, name: 'Sales Accounts', head_id: id(11) };
const supplierRecord = (patch: object = {}) => ({ id: id(50), company_id: company, row_version: 1, status: 'ACTIVE', name: 'Sharma Traders', code: 'SHARMA-TRADERS', ...patch });
const accountRecord = (patch: object = {}) => ({ id: id(60), company_id: company, row_version: 1, status: 'ACTIVE', kind: 'GENERAL', inventory_affected: false, posting_policy: 'MANUAL_ALLOWED', group_id: id(21), name: 'Office rent', code: 'OFFICE-RENT', ...patch });

type Handler = (request: ServiceRequest) => unknown;
/** Reads are answered here; the one write goes to `write`. */
function serve(write: Handler, groups: unknown[] = [...expenseGroups, otherGroup], captureRead:()=>unknown=()=>({...capture,company_id:company})) {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if(request.path.endsWith('/master-balances/capture'))return await captureRead() as never;
    if (request.path.includes('/configuration/options/countries')) return countries as never;
    if (request.path.includes('/configuration/options/states')) return page([{ value: 'MH', label: 'Maharashtra', code: '27' }, { value: 'KA', label: 'Karnataka', code: '29' }]) as never;
    // as the real API answers: head rows are lean, the nature is on the head itself
    if (request.path.includes('/account-heads?')) return page([{ id: head.id, company_id: company, name: head.name }, { id: id(11), company_id: company, name: 'Income' }]) as never;
    if (request.path.endsWith('/account-heads/' + id(10))) return head as never;
    if (request.path.endsWith('/account-heads/' + id(11))) return { id: id(11), company_id: company, name: 'Income', nature: 'INCOME' } as never;
    if (request.path.includes('/account-groups?')) return page(groups) as never;
    if (request.method === 'POST') return write(request) as never;
    throw { status: 404, message: 'unexpected ' + request.path };
  });
}
const writes = () => vi.mocked(serviceCall).mock.calls.map(call => call[1]).filter(request => request.method === 'POST');
beforeEach(() => { vi.mocked(serviceCall).mockReset(); });
it.each(['supplier','expense'])('confirms an uncertain quick %s creation after opening access changes',async(kind)=>{
  let reads=0,posts=0,resolveCapture!:(value:typeof capture)=>void;
  serve(()=>{if(++posts===1)throw {status:503,message:'Outcome unknown'};return kind==='supplier'?supplierRecord():accountRecord();},undefined,()=>++reads===1?{...capture,company_id:company}:new Promise<typeof capture>(resolve=>{resolveCapture=resolve;}));
  const onCreated=vi.fn();render(kind==='supplier'?<SupplierQuickCreate company={company} companyCountry="IN" canTax={false} onCreated={onCreated} onClose={vi.fn()}/>:<ExpenseAccountQuickCreate company={company} onCreated={onCreated} onClose={vi.fn()}/>);
  fireEvent.change(screen.getByRole('textbox',{name:kind==='supplier'?'Supplier name':'Account name'}),{target:{value:kind==='supplier'?'Sharma Traders':'Office rent'}});
  if(kind==='supplier')await waitFor(()=>expect(screen.getByRole('combobox',{name:/Country/})).toHaveValue('India'));else await waitFor(()=>expect(screen.getByRole('combobox',{name:'Account group'})).toBeEnabled());
  await userEvent.click(screen.getByRole('checkbox',{name:'Add opening balance'}));await waitFor(()=>expect(screen.getByLabelText('Opening balance')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Opening balance'),{target:{value:'100.0001'}});await userEvent.selectOptions(screen.getByRole('combobox',{name:'Dr / Cr'}),'CREDIT');
  await userEvent.click(screen.getByRole('checkbox',{name:'Add opening balance'}));await userEvent.click(screen.getByRole('checkbox',{name:'Add opening balance'}));await waitFor(()=>expect(reads).toBe(2));
  await userEvent.click(screen.getByRole('button',{name:kind==='supplier'?'Create supplier':'Create account'}));await screen.findByRole('button',{name:'Retry'});
  await act(async()=>resolveCapture({...capture,company_id:company,can_capture:false}));await userEvent.click(screen.getByRole('button',{name:'Retry'}));
  await waitFor(()=>expect(onCreated).toHaveBeenCalledTimes(1));expect(writes()).toHaveLength(2);expect(writes()[1]).toEqual(writes()[0]);
});

it('reveals an optional opening at the end of quick supplier creation and saves it in the same request',async()=>{
  serve(()=>supplierRecord());const {user,name,create}=supplier();await user.type(name(),'Sharma Traders');
  expect(screen.queryByRole('textbox',{name:'Opening balance'})).toBeNull();await user.click(screen.getByRole('checkbox',{name:'Add opening balance'}));
  const amount=await screen.findByRole('textbox',{name:'Opening balance'});await waitFor(()=>expect(amount).toBeEnabled());await user.type(amount,'50.0001');await user.selectOptions(screen.getByRole('combobox',{name:'Dr / Cr'}),'CREDIT');await user.click(create());
  await waitFor(()=>expect(writes()).toHaveLength(1));expect(writes()[0]!.body).toMatchObject({opening:{amount:'50.0001',side:'CREDIT',opening_date:'2026-04-01'}});
});

function supplier(props: { companyCountry?: string; canTax?: boolean } = {}) {
  const onCreated = vi.fn(), onClose = vi.fn(), user = userEvent.setup();
  render(<SupplierQuickCreate company={company} companyCountry={props.companyCountry ?? 'IN'} canTax={props.canTax ?? false} onCreated={onCreated} onClose={onClose} />);
  const name = () => screen.getByRole('textbox', { name: /Supplier name/ });
  const code = () => screen.getByRole('textbox', { name: /Supplier code/ });
  const create = () => screen.getByRole('button', { name: /^(Create supplier|Retry)$/ });
  return { onCreated, onClose, user, name, code, create };
}

describe('SupplierQuickCreate', () => {
  it('opens as a right-hand dialog that says what it makes, with the cursor already in the name', async () => {
    serve(() => supplierRecord());
    const { name } = supplier();
    const dialog = screen.getByRole('dialog', { name: 'New supplier' });
    expect(within(dialog).getByText(/with its payable account/)).toBeVisible();
    expect(name()).toHaveFocus();
    expect(await within(dialog).findByRole('combobox', { name: /Country/ })).toBeVisible();
  });

  it('suggests the code from the name, and the company’s country, and has no separate legal name to fill', async () => {
    serve(() => supplierRecord());
    const { user, name, code } = supplier();
    expect(screen.queryByRole('textbox', { name: /Legal name/ })).toBeNull();
    await user.type(name(), 'Sharma & Sons');
    expect(code()).toHaveValue('SHARMA-SONS');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
  });

  it('stops following the name once the code is written over, and follows again if it is emptied', async () => {
    serve(() => supplierRecord());
    const { user, name, code } = supplier();
    await user.type(name(), 'Sharma');
    await user.clear(code()); await user.type(code(), 'SH01');
    await user.type(name(), ' Traders');
    expect(code()).toHaveValue('SH01');
    await user.clear(code());
    await user.type(name(), ' Co');
    expect(code()).toHaveValue('SHARMA-TRADERS-CO');
  });

  it('falls back to India when the company country is not a country code', async () => {
    serve(() => supplierRecord());
    supplier({ companyCountry: 'unknown' });
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
  });

  it('uses the company country when it has one', async () => {
    serve(() => supplierRecord());
    supplier({ companyCountry: 'US' });
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('United States'));
  });

  it('creates the supplier and its payable account in one idempotent request, then hands the record back', async () => {
    serve(() => supplierRecord());
    const { user, name, create, onCreated } = supplier();
    await user.type(name(), 'Sharma Traders');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
    await user.click(create());
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(onCreated).toHaveBeenCalledWith({ id: id(50), label: 'Sharma Traders', meta: 'SHARMA-TRADERS' });
    expect(writes()).toHaveLength(1);
    expect(writes()[0]).toMatchObject({
      service: 'accounting', method: 'POST', path: `/v1/companies/${company}/parties/create-with-details`,
      body: { code: 'SHARMA-TRADERS', name: 'Sharma Traders', legal_name: 'Sharma Traders', party_type: 'ORGANISATION', country_code: 'IN', role: 'SUPPLIER', ledger: {} },
    });
    expect(writes()[0]!.key).toMatch(/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);
  });

  it('keeps its Enter and its submit to itself: neither reaches the bill behind it, and the form submits', async () => {
    serve(() => supplierRecord());
    const behind = vi.fn(), submitted = vi.fn();
    const onCreated = vi.fn(), user = userEvent.setup();
    render(<form onSubmit={submitted}><div onKeyDown={event => { if (event.key === 'Enter') behind(); }}>
      <SupplierQuickCreate company={company} companyCountry="IN" canTax={false} onCreated={onCreated} onClose={vi.fn()} /></div></form>);
    await user.type(screen.getByRole('textbox', { name: /Supplier name/ }), 'Sharma Traders');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
    fireEvent.keyDown(screen.getByRole('textbox', { name: /Supplier code/ }), { key: 'Enter' });
    // The browser's implicit submission (Enter in a field, button linked by the form attribute) ends in this event.
    fireEvent.submit(document.querySelector('[data-quick-create-form]')!);
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(behind).not.toHaveBeenCalled();
    expect(submitted).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /Create supplier|Creating supplier…/ })).toHaveAttribute('form', document.querySelector('[data-quick-create-form]')!.id);
  });

  it('shows every missing field beside it, sends nothing, and puts the cursor on the first', async () => {
    serve(() => supplierRecord());
    const { user, name, code, create } = supplier();
    await user.click(create());
    expect(writes()).toHaveLength(0);
    expect(name()).toHaveAccessibleDescription(/Enter the supplier name/);
    expect(code()).toHaveAccessibleDescription(/Enter a supplier code/);
    expect(name()).toHaveFocus();
    expect(screen.queryByText('The supplier was not created')).toBeNull();
  });

  it('locks the form and names the work while the request is in flight, and ignores a second click', async () => {
    let finish!: (value: unknown) => void;
    serve(() => new Promise(resolve => { finish = resolve; }));
    const { user, name, code, create, onCreated } = supplier();
    await user.type(name(), 'Sharma Traders');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
    await user.click(create());
    const busy = await screen.findByRole('button', { name: 'Creating supplier…' });
    expect(busy).toBeDisabled();
    expect(name()).toBeDisabled(); expect(code()).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    fireEvent.submit(document.querySelector('[data-quick-create-form]')!);
    expect(writes()).toHaveLength(1);
    finish(supplierRecord());
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
  });

  it('puts a service rejection beside its field, keeps the form editable, and sends a fresh request when it is fixed', async () => {
    let attempt = 0;
    serve(() => { attempt += 1; if (attempt === 1) throw { status: 422, message: 'Validation failed', fields: { code: 'This code is already used by another party.' } }; return supplierRecord(); });
    const { user, name, code, create, onCreated } = supplier();
    await user.type(name(), 'Sharma Traders');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
    await user.click(create());
    await waitFor(() => expect(code()).toHaveAccessibleDescription(/already used by another party/));
    expect(screen.queryByText('The supplier was not created')).toBeNull();
    expect(code()).toBeEnabled();
    await user.clear(code()); await user.type(code(), 'SHARMA-2');
    expect(code()).not.toHaveAccessibleDescription(/already used/);
    await user.click(create());
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(writes()).toHaveLength(2);
    expect(writes()[1]!.key).not.toBe(writes()[0]!.key);
    expect(writes()[1]!.body).toMatchObject({ code: 'SHARMA-2' });
  });

  it('finds the service’s field keys whether it prefixes them with the party or not', async () => {
    serve(() => { throw { status: 422, message: 'Validation failed', fields: { 'party.code': 'This code is not allowed.' } }; });
    const { user, name, code, create } = supplier();
    await user.type(name(), 'Sharma Traders');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
    await user.click(create());
    await waitFor(() => expect(code()).toHaveAccessibleDescription(/This code is not allowed/));
    // placed on its field, so not listed a second time above the form
    expect(screen.queryByText('The supplier was not created')).toBeNull();
  });

  it('says in a notice what it cannot place on a field, such as the payable account', async () => {
    serve(() => { throw { status: 422, message: 'Validation failed', fields: { 'ledger.group_id': 'No Sundry Creditors group is available.' } }; });
    const { user, name, create } = supplier();
    await user.type(name(), 'Sharma Traders');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
    await user.click(create());
    const notice = await screen.findByText('The supplier was not created');
    expect(notice.closest('[role]')).toHaveTextContent('No Sundry Creditors group is available.');
  });

  it('reports a refusal that is not about a field, and lets the person try again', async () => {
    let attempt = 0;
    serve(() => { attempt += 1; if (attempt === 1) throw { status: 403, message: 'You do not have permission to create suppliers.' }; return supplierRecord(); });
    const { user, name, create, onCreated } = supplier();
    await user.type(name(), 'Sharma Traders');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
    await user.click(create());
    expect(await screen.findByText('You do not have permission to create suppliers.')).toBeVisible();
    expect(screen.getByText('The supplier was not created')).toBeVisible();
    await user.click(create());
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
  });

  it('after a failure with no answer, locks the form and retries the very same request with the same key', async () => {
    let attempt = 0;
    serve(() => { attempt += 1; if (attempt === 1) throw { status: 503, message: 'Connection lost' }; return supplierRecord(); });
    const { user, name, code, create, onCreated } = supplier();
    await user.type(name(), 'Sharma Traders');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
    await user.click(create());
    expect(await screen.findByText('We could not confirm the result')).toBeVisible();
    expect(screen.getByText(/cannot be created twice/)).toBeVisible();
    expect(name()).toBeDisabled(); expect(code()).toBeDisabled();
    expect(onCreated).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(writes()).toHaveLength(2);
    expect(writes()[1]!.key).toBe(writes()[0]!.key);
    expect(writes()[1]!.body).toEqual(writes()[0]!.body);
  });

  it('does not take a reply that is not an active supplier of this company as success', async () => {
    let attempt = 0;
    serve(() => { attempt += 1; return attempt === 1 ? supplierRecord({ status: 'DRAFT' }) : supplierRecord({ company_id: id(2) }); });
    const { user, name, create, onCreated } = supplier();
    await user.type(name(), 'Sharma Traders');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
    await user.click(create());
    expect(await screen.findByText('We could not confirm the result')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(onCreated).not.toHaveBeenCalled();
    expect(screen.getByText('We could not confirm the result')).toBeVisible();
  });

  describe('closing', () => {
    it('closes at once when nothing has been typed', async () => {
      serve(() => supplierRecord());
      const { user, onClose } = supplier();
      await user.click(screen.getByRole('button', { name: 'Cancel' }));
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole('dialog', { name: 'Discard this new supplier?' })).toBeNull();
    });

    it.each([
      ['Escape', async (user: ReturnType<typeof userEvent.setup>) => { await user.keyboard('{Escape}'); }],
      ['the close button', async (user: ReturnType<typeof userEvent.setup>) => { await user.click(screen.getByRole('button', { name: 'Close' })); }],
      ['a click on the scrim', async () => { fireEvent.mouseDown(document.querySelector('.janso-drawer__scrim')!); }],
    ])('asks before throwing away what was typed, on %s', async (_how, close) => {
      serve(() => supplierRecord());
      const { user, name, onClose } = supplier();
      await user.type(name(), 'Sharma');
      await close(user);
      const ask = screen.getByRole('dialog', { name: 'Discard this new supplier?' });
      expect(onClose).not.toHaveBeenCalled();
      await user.click(within(ask).getByRole('button', { name: 'Keep editing' }));
      expect(onClose).not.toHaveBeenCalled();
      expect(name()).toHaveValue('Sharma');
      await close(user);
      await user.click(within(screen.getByRole('dialog', { name: 'Discard this new supplier?' })).getByRole('button', { name: 'Discard' }));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('will not close while the request is in flight', async () => {
      serve(() => new Promise(() => undefined));
      const { user, name, create, onClose } = supplier();
      await user.type(name(), 'Sharma Traders');
      await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
      await user.click(create());
      await screen.findByRole('button', { name: 'Creating supplier…' });
      await user.keyboard('{Escape}');
      fireEvent.mouseDown(document.querySelector('.janso-drawer__scrim')!);
      expect(onClose).not.toHaveBeenCalled();
      expect(screen.queryByRole('dialog', { name: /Discard/ })).toBeNull();
    });

    it('warns that it may already exist when the outcome is unknown, instead of the ordinary discard', async () => {
      serve(() => { throw { status: 503, message: 'Connection lost' }; });
      const { user, name, create, onClose } = supplier();
      await user.type(name(), 'Sharma Traders');
      await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
      await user.click(create());
      await screen.findByText('We could not confirm the result');
      await user.click(screen.getByRole('button', { name: 'Cancel' }));
      const ask = screen.getByRole('dialog', { name: 'Close without confirming the supplier?' });
      expect(within(ask).getByText(/may already have been created/)).toBeVisible();
      await user.click(within(ask).getByRole('button', { name: 'Close anyway' }));
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });
});

describe('SupplierQuickCreate: state and GST registration', () => {
  const GSTIN = '27ABCDE1234F1Z5';
  const gstStatus = () => screen.getByRole('combobox', { name: /GST registration/ });
  const gstin = () => screen.queryByRole('textbox', { name: /GSTIN/ });
  async function pickState(user: ReturnType<typeof userEvent.setup>, label = 'Maharashtra') {
    await user.click(screen.getByRole('combobox', { name: /State/ }));
    await user.click(await screen.findByRole('option', { name: new RegExp(label) }));
  }
  const filled = async (user: ReturnType<typeof userEvent.setup>, name: () => HTMLElement) => {
    await user.type(name(), 'Sharma Traders');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('India'));
  };

  it('offers GST status, state and GSTIN for an Indian supplier, starting on Regular', async () => {
    serve(() => supplierRecord());
    supplier({ canTax: true });
    expect(within(gstStatus()).getAllByRole('option').map(option => option.textContent)).toEqual(['Regular', 'Composition', 'Unregistered', 'Add later']);
    expect(gstStatus()).toHaveValue('REGULAR');
    expect(screen.getByRole('combobox', { name: /State/ })).toBeVisible();
    expect(gstin()).toBeVisible();
  });

  it('does not offer them to someone who may not record tax registrations', () => {
    serve(() => supplierRecord());
    supplier({ canTax: false });
    expect(screen.queryByRole('combobox', { name: /GST registration/ })).toBeNull();
    expect(screen.queryByRole('combobox', { name: /State/ })).toBeNull();
    expect(gstin()).toBeNull();
  });

  it('does not offer them for a supplier outside India', async () => {
    serve(() => supplierRecord());
    supplier({ canTax: true, companyCountry: 'US' });
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Country/ })).toHaveValue('United States'));
    expect(screen.queryByRole('combobox', { name: /GST registration/ })).toBeNull();
    expect(gstin()).toBeNull();
  });

  it('asks an unregistered supplier for the state only, and a supplier added later for nothing', async () => {
    serve(() => supplierRecord());
    const { user } = supplier({ canTax: true });
    await user.selectOptions(gstStatus(), 'UNREGISTERED');
    expect(screen.getByRole('combobox', { name: /State/ })).toBeVisible();
    expect(gstin()).toBeNull();
    await user.selectOptions(gstStatus(), 'NONE');
    expect(screen.queryByRole('combobox', { name: /State/ })).toBeNull();
    expect(gstin()).toBeNull();
  });

  it('requires the state and the GSTIN of a regular supplier, beside their fields, and sends nothing', async () => {
    serve(() => supplierRecord());
    const { user, name, create } = supplier({ canTax: true });
    await filled(user, name);
    await user.click(create());
    expect(writes()).toHaveLength(0);
    expect(gstin()).toHaveAccessibleDescription(/Enter the supplier’s GSTIN/);
    expect(screen.getByRole('combobox', { name: /State/ })).toHaveAccessibleDescription(/Choose the supplier’s state/);
  });

  it('cleans a typed GSTIN into capitals without spaces or hyphens', async () => {
    serve(() => supplierRecord());
    const { user } = supplier({ canTax: true });
    await user.type(gstin()!, '27abcde-1234 f1z5');
    expect(gstin()).toHaveValue(GSTIN);
  });

  it('creates the supplier with its GST registration in the same single request', async () => {
    serve(() => supplierRecord());
    const { user, name, create, onCreated } = supplier({ canTax: true });
    await filled(user, name);
    await pickState(user);
    await user.type(gstin()!, GSTIN);
    await user.click(create());
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(writes()).toHaveLength(1);
    expect(writes()[0]!.body).toEqual({
      code: 'SHARMA-TRADERS', name: 'Sharma Traders', legal_name: 'Sharma Traders', party_type: 'ORGANISATION', country_code: 'IN', role: 'SUPPLIER', ledger: {},
      tax_registration: { scheme: 'GST_IN', registration_type: 'REGULAR', country_code: 'IN', state_code: 'MH', registration_number: GSTIN },
    });
  });

  it('records an unregistered supplier by state, with no number', async () => {
    serve(() => supplierRecord());
    const { user, name, create, onCreated } = supplier({ canTax: true });
    await filled(user, name);
    await user.selectOptions(gstStatus(), 'UNREGISTERED');
    await pickState(user, 'Karnataka');
    await user.click(create());
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(writes()[0]!.body).toMatchObject({ tax_registration: { registration_type: 'UNREGISTERED', state_code: 'KA' } });
    expect((writes()[0]!.body as { tax_registration: object }).tax_registration).not.toHaveProperty('registration_number');
  });

  it('leaves the registration out when it is to be added later', async () => {
    serve(() => supplierRecord());
    const { user, name, create, onCreated } = supplier({ canTax: true });
    await filled(user, name);
    await user.selectOptions(gstStatus(), 'NONE');
    await user.click(create());
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(writes()[0]!.body).not.toHaveProperty('tax_registration');
  });

  it('puts a rejected GSTIN beside the GSTIN field, not in a notice', async () => {
    serve(() => { throw { status: 422, message: 'Validation failed', fields: { 'tax_registration.registration_number': 'invalid GST registration number' } }; });
    const { user, name, create } = supplier({ canTax: true });
    await filled(user, name);
    await pickState(user);
    await user.type(gstin()!, GSTIN);
    await user.click(create());
    await waitFor(() => expect(gstin()).toHaveAccessibleDescription(/invalid GST registration number/));
    expect(screen.queryByText('The supplier was not created')).toBeNull();
  });

  it('forgets the state when the country changes, so a state of one country is never sent for another', async () => {
    serve(() => supplierRecord());
    const { user, name, create } = supplier({ canTax: true });
    await filled(user, name);
    await pickState(user);
    expect(screen.getByRole('combobox', { name: /State/ })).toHaveValue('Maharashtra');
    await user.click(screen.getByRole('combobox', { name: /Country/ }));
    await user.click(await screen.findByRole('option', { name: /United States/ }));
    expect(screen.queryByRole('combobox', { name: /State/ })).toBeNull();
    await user.click(screen.getByRole('combobox', { name: /Country/ }));
    await user.click(await screen.findByRole('option', { name: /India/ }));
    expect(await screen.findByRole('combobox', { name: /State/ })).toHaveValue('');
    await user.click(create());
    expect(writes()).toHaveLength(0);
  });

  it('opens the full supplier form in a new tab, leaving the bill as it is', async () => {
    serve(() => supplierRecord());
    supplier();
    const link = screen.getByRole('link', { name: /Full supplier form/ });
    expect(link).toHaveAttribute('href', '/accounting/suppliers/new');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(link).toHaveAccessibleName(/opens in a new tab/);
  });
});

function account() {
  const onCreated = vi.fn(), onClose = vi.fn(), user = userEvent.setup();
  render(<ExpenseAccountQuickCreate company={company} onCreated={onCreated} onClose={onClose} />);
  const name = () => screen.getByRole('textbox', { name: /Account name/ });
  const code = () => screen.getByRole('textbox', { name: /Account code/ });
  const group = () => screen.getByRole('combobox', { name: /Account group/ });
  const create = () => screen.getByRole('button', { name: /^(Create account|Retry)$/ });
  return { onCreated, onClose, user, name, code, group, create };
}
const loaded = () => waitFor(() => expect(screen.getByRole('combobox', { name: /Account group/ })).toBeEnabled());

describe('ExpenseAccountQuickCreate', () => {
  it('opens as a dialog that says what it makes, with the cursor in the name', async () => {
    serve(() => accountRecord());
    const { name } = account();
    const dialog = screen.getByRole('dialog', { name: 'New expense account' });
    expect(within(dialog).getByText(/Creates an expense account you can post bills to/)).toBeVisible();
    expect(name()).toHaveFocus();
    await loaded();
  });

  it('opens the full account form in a new tab, leaving the bill as it is', async () => {
    serve(() => accountRecord());
    account();
    const link = screen.getByRole('link', { name: /Full account form/ });
    expect(link).toHaveAttribute('href', '/accounting/accounts/new');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    await loaded();
  });

  it('offers only groups under an expense head, and starts on Indirect Expenses', async () => {
    serve(() => accountRecord());
    const { group } = account();
    await loaded();
    expect(within(group()).getAllByRole('option').map(option => option.textContent)).toEqual(['Choose a group', 'Direct Expenses', 'Indirect Expenses']);
    expect(group()).toHaveValue(id(21));
  });

  it('leaves the group to the person when no group is the obvious one', async () => {
    serve(() => accountRecord(), [expenseGroups[0]!, { ...expenseGroups[1]!, name: 'Marketing' }]);
    const { group, user, name, create } = account();
    await loaded();
    expect(group()).toHaveValue('');
    await user.type(name(), 'Courier');
    await user.click(create());
    expect(writes()).toHaveLength(0);
    expect(group()).toHaveAccessibleDescription(/Choose the group/);
  });

  it('suggests the code from the name until it is written over', async () => {
    serve(() => accountRecord());
    const { user, name, code } = account();
    await loaded();
    await user.type(name(), 'Office rent');
    expect(code()).toHaveValue('OFFICE-RENT');
    await user.clear(code()); await user.type(code(), 'RENT01');
    await user.type(name(), ' 2');
    expect(code()).toHaveValue('RENT01');
  });

  it('creates a general, postable, non-stock account in one idempotent request and hands the record back', async () => {
    serve(() => accountRecord());
    const { user, name, create, onCreated } = account();
    await loaded();
    await user.type(name(), 'Office rent');
    await user.click(create());
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(onCreated).toHaveBeenCalledWith({ id: id(60), label: 'Office rent', meta: 'OFFICE-RENT' });
    expect(writes()).toHaveLength(1);
    expect(writes()[0]).toMatchObject({
      service: 'accounting', method: 'POST', path: `/v1/companies/${company}/accounts/create-active`,
      body: { code: 'OFFICE-RENT', name: 'Office rent', group_id: id(21), kind: 'GENERAL', currency_mode: 'BASE', posting_policy: 'MANUAL_ALLOWED', inventory_affected: false },
    });
    expect(writes()[0]!.body).not.toHaveProperty('description');
    expect(writes()[0]!.key).toMatch(/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);
  });

  it('sends the description when there is one', async () => {
    serve(() => accountRecord());
    const { user, name, create, onCreated } = account();
    await loaded();
    await user.type(name(), 'Office rent');
    await user.type(screen.getByRole('textbox', { name: /Description/ }), 'Head office, monthly');
    await user.click(create());
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(writes()[0]!.body).toMatchObject({ description: 'Head office, monthly' });
  });

  it('shows missing fields beside them and sends nothing', async () => {
    serve(() => accountRecord());
    const { user, name, code, create } = account();
    await loaded();
    await user.click(create());
    expect(writes()).toHaveLength(0);
    expect(name()).toHaveAccessibleDescription(/Enter the account name/);
    expect(code()).toHaveAccessibleDescription(/Enter an account code/);
    expect(name()).toHaveFocus();
  });

  it('cannot be submitted until the groups have loaded', async () => {
    let release!: (value: unknown) => void;
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (request.path.includes('/account-heads?')) return new Promise(resolve => { release = resolve; }) as never;
      if (request.path.endsWith('/account-heads/' + id(10))) return head as never;
      return page([]) as never;
    });
    const { group, create } = account();
    expect(group()).toBeDisabled();
    expect(within(group()).getByRole('option', { name: 'Loading groups…' })).toBeInTheDocument();
    expect(create()).toBeDisabled();
    release(page([{ id: head.id, company_id: company, name: head.name }]));
    await waitFor(() => expect(screen.getByText('No expense groups are available')).toBeVisible());
  });

  it('explains a company with no expense group, instead of offering a form that cannot work', async () => {
    serve(() => accountRecord(), [otherGroup]);
    const { create, group } = account();
    expect(await screen.findByText('No expense groups are available')).toBeVisible();
    expect(create()).toBeDisabled();
    expect(group()).toBeDisabled();
  });

  it('says when the groups could not be loaded, and loads them again on request', async () => {
    let fail = true;
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (fail) throw { status: 403, message: 'You do not have access to account groups.' };
      if (request.path.endsWith('/account-heads/' + id(10))) return head as never;
      return (request.path.includes('/account-heads?') ? page([{ id: head.id, company_id: company, name: head.name }]) : page(expenseGroups)) as never;
    });
    const { user, create } = account();
    const notice = await screen.findByText('Account groups could not be loaded');
    expect(notice.closest('[role]')).toHaveTextContent('You do not have access to account groups.');
    expect(create()).toBeDisabled();
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await loaded();
    expect(screen.queryByText('Account groups could not be loaded')).toBeNull();
  });

  it('puts a service rejection beside its field and keeps the form editable', async () => {
    serve(() => { throw { status: 422, message: 'Validation failed', fields: { code: 'This code is already used by another account.' } }; });
    const { user, name, code, create } = account();
    await loaded();
    await user.type(name(), 'Office rent');
    await user.click(create());
    await waitFor(() => expect(code()).toHaveAccessibleDescription(/already used by another account/));
    expect(code()).toBeEnabled();
    expect(screen.queryByText('The expense account was not created')).toBeNull();
  });

  it('retries an unanswered request with the same key and body, with the form locked', async () => {
    let attempt = 0;
    serve(() => { attempt += 1; if (attempt === 1) throw { status: 500, message: 'Internal error' }; return accountRecord(); });
    const { user, name, create, onCreated } = account();
    await loaded();
    await user.type(name(), 'Office rent');
    await user.click(create());
    expect(await screen.findByText('We could not confirm the result')).toBeVisible();
    expect(name()).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(writes()[1]!.key).toBe(writes()[0]!.key);
    expect(writes()[1]!.body).toEqual(writes()[0]!.body);
  });

  it.each([
    ['not active', { status: 'DRAFT' }],
    ['a party account', { kind: 'PARTY' }],
    ['stock-affecting', { inventory_affected: true }],
    ['source-only', { posting_policy: 'SOURCE_ONLY' }],
    ['in another group', { group_id: id(20) }],
    ['another company’s', { company_id: id(2) }],
  ])('does not take an account that is %s as the one it asked for', async (_what, patch) => {
    serve(() => accountRecord(patch));
    const { user, name, create, onCreated } = account();
    await loaded();
    await user.type(name(), 'Office rent');
    await user.click(create());
    expect(await screen.findByText('We could not confirm the result')).toBeVisible();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it('asks before discarding what was typed, and closes at once when nothing was', async () => {
    serve(() => accountRecord());
    const { user, name, onClose } = account();
    await loaded();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    onClose.mockClear();
    await user.type(name(), 'Office');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).not.toHaveBeenCalled();
    await user.click(within(screen.getByRole('dialog', { name: 'Discard this new expense account?' })).getByRole('button', { name: 'Discard' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
