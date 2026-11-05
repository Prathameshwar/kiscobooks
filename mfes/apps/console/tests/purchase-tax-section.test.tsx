import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PurchaseTaxSection, type TaxAccount } from '../app/components/PurchaseTaxSection';
import { blankPurchaseTax, defaultKey, resolvePurchaseTax, type AccountTaxDefault, type CompanyGst, type PurchaseTaxDraft, type PurchaseTaxFacts, type SupplierGst } from '../app/lib/purchase-tax';

vi.mock('../app/components/AccountingConfigurationCommon', () => ({
  AccountingReference: ({ label, value, onChange, error, hint, disabled }: { label: string; value: string | null; onChange: (value: string | null) => void; error?: string; hint?: string; disabled?: boolean }) =>
    <label>{label}<input aria-label={label} value={value ?? ''} disabled={disabled} onChange={event => onChange(event.target.value || null)} />{error ? <span role="alert">{error}</span> : null}{hint ? <small>{hint}</small> : null}</label>,
}));

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), supplier = id(3), account = id(7), second = id(8);
const mine: CompanyGst = { id: id(20), number: '27AAAAA0000A1Z5', state: 'IN-MH', primary: true, from: '2020-04-01', to: null };
const other: CompanyGst = { id: id(21), number: '29AAAAA0000A1Z5', state: 'IN-KA', primary: false, from: '2020-04-01', to: null };
const regular: SupplierGst = { id: id(30), type: 'REGULAR', state: 'IN-GJ', number: '24BBBBB1111B1Z6', from: '2019-07-01', to: null };
const sac = (patch: Partial<AccountTaxDefault> = {}): AccountTaxDefault => ({ id: id(40), account, code: '998399', codeSystem: 'SAC', supplyKind: 'SERVICE', treatment: 'TAXABLE', reverse: false, ...patch });
const accounts: TaxAccount[] = [{ id: account, label: 'Professional fees', lines: [1, 3] }, { id: second, label: 'Office rent', lines: [2] }];

type Setup = { tax?: Partial<PurchaseTaxDraft>; facts?: Partial<PurchaseTaxFacts>; failures?: { companies?: string; supplier?: string; defaults?: string }; loading?: boolean; editable?: boolean; locked?: boolean; showProblems?: boolean; canManage?: boolean; supplierId?: string; accounts?: TaxAccount[]; invoiceDate?: string };
function setup(options: Setup = {}) {
  const tax = { ...blankPurchaseTax(), choice: 'FORWARD' as const, ...options.tax };
  const facts: PurchaseTaxFacts = { companies: [mine], suppliers: new Map([[supplier, [regular]]]), defaults: new Map([[defaultKey(account, '2026-10-30'), sac()], [defaultKey(second, '2026-10-30'), null]]), ...options.facts };
  const resolution = resolvePurchaseTax({ tax, invoiceDate: options.invoiceDate ?? '2026-10-30', supplier: options.supplierId ?? supplier, facts });
  const onChange = vi.fn(), onReload = vi.fn();
  const view = render(<PurchaseTaxSection company={company} tax={tax} resolution={resolution} facts={facts} failures={options.failures ?? {}} loading={options.loading ?? false}
    accounts={options.accounts ?? accounts} supplierId={options.supplierId ?? supplier} editable={options.editable ?? true} locked={options.locked ?? false} showProblems={options.showProblems ?? false}
    canManage={options.canManage ?? false} onChange={onChange} onReload={onReload} />);
  return { ...view, onChange, onReload };
}

describe('the GST section of a Purchase bill', () => {
  it('is a labelled group that says Accounting, not the person, works the tax out', () => {
    setup();
    const group = screen.getByRole('group', { name: 'GST on this bill' });
    expect(within(group).getByText(/Accounting works out the GST from each expense account’s tax setup/)).toBeVisible();
  });

  describe('how the supplier charged it', () => {
    it('offers the two ways, names the chosen one, and says what it means', () => {
      setup();
      const select = screen.getByRole('combobox', { name: /How GST is charged/ }) as HTMLSelectElement;
      expect(within(select).getAllByRole('option').map(option => option.textContent)).toEqual(['Charged by the supplier', 'Reverse charge: you pay the GST']);
      expect(select.value).toBe('FORWARD');
      expect(select).toHaveAccessibleDescription(/you owe it to the supplier/);
    });
    it('reports a change to reverse charge, and shows what that means', () => {
      const view = setup({ tax: { choice: 'REVERSE' } });
      expect(screen.getByRole('combobox', { name: /How GST is charged/ })).toHaveValue('REVERSE');
      expect(screen.getByRole('combobox', { name: /How GST is charged/ })).toHaveAccessibleDescription(/not added to what you owe the supplier/);
      fireEvent.change(screen.getByRole('combobox', { name: /How GST is charged/ }), { target: { value: 'FORWARD' } });
      expect(view.onChange).toHaveBeenCalledWith({ choice: 'FORWARD' });
    });
  });

  describe('the company’s registration', () => {
    it('is stated, not asked, when the company has one in force', () => {
      setup();
      expect(screen.queryByRole('combobox', { name: /Your GST registration/ })).toBeNull();
      expect(screen.getByText('Your GST registration').closest('dl')).toHaveTextContent('27AAAAA0000A1Z5 · MH');
    });
    it('is a choice, with the primary one marked, when there are several', () => {
      const view = setup({ facts: { companies: [mine, other] } });
      const select = screen.getByRole('combobox', { name: /Your GST registration/ }) as HTMLSelectElement;
      expect(within(select).getAllByRole('option').map(option => option.textContent)).toEqual(['27AAAAA0000A1Z5 · MH · primary', '29AAAAA0000A1Z5 · KA']);
      expect(select.value).toBe(mine.id);
      fireEvent.change(select, { target: { value: other.id } });
      // A new registration brings its own state: the place of supply follows it again.
      expect(view.onChange).toHaveBeenCalledWith({ companyRegistration: other.id, placeOfSupply: '' });
    });
    it('asks the person to choose when the one they chose is no longer in force', () => {
      setup({ facts: { companies: [mine, other] }, tax: { companyRegistration: id(77) }, showProblems: true });
      expect(screen.getByRole('combobox', { name: /Your GST registration/ })).toHaveDisplayValue('Choose a registration');
      expect(screen.getByText('Choose the GST registration this bill is under.')).toBeVisible();
    });
    it('offers the one that is in force when the saved choice no longer is, rather than a dead end', () => {
      const view = setup({ tax: { companyRegistration: id(77) }, showProblems: true });
      const select = screen.getByRole('combobox', { name: /Your GST registration/ }) as HTMLSelectElement;
      expect(within(select).getAllByRole('option').map(option => option.textContent)).toEqual(['Choose a registration', '27AAAAA0000A1Z5 · MH · primary']);
      expect(screen.getByText('Choose the GST registration this bill is under.')).toBeVisible();
      fireEvent.change(select, { target: { value: mine.id } });
      expect(view.onChange).toHaveBeenCalledWith({ companyRegistration: mine.id, placeOfSupply: '' });
    });
    it('says so when the company has none in force, and while it is still being read', () => {
      const { unmount } = setup({ facts: { companies: [] }, showProblems: true });
      expect(screen.getByText('Your GST registration').closest('dl')).toHaveTextContent('None in force');
      expect(screen.getAllByRole('alert').map(node => node.textContent).join(' ')).toMatch(/no GST registration in force/);
      unmount();
      setup({ facts: { companies: null } });
      expect(screen.getByText('Your GST registration').closest('dl')).toHaveTextContent('Reading…');
    });
  });

  describe('place of supply and completion date', () => {
    it('follow the masters until the person chooses', () => {
      setup();
      expect(screen.getByRole('textbox', { name: /Place of supply/ })).toHaveValue('IN-MH');
      expect(screen.getByText('Follows your registration’s state until you choose another.')).toBeVisible();
      expect(screen.getByLabelText(/Service completion date/)).toHaveValue('2026-10-30');
      expect(screen.getByText('Follows the supplier invoice date until you choose another.')).toBeVisible();
    });
    it('show what the person chose, and stop saying they follow anything', () => {
      setup({ tax: { placeOfSupply: 'IN-KA', completionDate: '2026-10-02' } });
      expect(screen.getByRole('textbox', { name: /Place of supply/ })).toHaveValue('IN-KA');
      expect(screen.getByLabelText(/Service completion date/)).toHaveValue('2026-10-02');
      expect(screen.queryByText(/until you choose another/)).toBeNull();
    });
    it('report a choice, and clearing the place hands it back to the masters', () => {
      const view = setup();
      fireEvent.change(screen.getByRole('textbox', { name: /Place of supply/ }), { target: { value: 'IN-DL' } });
      expect(view.onChange).toHaveBeenLastCalledWith({ placeOfSupply: 'IN-DL' });
      fireEvent.change(screen.getByRole('textbox', { name: /Place of supply/ }), { target: { value: '' } });
      expect(view.onChange).toHaveBeenLastCalledWith({ placeOfSupply: '' });
      fireEvent.change(screen.getByLabelText(/Service completion date/), { target: { value: '2026-10-09' } });
      expect(view.onChange).toHaveBeenLastCalledWith({ completionDate: '2026-10-09' });
    });
    it('say what is wrong, but only once a save was refused', () => {
      const { unmount } = setup({ tax: { placeOfSupply: 'Maharashtra', completionDate: '2026-02-30' } });
      expect(screen.queryByText(/Choose the place of supply/)).toBeNull();
      unmount();
      setup({ tax: { placeOfSupply: 'Maharashtra', completionDate: '2026-02-30' }, showProblems: true });
      expect(screen.getByText(/Choose the place of supply/)).toBeVisible();
      expect(screen.getByText('Enter a valid service completion date.')).toBeVisible();
    });
  });

  describe('the supplier’s registration', () => {
    const none = (facts: Partial<PurchaseTaxFacts>, extra: Setup = {}) => setup({ facts: { suppliers: new Map(), ...facts }, ...extra });
    it('is read from the supplier’s tax registrations and shown with its type', () => {
      setup();
      const dl = screen.getByText('Supplier’s GST registration').closest('dl')!;
      expect(dl).toHaveTextContent('24BBBBB1111B1Z6 · GJ');
      expect(dl).toHaveTextContent('Regular registration, read from the supplier’s tax registrations.');
      expect(screen.queryByText(/can only be recorded for a regular/)).toBeNull();
    });
    it('waits for a supplier, then for the read', () => {
      const { unmount } = setup({ supplierId: '' });
      expect(screen.getByText('Supplier’s GST registration').closest('dl')).toHaveTextContent('Choose the supplier first');
      unmount();
      none({});
      expect(screen.getByText('Supplier’s GST registration').closest('dl')).toHaveTextContent('Reading…');
    });
    it('says it could not be read, and reads again on request', () => {
      const view = none({}, { failures: { supplier: 'The supplier’s GST registrations could not be verified.' } });
      expect(screen.getByText('Supplier’s GST registration').closest('dl')).toHaveTextContent('Could not be read');
      expect(screen.getByText('Tax details could not be read')).toBeVisible();
      fireEvent.click(screen.getByRole('button', { name: 'Read the tax details again' }));
      expect(view.onReload).toHaveBeenCalledTimes(1);
    });
    it('explains a supplier with no GST registration, and links to where it is added only for someone who may', () => {
      const { unmount } = none({ suppliers: new Map([[supplier, []]]) });
      expect(screen.getByText('The supplier has no GST registration on record')).toBeVisible();
      expect(screen.queryByRole('link', { name: /supplier’s tax registrations/ })).toBeNull();
      unmount();
      const view = none({ suppliers: new Map([[supplier, []]]) }, { canManage: true });
      const link = screen.getByRole('link', { name: /Open the supplier’s tax registrations/ });
      expect(link).toHaveAttribute('href', '/accounting/party-tax-registrations/new?party_id=' + supplier);
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
      expect(link).toHaveTextContent('(opens in a new tab)');
      fireEvent.click(screen.getByRole('button', { name: 'Read the tax details again' }));
      expect(view.onReload).toHaveBeenCalled();
    });
    it.each([['COMPOSITION', 'composition'], ['UNREGISTERED', 'unregistered']])('says a %s supplier cannot be taxed here', (type, word) => {
      none({ suppliers: new Map([[supplier, [{ ...regular, type }]]]) });
      expect(screen.getByText('GST can only be recorded for a regular GST supplier')).toBeVisible();
      expect(screen.getByText(new RegExp('this one is ' + word))).toBeVisible();
    });
    it('stays a choice after one is picked, so the person can pick another', () => {
      const secondRegistration: SupplierGst = { ...regular, id: id(31), state: 'IN-KA', number: '29BBBBB1111B1Z6' };
      const view = none({ suppliers: new Map([[supplier, [regular, secondRegistration]]]) }, { tax: { supplierRegistration: secondRegistration.id } });
      const select = screen.getByRole('combobox', { name: /Supplier’s GST registration/ }) as HTMLSelectElement;
      expect(select.value).toBe(secondRegistration.id);
      expect(within(select).getAllByRole('option').map(option => option.textContent)).toEqual(['24BBBBB1111B1Z6 · GJ', '29BBBBB1111B1Z6 · KA']);
      fireEvent.change(select, { target: { value: regular.id } });
      expect(view.onChange).toHaveBeenCalledWith({ supplierRegistration: regular.id });
    });
    it('is a choice when the supplier has several regular registrations, and reports it', () => {
      const secondRegistration: SupplierGst = { ...regular, id: id(31), state: 'IN-KA', number: '29BBBBB1111B1Z6' };
      const view = none({ suppliers: new Map([[supplier, [regular, secondRegistration]]]) }, { showProblems: true });
      const select = screen.getByRole('combobox', { name: /Supplier’s GST registration/ });
      expect(within(select).getAllByRole('option').map(option => option.textContent)).toEqual(['Choose the one on the invoice', '24BBBBB1111B1Z6 · GJ', '29BBBBB1111B1Z6 · KA']);
      expect(screen.getByText('This supplier has more than one regular GST registration. Choose the one on the invoice.')).toBeVisible();
      fireEvent.change(select, { target: { value: secondRegistration.id } });
      expect(view.onChange).toHaveBeenCalledWith({ supplierRegistration: secondRegistration.id });
    });
  });

  describe('tax by expense account', () => {
    it('lists each account once with its lines, and what its tax setup says', () => {
      setup();
      const list = screen.getByRole('list');
      const [first, secondRow] = within(list).getAllByRole('listitem');
      expect(first).toHaveTextContent('Professional fees');
      expect(first).toHaveTextContent('Lines 1, 3');
      expect(first).toHaveTextContent('SAC 998399 · Taxable');
      expect(first).toHaveAttribute('data-tone', 'ok');
      expect(secondRow).toHaveTextContent('Office rent');
      expect(secondRow).toHaveTextContent('Line 2');
      expect(secondRow).toHaveTextContent('no purchase tax default');
      expect(secondRow).toHaveAttribute('data-tone', 'bad');
    });
    it('offers to set a missing tax default only to someone who may manage tax masters', () => {
      const { unmount } = setup();
      expect(screen.queryByRole('link', { name: /Set its tax default/ })).toBeNull();
      unmount();
      setup({ canManage: true });
      const link = screen.getByRole('link', { name: /Set its tax default/ });
      expect(link).toHaveAttribute('href', '/accounting/account-tax-defaults/new?account_id=' + second);
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });
    it('says the account disagrees with the bill about reverse charge', () => {
      setup({ tax: { choice: 'REVERSE' } });
      expect(screen.getAllByRole('listitem')[0]).toHaveTextContent(/not set to reverse charge/);
    });
    it('shows an account whose tax default has not been read as still being read', () => {
      setup({ facts: { defaults: new Map() } });
      expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('Reading the account’s tax default…');
      expect(screen.getAllByRole('listitem')[0]).toHaveAttribute('data-tone', 'pending');
    });
    it('is left out when the bill has no expense account yet', () => {
      setup({ accounts: [] });
      expect(screen.queryByRole('region', { name: 'Tax by expense account' })).toBeNull();
      expect(screen.queryByRole('list')).toBeNull();
    });
  });

  describe('reading the tax setup', () => {
    it('says it is reading while it is', () => {
      setup({ loading: true });
      expect(screen.getByRole('status')).toHaveTextContent('Reading the tax setup…');
      expect(screen.getByText('Reading the tax setup…')).toBeVisible();
    });
    it('says nothing about reading once it has failed, and offers to read again', () => {
      const view = setup({ loading: true, failures: { defaults: 'This account has overlapping tax defaults on that date. Review them in Masters.' } });
      expect(screen.queryByText('Reading the tax setup…')).toBeNull();
      expect(screen.getByText(/overlapping tax defaults/)).toBeVisible();
      fireEvent.click(screen.getByRole('button', { name: 'Read the tax details again' }));
      expect(view.onReload).toHaveBeenCalledTimes(1);
    });
  });

  describe('who can change it', () => {
    it('is read-only for a reader and while the bill is busy', () => {
      const { unmount } = setup({ editable: false });
      for (const name of [/How GST is charged/, /Place of supply/, /Service completion date/]) expect(screen.getByLabelText(name)).toBeDisabled();
      unmount();
      setup({ locked: true, facts: { companies: [mine, other] } });
      for (const name of [/How GST is charged/, /Your GST registration/, /Place of supply/, /Service completion date/]) expect(screen.getByLabelText(name)).toBeDisabled();
    });
    it('keeps “read again” available to a reader, but not while the bill is busy', () => {
      const { unmount } = setup({ editable: false, failures: { companies: 'x' } });
      expect(screen.getByRole('button', { name: 'Read the tax details again' })).toBeEnabled();
      unmount();
      setup({ locked: true, failures: { companies: 'x' } });
      expect(screen.getByRole('button', { name: 'Read the tax details again' })).toBeDisabled();
    });
  });

  it('has no unlabelled control', () => {
    setup({ canManage: true, facts: { companies: [mine, other], suppliers: new Map([[supplier, [regular, { ...regular, id: id(31) }]]]) } });
    for (const control of [...screen.getAllByRole('combobox'), ...screen.getAllByRole('textbox'), ...screen.getAllByRole('link'), ...screen.queryAllByRole('button')])
      expect(control, control.outerHTML).toHaveAccessibleName();
  });
});
