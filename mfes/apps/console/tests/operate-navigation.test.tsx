import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { OperateLanding } from '../app/components/OperateLanding';
import { OperateFamilyPage } from '../app/components/OperateFamily';
import { OPERATE_AREAS, areaHref, familyHref, listHref, operateReturn, withReturn } from '../app/lib/operate-navigation';
import { VOUCHER_KINDS } from '../app/lib/voucher-kinds';
import { navigationFor, sidebarCurrentHref } from '../app/nav';
import { serviceCall } from '../app/lib/service-call';
import { sessionFor } from './helpers';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const company = '10000000-0000-7000-8000-000000000001', typeId = '10000000-0000-7000-8000-000000000002';
const expense = OPERATE_AREAS[1], purchase = expense.families[0];
const page = { items: [], page: { limit: 25, has_more: false, next_cursor: null } };
beforeEach(() => { vi.mocked(serviceCall).mockReset(); vi.mocked(serviceCall).mockResolvedValue(page); });

it('covers all 22 voucher kinds with list destinations', () => {
  const seen = new Set<string>();
  for (const area of OPERATE_AREAS) for (const family of area.families) for (const kind of family.kinds) {
    seen.add(kind);
    const href = listHref(area, family, kind);
    expect(operateReturn(href)).toBe(href);
    expect(operateReturn(listHref(area, family, kind, typeId))).toBe(listHref(area, family, kind, typeId));
  }
  expect([...seen].sort()).toEqual(VOUCHER_KINDS.map(kind => kind.value).sort());
});
it.each(['https://evil.invalid', '//evil.invalid/operate/income', '/operate/expense/unknown', '/operate/expense/purchase/sales', '/operate/expense/purchase/', '/operate/income#bad', '/operate/income?returnTo=https://evil.invalid', '/operate/income/%2e%2e/expense', '/operate/expense/purchase/purchase?type_id=no', '/operate/expense/purchase/purchase?type_id=' + typeId + '&type_id=' + typeId])('rejects unsafe or inconsistent return %s', value => {
  expect(operateReturn(value)).toBeUndefined();
  expect(withReturn('/vouchers', value)).toBe('/vouchers');
});
it('places the new menus after overview and applies company-scoped permissions', async () => {
  const session = await sessionFor({ permissions: ['vouchers.read'] });
  session.company = { id: company, name: 'Company' };
  session.grants = [{ scope_type: 'company', scope_id: company, permissions: ['vouchers.read'], valid_from: '2000-01-01', valid_to: null }];
  const items = navigationFor(session).find(section => section.label === 'Operate')!.items;
  expect(items.map(item => item.label)).toEqual(['Business overview', 'Income', 'Expense', 'Inventory', 'Voucher drafts']);
  expect(sidebarCurrentHref(items, listHref(expense, purchase, 'PURCHASE'))).toBe(areaHref(expense));
  session.grants[0].scope_id = typeId;
  expect(navigationFor(session).flatMap(section => section.items).filter(item => item.href.startsWith('/operate/'))).toEqual([]);
  session.company = { name: 'Select company' };
  expect(navigationFor(session).flatMap(section => section.items).filter(item => item.href.startsWith('/operate/'))).toEqual([]);
});
it.each(OPERATE_AREAS)('renders $title landing cards and searches related kinds', async area => {
  render(<OperateLanding area={area} />);
  expect(screen.getByRole('heading', { name: area.title })).toBeInTheDocument();
  for (const family of area.families) expect(screen.getByRole('link', { name: new RegExp('^' + family.title) })).toHaveAttribute('href', familyHref(area, family));
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'never-matches' } });
  fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  await screen.findByText(/No workflows match/);
  fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
  await waitFor(() => expect(screen.queryByText(/No workflows match/)).not.toBeInTheDocument());
});
it('shows purchase, return, note and print links with verified configured type cards', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_proxy, request) => {
    const kind = new URL(request.path, 'https://console.invalid').searchParams.get('kind');
    return kind === 'PURCHASE' ? { ...page, items: [{ id: typeId, company_id: company, kind, status: 'ACTIVE', name: 'Local supplier bills', code: 'LP' }] } : page;
  });
  render(<OperateFamilyPage company={company} area={expense} family={purchase} canPrint canManageTypes />);
  expect(await screen.findByRole('link', { name: /Local supplier bills/ })).toHaveAttribute('href', listHref(expense, purchase, 'PURCHASE', typeId));
  const notes = within(screen.getByRole('region', { name: 'Purchase returns / debit notes' }));
  expect(notes.getByRole('link', { name: /Purchase returns/ })).toHaveAttribute('href', listHref(expense, purchase, 'DEBIT_NOTE'));
  expect(screen.getByRole('link', { name: /Purchase print config/ })).toHaveAttribute('href', withReturn('/documents/vouchers/purchase', familyHref(expense, purchase)));
  expect(vi.mocked(serviceCall).mock.calls.every(call => new URL(call[1].path, 'https://console.invalid').searchParams.get('status') === 'ACTIVE')).toBe(true);
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'LP' } });
  fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  await waitFor(() => expect(screen.queryByRole('link', { name: /^Purchase Browse/ })).not.toBeInTheDocument());
  expect(screen.getByRole('link', { name: /Local supplier bills/ })).toBeInTheDocument();
});
it('withholds print and management links without their permissions', async () => {
  render(<OperateFamilyPage company={company} area={expense} family={purchase} canPrint={false} canManageTypes={false} />);
  expect(screen.queryByRole('region', { name: 'Print configuration' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Manage voucher types' })).not.toBeInTheDocument();
  await waitFor(() => expect(screen.queryAllByText(/^Loading /)).toHaveLength(0));
});
it.each(['Purchase print config'])('finds the card by its displayed title: %s', async title => {
  render(<OperateFamilyPage company={company} area={expense} family={purchase} canPrint canManageTypes={false} />);
  await waitFor(() => expect(screen.queryAllByText(/^Loading /)).toHaveLength(0));
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: title } });
  fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  await waitFor(() => expect(screen.getByRole('link', { name: new RegExp('^' + title) })).toBeInTheDocument());
  expect(screen.queryByText(/No cards match your search/)).not.toBeInTheDocument();
});
it('shows specific Purchase types without generic purchase voucher cards', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_proxy, request) => {
    const kind = new URL(request.path, 'https://console.invalid').searchParams.get('kind');
    return kind !== 'PURCHASE' ? page : { ...page, items: [
      { id: typeId, company_id: company, kind, status: 'ACTIVE', name: 'Purchase voucher', code: 'PURCHASE' },
      { id: company, company_id: company, kind, status: 'ACTIVE', name: 'Purchase - Account Bill', code: 'P-ACCOUNT' },
      { id: '10000000-0000-7000-8000-000000000003', company_id: company, kind, status: 'ACTIVE', name: 'Purchase - Mixed bill', code: 'P-MIXED' },
    ] };
  });
  render(<OperateFamilyPage company={company} area={expense} family={purchase} canPrint canManageTypes={false} />);
  const mixed = await screen.findByRole('link', { name: 'Purchase - Goods & Services Bill' });
  expect(mixed).toHaveAttribute('href', listHref(expense, purchase, 'PURCHASE', '10000000-0000-7000-8000-000000000003'));
  expect(screen.getByRole('link', { name: 'Purchase - Account Bill' })).toHaveAttribute('href', listHref(expense, purchase, 'PURCHASE', company));
  expect(screen.queryByRole('link', { name: /^All Purchase vouchers?$/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /^Purchase vouchers?$/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Purchase - Mixed bill' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Purchase print config' })).toBeInTheDocument();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Purchase - Goods & Services Bill' } });
  fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  await waitFor(() => expect(screen.queryByRole('link', { name: 'Purchase - Account Bill' })).not.toBeInTheDocument());
  expect(screen.getByRole('link', { name: 'Purchase - Goods & Services Bill' })).toBeInTheDocument();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Purchase - Mixed bill' } });
  fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  await waitFor(() => expect(screen.getByRole('link', { name: 'Purchase - Goods & Services Bill' })).toBeInTheDocument());
});
it('groups sole return, credit and receipt types into one card grid', async () => {
  const related = [{ kind: 'DEBIT_NOTE', name: 'Debit Note' }, { kind: 'CREDIT_NOTE', name: 'Credit Note' }, { kind: 'RECEIPT_NOTE', name: 'Receipt Note' }];
  vi.mocked(serviceCall).mockImplementation(async (_proxy, request) => {
    const kind = new URL(request.path, 'https://console.invalid').searchParams.get('kind');
    const row = related.find(row => row.kind === kind);
    return row ? { ...page, items: [{ ...row, id: typeId, company_id: company, status: 'ACTIVE', code: row.kind }] } : page;
  });
  render(<OperateFamilyPage company={company} area={expense} family={purchase} canPrint canManageTypes={false} />);
  const group = within(await screen.findByRole('region', { name: 'Returns, Notes & Receipts' }));
  for (const row of related) expect(await group.findByRole('link', { name: row.name })).toHaveAttribute('href', listHref(expense, purchase, row.kind, typeId));
  expect(group.getAllByRole('link')).toHaveLength(3);
  expect(screen.queryByRole('region', { name: 'Purchase returns / debit notes' })).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Supplier credit notes' })).not.toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Purchase order' })).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Print configuration' })).toBeInTheDocument();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Receipt Note' } }); fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  await waitFor(() => expect(group.queryByRole('link', { name: 'Debit Note' })).not.toBeInTheDocument());
  expect(group.getAllByRole('link')).toHaveLength(1);
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Returns, Notes & Receipts' } }); fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  await waitFor(() => expect(group.getAllByRole('link')).toHaveLength(3));
  expect(screen.queryByText(/No cards match/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'no-card-match' } }); fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  await screen.findByText(/No cards match your search/);
  expect(screen.queryByRole('region', { name: 'Returns, Notes & Receipts' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
  await waitFor(() => expect(group.getAllByRole('link')).toHaveLength(3));
});
it.each([false, true])('keeps related types in their own section when multiple types or more pages exist: %s', async more => {
  vi.mocked(serviceCall).mockImplementation(async (_proxy, request) => {
    const query = new URL(request.path, 'https://console.invalid').searchParams;
    const kind = query.get('kind');
    if (kind === 'DEBIT_NOTE' && query.has('cursor')) return { ...page, items: [{ id: typeId, company_id: company, kind, status: 'ACTIVE', name: 'Last return' }] };
    if (kind === 'DEBIT_NOTE') return { ...page, page: { ...page.page, has_more: more, next_cursor: more ? 'next-types' : null }, items: Array.from({ length: more ? 1 : 2 }, (_, index) => ({ id: index ? company : typeId, company_id: company, kind, status: 'ACTIVE', name: 'Return ' + index })) };
    return kind === 'CREDIT_NOTE' ? { ...page, items: [{ id: typeId, company_id: company, kind, status: 'ACTIVE', name: 'Credit Note' }] } : page;
  });
  render(<OperateFamilyPage company={company} area={expense} family={purchase} canPrint={false} canManageTypes={false} />);
  await waitFor(() => expect(screen.queryAllByText(/^Loading /)).toHaveLength(0));
  const notes = within(screen.getByRole('region', { name: 'Purchase returns / debit notes' }));
  expect(notes.getByRole('link', { name: /^All / })).toHaveAttribute('href', listHref(expense, purchase, 'DEBIT_NOTE'));
  expect(notes.getByRole('link', { name: 'Return 0' })).toBeInTheDocument();
  const group = within(screen.getByRole('region', { name: 'Returns, Notes & Receipts' }));
  expect(group.getByRole('link', { name: 'Credit Note' })).toBeInTheDocument();
  expect(group.queryByRole('link', { name: 'Return 0' })).not.toBeInTheDocument();
  if (more) {
    fireEvent.click(notes.getByRole('button', { name: /next/i }));
    expect(await notes.findByRole('link', { name: 'Last return' })).toHaveAttribute('href', listHref(expense, purchase, 'DEBIT_NOTE', typeId));
    expect(notes.getByRole('link', { name: /^All / })).toBeInTheDocument();
    expect(group.queryByRole('link', { name: 'Last return' })).not.toBeInTheDocument();
  }
});
it.each([
  { kind: 'DEBIT_NOTE', label: 'Purchase returns / debit notes', name: 'Debit Note' },
  { kind: 'CREDIT_NOTE', label: 'Supplier credit notes', name: 'Credit Note' },
])('omits the redundant All card when $name is the only configured type', async ({ kind, label, name }) => {
  vi.mocked(serviceCall).mockImplementation(async (_proxy, request) => new URL(request.path, 'https://console.invalid').searchParams.get('kind') === kind
    ? { ...page, items: [{ id: typeId, company_id: company, kind, status: 'ACTIVE', name, code: kind }] } : page);
  render(<OperateFamilyPage company={company} area={expense} family={purchase} canPrint canManageTypes={false} />);
  const region = within(await screen.findByRole('region', { name: 'Returns, Notes & Receipts' }));
  expect(await region.findByRole('link', { name })).toHaveAttribute('href', listHref(expense, purchase, kind, typeId));
  expect(region.queryByRole('link', { name: /^All / })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: label + ' print config' })).toBeInTheDocument();
  if (kind === 'DEBIT_NOTE') expect(region.getByText(/product and account details/i)).toBeInTheDocument();
});
it.each([
  { count: 0, more: false }, { count: 2, more: false }, { count: 1, more: true },
])('keeps All when type count is $count and more pages is $more', async ({ count, more }) => {
  vi.mocked(serviceCall).mockImplementation(async (_proxy, request) => {
    const kind = new URL(request.path, 'https://console.invalid').searchParams.get('kind');
    return kind === 'DEBIT_NOTE' ? { ...page, page: { ...page.page, has_more: more, next_cursor: more ? 'next-types' : null }, items: Array.from({ length: count }, (_, index) => ({ id: index ? company : typeId, company_id: company, kind, status: 'ACTIVE', name: 'Return ' + index, code: 'RETURN' + index })) } : page;
  });
  render(<OperateFamilyPage company={company} area={expense} family={purchase} canPrint={false} canManageTypes={false} />);
  await waitFor(() => expect(screen.queryAllByText(/^Loading /)).toHaveLength(0));
  const region = within(screen.getByRole('region', { name: 'Purchase returns / debit notes' }));
  expect(region.getByRole('link', { name: /^All / })).toHaveAttribute('href', listHref(expense, purchase, 'DEBIT_NOTE'));
});
it('refuses foreign configured types, reports a failure and retries', async () => {
  vi.mocked(serviceCall).mockResolvedValue({ ...page, items: [{ id: typeId, company_id: typeId, kind: 'PURCHASE', status: 'ACTIVE', name: 'Foreign type' }] });
  render(<OperateFamilyPage company={company} area={expense} family={purchase} canPrint={false} canManageTypes={false} />);
  await screen.findAllByText(/response did not match this company/);
  expect(screen.queryByRole('link', { name: /Foreign type/ })).not.toBeInTheDocument();
  vi.mocked(serviceCall).mockResolvedValue(page);
  fireEvent.click(screen.getByRole('button', { name: 'Retry purchase types' }));
  await waitFor(() => expect(within(screen.getByRole('region', { name: 'Purchase' })).queryByText(/response did not match/)).not.toBeInTheDocument());
});
it('shows a clear empty search result and restores the cards', async () => {
  render(<OperateFamilyPage company={company} area={expense} family={purchase} canPrint canManageTypes={false} />);
  await waitFor(() => expect(screen.queryAllByText(/^Loading /)).toHaveLength(0));
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'no-card-match' } }); fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  await screen.findByText(/No cards match your search/);
  expect(screen.queryByRole('region', { name: 'Purchase' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
  await screen.findByRole('region', { name: 'Purchase' });
});
it('pages configured types without hiding an incomplete search result', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_proxy, request) => {
    const query = new URL(request.path, 'https://console.invalid').searchParams;
    return query.get('kind') !== 'PURCHASE' ? page : query.has('cursor')
      ? { ...page, items: [{ id: typeId, company_id: company, kind: 'PURCHASE', status: 'ACTIVE', name: 'Second-page bills', code: 'P2' }] }
      : { ...page, page: { ...page.page, has_more: true, next_cursor: 'signed-types-next' } };
  });
  render(<OperateFamilyPage company={company} area={expense} family={purchase} canPrint={false} canManageTypes={false} />);
  await screen.findByText(/Browse other pages for more types/);
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Second-page' } }); fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  const region = screen.getByRole('region', { name: 'Purchase' });
  await waitFor(() => expect(within(region).getByRole('button', { name: /next/i })).toBeEnabled());
  fireEvent.click(within(region).getByRole('button', { name: /next/i }));
  expect(await screen.findByRole('link', { name: 'Second-page bills' })).toHaveAttribute('href', listHref(expense, purchase, 'PURCHASE', typeId));
  fireEvent.click(within(region).getByRole('button', { name: /previous/i }));
  await waitFor(() => expect(screen.queryByRole('link', { name: 'Second-page bills' })).not.toBeInTheDocument());
});
it('clarifies Sales card headings, invoice names and workflow descriptions without changing destinations', async () => {
  const income = OPERATE_AREAS[0], sales = income.families[0];
  const rows = [
    { kind: 'SALES', name: 'Sales - Mixed Invoice', profile: 'STANDARD', code: 'SAL_MIX' },
    { kind: 'SALES', name: 'Sales - Product Invoice', profile: 'STANDARD', code: 'SAL_PRD' },
    { kind: 'SALES', name: 'Sales - Account Invoice', profile: 'STANDARD', code: 'SAL_ACC' },
    { kind: 'SALES', name: 'Pro Forma Invoice', profile: 'PRO_FORMA', code: 'PROFORMA' },
    { kind: 'CREDIT_NOTE', name: 'Credit Note', profile: 'STANDARD', code: 'CRN' },
    { kind: 'SALES_ORDER', name: 'Quotation', profile: 'QUOTATION', code: 'QUOTE' },
    { kind: 'SALES_ORDER', name: 'Sales Order', profile: 'STANDARD', code: 'SO' },
    { kind: 'DELIVERY_NOTE', name: 'Delivery Note', profile: 'STANDARD', code: 'DN' },
    { kind: 'DELIVERY_NOTE', name: 'Delivery Challan', profile: 'DELIVERY_CHALLAN', code: 'DC' },
  ].map((row, index) => ({ ...row, id: `10000000-0000-7000-8000-${String(index + 10).padStart(12, '0')}`, company_id: company, status: 'ACTIVE' }));
  vi.mocked(serviceCall).mockImplementation(async (_proxy, request) => ({ ...page, items: rows.filter(row => row.kind === new URL(request.path, 'https://console.invalid').searchParams.get('kind')) }));
  render(<OperateFamilyPage company={company} area={income} family={sales} canPrint canManageTypes={false} />);
  const invoices = within(await screen.findByRole('region', { name: 'Sales invoices' }));
  const mixed = await invoices.findByRole('link', { name: 'Sales - Product & Account Invoice' });
  expect(mixed).toHaveAttribute('href', listHref(income, sales, 'SALES', rows[0].id));
  expect(invoices.getByRole('link', { name: 'All Sales Invoices' })).toHaveAttribute('href', listHref(income, sales, 'SALES'));
  expect(invoices.queryByRole('link', { name: 'Sales - Mixed Invoice' })).not.toBeInTheDocument();
  expect(invoices.getByText(/preliminary customer invoices/i)).toBeInTheDocument();
  expect(invoices.getByText(/item and account details/i)).toBeInTheDocument();
  expect(invoices.getByText(/customer invoices for goods and services/i)).toBeInTheDocument();
  expect(invoices.getByText(/account-based customer invoices/i)).toBeInTheDocument();
  const returns = within(screen.getByRole('region', { name: 'Customer returns & credits' }));
  expect(returns.getByRole('link', { name: 'Credit Note' })).toHaveAttribute('href', listHref(income, sales, 'CREDIT_NOTE', rows[4].id));
  expect(returns.queryByRole('link', { name: /^All / })).not.toBeInTheDocument();
  expect(returns.getByText(/customer returns and credit adjustments/i)).toBeInTheDocument();
  expect(returns.getByText('Customer returns, credit notes and invoice adjustments.')).toBeInTheDocument();
  expect(returns.queryByText(/supplier credit/i)).not.toBeInTheDocument();
  expect(within(screen.getByRole('region', { name: 'Orders & quotations' })).getByText(/price quotations before/i)).toBeInTheDocument();
  expect(within(screen.getByRole('region', { name: 'Delivery notes & challans' })).getAllByText(/goods dispatched to customers/i)).toHaveLength(2);
  expect(screen.getByRole('link', { name: 'Sales print config' })).toBeInTheDocument();
  for (const query of ['Sales - Product & Account Invoice', 'Sales - Mixed Invoice', 'SAL_MIX', 'item and account details']) {
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: query } }); fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
    await waitFor(() => expect(screen.queryByRole('link', { name: 'Sales - Product Invoice' })).not.toBeInTheDocument());
    expect(screen.getByRole('link', { name: 'Sales - Product & Account Invoice' })).toBeInTheDocument();
    expect(screen.queryByText(/No cards match/)).not.toBeInTheDocument();
  }
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'All Sales vouchers' } }); fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  expect(await screen.findByRole('link', { name: 'All Sales Invoices' })).toBeInTheDocument();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'preliminary customer invoices' } }); fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  await waitFor(() => expect(screen.queryByRole('link', { name: 'Sales - Product & Account Invoice' })).not.toBeInTheDocument());
  expect(invoices.getByRole('link', { name: 'Pro Forma Invoice' })).toHaveAttribute('href', listHref(income, sales, 'SALES', rows[3].id));
  expect(invoices.getAllByRole('link')).toHaveLength(1);
});
it.each([
  { name: 'Sales - Mixed Invoice', profile: undefined, title: 'Sales - Product & Account Invoice' },
  { name: 'Wholesale Invoice', profile: 'STANDARD', title: 'Wholesale Invoice' },
  { name: 'Sales - Mixed Invoice', profile: 'PRO_FORMA', title: 'Sales - Mixed Invoice' },
])('preserves custom Sales names and profiles while supporting legacy captions: $title', async ({ name, profile, title }) => {
  const income = OPERATE_AREAS[0], sales = income.families[0];
  vi.mocked(serviceCall).mockImplementation(async (_proxy, request) => new URL(request.path, 'https://console.invalid').searchParams.get('kind') === 'SALES'
    ? { ...page, items: [{ id: typeId, company_id: company, kind: 'SALES', status: 'ACTIVE', name, profile, code: 'CUSTOM' }] } : page);
  render(<OperateFamilyPage company={company} area={income} family={sales} canPrint={false} canManageTypes={false} />);
  expect(await screen.findByRole('link', { name: title })).toHaveAttribute('href', listHref(income, sales, 'SALES', typeId));
  expect(screen.queryByRole('link', { name: 'All Sales Invoices' })).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Print configuration' })).not.toBeInTheDocument();
  if (profile === 'PRO_FORMA') expect(screen.getByText(/preliminary customer invoices/i)).toBeInTheDocument();
});
it('accepts only canonical bounded local return destinations', () => {
  expect(operateReturn('/operate/income/../expense/purchase')).toBeUndefined();
  expect(operateReturn('/operate/income' + 'a'.repeat(501))).toBeUndefined();
  expect(operateReturn(undefined)).toBeUndefined();
  expect(operateReturn('/operate/income')).toBe('/operate/income');
  expect(operateReturn('/operate/expense/purchase')).toBe('/operate/expense/purchase');
  expect(operateReturn('/operate/expense/purchase/purchase?type_id=' + typeId + '&bad=true')).toBeUndefined();
});
