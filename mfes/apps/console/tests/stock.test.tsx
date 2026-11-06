import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { StockDirectory } from '../app/components/StockDirectory';
import { StockAccountConfiguration } from '../app/components/StockAccountConfiguration';
import { allowedStockRequest } from '../app/lib/stock-policy';
import { serviceCall } from '../app/lib/service-call';

vi.mock('../app/lib/service-call', async original => ({ ...(await original<typeof import('../app/lib/service-call')>()), serviceCall: vi.fn() }));
vi.mock('../app/components/StockTrackingCommon', () => ({ TrackingReference: ({ label, value, onChange }: { label: string; value: string | null; onChange: (value: string | null) => void }) => <input aria-label={label} value={value ?? ''} onChange={event => onChange(event.target.value || null)} /> }));
vi.mock('../app/components/AccountingConfigurationCommon', async original => ({ ...(await original<typeof import('../app/components/AccountingConfigurationCommon')>()), AccountingReference: ({ label, value, onChange, disabled, error }: { label: string; value: string | null; onChange: (value: string | null) => void; disabled?: boolean; error?: string }) => <label>{label}<input aria-label={label} disabled={disabled} aria-invalid={!!error} value={value ?? ''} onChange={event => onChange(event.target.value || null)} />{error && <span>{error}</span>}</label> }));
const company = '10000000-0000-7000-8000-000000000001', item = '10000000-0000-7000-8000-000000000002', id = '10000000-0000-7000-8000-000000000003';
it('allows one scoped stock balance read and rejects extra filters or writes', () => {
  const path = '/v1/companies/' + company + '/stock/positions/balance';
  expect(allowedStockRequest('GET', path + '?item_id=' + item)).toBe(true);
  expect(allowedStockRequest('GET', path + '?item_id=' + item + '&warehouse_id=' + id)).toBe(true);
  expect(allowedStockRequest('GET', path)).toBe(false);
  expect(allowedStockRequest('GET', path + '?item_id=' + item + '&limit=200')).toBe(false);
  expect(allowedStockRequest('POST', path + '?item_id=' + item)).toBe(false);
});
it('allows only bounded opening line reads with an explicit stock date', () => {
  const path = '/v1/companies/' + company + '/stock/opening-lines';
  expect(allowedStockRequest('GET', path + '?stock_date=2026-04-01&limit=50')).toBe(true);
  expect(allowedStockRequest('GET', path)).toBe(false);
  expect(allowedStockRequest('POST', path + '?stock_date=2026-04-01')).toBe(false);
  expect(allowedStockRequest('GET', path + '?stock_date=2026-04-01&account_id=' + id)).toBe(false);
});
const keys = ['inventory_account_id', 'receipt_clearing_account_id', 'dispatch_clearing_account_id', 'opening_offset_account_id', 'variance_account_id'];
const labels = ['Inventory asset account', 'Goods received clearing', 'Goods dispatched clearing', 'Opening balance offset', 'Stock variance account'];
const api = vi.fn(), page = { limit: 25, has_more: false, next_cursor: null };
let hidden = false;
beforeEach(() => {
  vi.clearAllMocks(); hidden = false;
  vi.mocked(serviceCall).mockImplementation((_endpoint, request) => api(request) as never);
  api.mockImplementation(async request => {
    const path = request.path as string;
    if (path.endsWith('/configuration')) return { generation: 9, posting_enabled: false, can_configure: true };
    if (path.endsWith('/field-set')) return { resource: 'stock-' + path.split('/').at(-2), fields: ['item_id', 'warehouse_id', 'lot_id', 'quantity', 'value', 'currency', 'method', 'stock_date', 'custody_kind', 'valid_from', 'reason', ...keys].map(key => ({ key, label: key, readable: !(hidden && ['value', 'currency', 'item_id'].includes(key)), visible: !(hidden && ['value', 'currency', 'item_id'].includes(key)), writable: true, required: false, definition: { type: 'string' } })) };
    if (path.includes('/account-policies?')) return { items: [], page };
    return { items: [{ id, item_id: item, warehouse_id: id, quantity: '2.0000', value: '12.5000', currency: 'INR', method: 'FIFO', custody_kind: 'WAREHOUSE', stock_date: '2026-10-28' }], page };
  });
});
it.each(['cost-pools', 'positions', 'movements'] as const)('renders %s with shared stock controls and activation status', async view => {
  render(<StockDirectory company={company} view={view} canConfigure={false} />);
  expect(await screen.findByRole('link', { name: 'View stock' })).toHaveAttribute('href', '/inventory/stock?item_id=' + item);
  expect(screen.getByRole('navigation', { name: 'Stock views' })).toBeVisible();
  expect(screen.getByText(/awaiting installation activation/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled();
});
it('removes hidden value columns and product filters before requesting rows', async () => {
  hidden = true;
  render(<StockDirectory company={company} view="cost-pools" canConfigure={false} initialQuery={'item_id=' + item} />);
  await screen.findByRole('columnheader', { name: 'On hand' });
  expect(screen.queryByRole('columnheader', { name: 'Carrying value' })).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Product filter')).not.toBeInTheDocument();
  expect(api.mock.calls.filter(([request]) => request.path.includes('/cost-pools?')).every(([request]) => !request.path.includes('item_id='))).toBe(true);
});
it('shows stock account setup read-only without configure authority', async () => {
  render(<StockAccountConfiguration company={company} canConfigure={false} generation={9} onSaved={() => {}} />);
  await screen.findByText(/Stock accounts have not been configured/);
  expect(screen.queryByRole('button', { name: 'Save stock accounts' })).not.toBeInTheDocument();
});
it('retains exact account mapping body and key after an uncertain save', async () => {
  const original = api.getMockImplementation()!, writes: Array<{ key: string; body: Record<string, unknown> }> = [];
  api.mockImplementation(async request => {
    if (request.method === 'POST') { writes.push(request); if (writes.length === 1) throw { status: 503, message: 'Connection lost' }; return { id, company_id: company, valid_from: '2026-04-01', row_version: 1 }; }
    return original(request);
  });
  const onSaved = vi.fn();
  const { rerender } = render(<StockAccountConfiguration company={company} canConfigure generation={9} onSaved={onSaved} />);
  await screen.findByLabelText('Inventory asset account');
  labels.forEach((label, index) => fireEvent.change(screen.getByLabelText(label), { target: { value: '20000000-0000-7000-8000-00000000000' + (index + 1) } }));
  fireEvent.change(screen.getByLabelText('Effective from'), { target: { value: '2026-04-01' } });
  fireEvent.change(screen.getByLabelText('Reason for configuration'), { target: { value: 'Initial reviewed stock accounts' } });
  await userEvent.click(screen.getByRole('button', { name: 'Save stock accounts' }));
  await screen.findByRole('button', { name: 'Retry the same save' });
  expect(screen.queryByRole('button', { name: 'Reload and review' })).not.toBeInTheDocument();
  expect(screen.getByLabelText('Inventory asset account')).toBeDisabled();
  rerender(<StockAccountConfiguration company={company} canConfigure generation={99} onSaved={onSaved} />);
  await userEvent.click(screen.getByRole('button', { name: 'Retry the same save' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  expect(writes).toHaveLength(2); expect(writes[0]!.key).toBe(writes[1]!.key);
  expect(writes[1]!.body).toEqual(writes[0]!.body); expect(writes[1]!.body.expected_generation).toBe(9);
});
it('limits the browser proxy to exact stock reads and account-policy publication', () => {
  const base = '/v1/companies/' + company + '/stock';
  expect(allowedStockRequest('GET', base + '/movements?item_id=' + item + '&limit=25')).toBe(true);
  expect(allowedStockRequest('POST', base + '/account-policies')).toBe(true);
  for (const path of ['/movements/post', '/positions?sort=value', '/positions?limit=0', '/positions?item_id=wrong', '/positions?limit=25&limit=50', '/../journals', '/%2e%2e/journals']) expect(allowedStockRequest('GET', base + path)).toBe(false);
  expect(allowedStockRequest('POST', base + '/movements')).toBe(false);
  expect(allowedStockRequest('PATCH', base + '/positions/' + id)).toBe(false);
});

it('offers an audited unused-mapping correction and preserves its explicit target', async () => {
  const original = api.getMockImplementation()!, writes: Array<{ body: Record<string, unknown> }> = [];
  const mapping = Object.fromEntries(keys.map((key, index) => [key, '20000000-0000-7000-8000-00000000000' + (index + 1)]));
  api.mockImplementation(async request => {
    if (request.method === 'POST') { writes.push(request); return { id, company_id: company, valid_from: '2026-04-01' }; }
    if (request.path.includes('/account-policies?')) return { items: [{ id }], page };
    if (request.path.endsWith('/account-policies/' + id)) return { id, company_id: company, valid_from: '2026-10-28', ...mapping };
    return original(request);
  });
  render(<StockAccountConfiguration company={company} canConfigure generation={9} correctablePolicyId={id} onSaved={() => {}} />);
  await screen.findByRole('checkbox', { name: 'Correct the unused mapping' });
  await userEvent.click(screen.getByRole('checkbox', { name: 'Correct the unused mapping' }));
  fireEvent.change(screen.getByLabelText('Effective from'), { target: { value: '2026-04-01' } });
  fireEvent.change(screen.getByLabelText('Reason for configuration'), { target: { value: 'Correct initial opening date' } });
  await userEvent.click(screen.getByRole('button', { name: 'Save stock accounts' }));
  await waitFor(() => expect(writes).toHaveLength(1));
  expect(writes[0]!.body.correct_unused_id).toBe(id);
  expect(writes[0]!.body.valid_from).toBe('2026-04-01');
});
