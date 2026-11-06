import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { PurchaseStockDetails } from '../app/components/PurchaseStockDetails';
import { PurchaseBatchChooser } from '../app/components/PurchaseBatchChooser';
import { PurchaseBatchSummary } from '../app/components/PurchaseBatchSummary';
import { blankPurchaseLine } from '../app/lib/purchase-workspace';
import { productFieldRequest } from '../app/lib/product-fields';
import { preparePurchaseBatch, purchaseBatchEligibility, purchaseBatchProblems, type PurchaseTracking } from '../app/lib/purchase-stock';

vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('../app/components/VoucherStock', () => ({ StockReference: ({ label }: { label: string }) => <span>{label}</span> }));

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), item = id(2), batch = id(3), postingDate = '2026-10-31';
const profile: PurchaseTracking = { itemId: item, companyId: company, profileRevisionId: id(4), lotTracking: true, serialTracking: false,
  manufactureDateRequired: true, expiryRequired: true, shelfLifeDays: 365, minimumRemainingLifeDays: 30 };
const detail = { id: batch, company_id: company, item_id: item, code: 'B-1', status: 'ACTIVE', is_held: false, manufactured_on: '2026-01-01', expires_on: '2026-12-31' };
const access = { warehouse: true, bin: true, batch: true, serial: false };

beforeEach(() => {
  vi.mocked(productFieldRequest).mockReset();
  vi.mocked(productFieldRequest).mockImplementation(async (_service, method, path) => {
    if (path.includes('/context/')) return { company_id: company, item_id: item, profile_revision_id: profile.profileRevisionId,
      lot_tracking: true, serial_tracking: false, expiry_required: true, manufacture_date_required: true, shelf_life_days: 365, minimum_remaining_life_days: 30 } as never;
    if (path.endsWith('/warehouse-configuration')) return { company_id: company, default_purchase_warehouse_id: id(5) } as never;
    if (method === 'GET' && path.includes('/stock-tracking/batches?')) return { items: [detail], page: { has_more: false, next_cursor: null } } as never;
    if (method === 'GET' && path.endsWith('/stock-tracking/batches/' + batch)) return detail as never;
    if (method === 'POST' && path.endsWith('/stock-tracking/batches')) return detail as never;
    throw Error('Unexpected request ' + method + ' ' + path);
  });
});

function stock(options: { prompt?: boolean; saved?: boolean; canRead?: boolean; canCreate?: boolean } = {}) {
  const onChange = vi.fn();
  render(<DisplayConfigProvider config={{}}><PurchaseStockDetails company={company} line={{ ...blankPurchaseLine('p1', 'ITEM'), subject: item, label: 'Milk 1 L',
    ...(options.saved ? { stock: { warehouseId: id(5), binId: '', lotId: batch, unitIds: [id(6)] } } : {}) }} postingDate={postingDate}
    canEdit access={access} canReadBatch={options.canRead ?? true} canPrepareBatch={options.canCreate ?? true}
    promptForItem={options.prompt ? item : null} onChange={onChange} /></DisplayConfigProvider>);
  return { onChange, user: userEvent.setup() };
}

it('requires dates only when configured, and rejects expiry before posting or minimum remaining life', () => {
  const draft = { code: 'B-1', manufacturedOn: '', expiresOn: '', reason: 'Purchase receipt' };
  expect(purchaseBatchProblems(draft, profile, postingDate)).toMatchObject({ manufacturedOn: expect.any(String), expiresOn: expect.any(String) });
  expect(purchaseBatchProblems(draft, { ...profile, manufactureDateRequired: false, expiryRequired: false }, postingDate)).toEqual({});
  expect(purchaseBatchProblems({ ...draft, manufacturedOn: '2026-01-01', expiresOn: '2026-11-01' }, profile, postingDate).expiresOn).toMatch(/remaining shelf life/);
  expect(purchaseBatchEligibility({ status: 'ACTIVE', is_held: false, expires_on: '2026-10-01' }, profile, postingDate)).toMatch(/expires before/);
});

it('opens the chooser after selecting a tracked product and selects an existing batch', async () => {
  const { onChange, user } = stock({ prompt: true });
  expect(await screen.findByRole('dialog', { name: 'Choose batch for this purchase' })).toBeVisible();
  const search = screen.getByRole('combobox', { name: 'Search batches' });
  await user.type(search, 'B-1');
  await user.click(await screen.findByRole('option', { name: /B-1/ }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Use selected batch' })).toBeEnabled());
  await user.click(screen.getByRole('button', { name: 'Use selected batch' }));
  await waitFor(() => expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ lotId: batch, unitIds: [] })));
  expect(screen.queryByRole('dialog', { name: 'Choose batch for this purchase' })).not.toBeInTheDocument();
});

it('does not prompt for a product without batch tracking', async () => {
  vi.mocked(productFieldRequest).mockImplementation(async (_service, _method, path) => path.includes('/context/')
    ? { company_id: company, item_id: item, profile_revision_id: profile.profileRevisionId, lot_tracking: false, serial_tracking: false,
      expiry_required: false, manufacture_date_required: false, shelf_life_days: null, minimum_remaining_life_days: null } as never
    : { company_id: company, default_purchase_warehouse_id: id(5) } as never);
  stock({ prompt: true });
  expect(await screen.findByText('This product does not require batch or serial tracking.')).toBeVisible();
  expect(screen.queryByRole('dialog', { name: 'Choose batch for this purchase' })).not.toBeInTheDocument();
});

it('creates and selects a batch with its required dates and one idempotency key', async () => {
  const { onChange, user } = stock({ prompt: true });
  await user.click(await screen.findByRole('tab', { name: 'Create batch' }));
  await user.click(screen.getByRole('button', { name: 'Create and select batch' }));
  expect(screen.getByText('Expiry date is required for this product.')).toBeVisible();
  await user.type(screen.getByLabelText('Batch code'), 'B-1');
  await user.type(screen.getByLabelText('Manufacture date'), '2026-01-01');
  await user.type(screen.getByLabelText('Expiry date'), '2026-12-31');
  await user.click(screen.getByRole('button', { name: 'Create and select batch' }));
  await waitFor(() => expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ lotId: batch })));
  expect(productFieldRequest).toHaveBeenCalledWith('accounting', 'POST', `/v1/companies/${company}/stock-tracking/batches`,
    expect.objectContaining({ item_id: item, code: 'B-1', manufactured_on: '2026-01-01', expires_on: '2026-12-31' }), expect.any(String));
});

it('dismisses without a batch, then reopens the same chooser from the line', async () => {
  const { onChange, user } = stock({ prompt: true });
  await user.click(await screen.findByRole('button', { name: 'Cancel' }));
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.getByText('Select a batch for this product before saving the Purchase.')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Choose or create batch' }));
  expect(screen.getByRole('dialog', { name: 'Choose batch for this purchase' })).toBeVisible();
});

it('shows saved dates and offers Change batch without prompting again', async () => {
  const { user, onChange } = stock({ prompt: true, saved: true });
  expect(await screen.findByText(/Expires/)).toBeVisible();
  expect(screen.queryByRole('dialog', { name: 'Choose batch for this purchase' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Change batch' }));
  expect(screen.getByRole('dialog', { name: 'Choose batch for this purchase' })).toBeVisible();
  expect(onChange).not.toHaveBeenCalled();
});

it('hides batch creation without manage permission and keeps the read permission separate', async () => {
  const { user } = stock({ prompt: true, canCreate: false });
  expect(await screen.findByRole('dialog', { name: 'Choose batch for this purchase' })).toBeVisible();
  expect(screen.queryByRole('tab', { name: 'Create batch' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.getByRole('button', { name: 'Choose or create batch' })).toBeVisible();
});

it('rejects an Accounting response for another product before applying a batch', async () => {
  vi.mocked(productFieldRequest).mockResolvedValue({ ...detail, item_id: id(99) } as never);
  await expect(preparePurchaseBatch(company, item, { code: 'B-1', manufacturedOn: '2026-01-01', expiresOn: '2026-12-31', reason: 'Purchase receipt' }, profile, 'key', postingDate)).rejects.toThrow(/could not be verified/);
});

it('rejects a prepared batch whose returned dates differ from the requested dates', async () => {
  vi.mocked(productFieldRequest).mockResolvedValue({ ...detail, expires_on: '2026-11-30' } as never);
  await expect(preparePurchaseBatch(company, item, { code: 'B-1', manufacturedOn: '2026-01-01', expiresOn: '2026-12-31', reason: 'Purchase receipt' }, profile, 'key', postingDate)).rejects.toThrow(/could not be verified/);
});

it('blocks a held batch before it can be selected', async () => {
  vi.mocked(productFieldRequest).mockImplementation(async (_service, _method, path) => path.includes('/batches?')
    ? { items: [{ ...detail, is_held: true }], page: { has_more: false, next_cursor: null } } as never
    : { ...detail, is_held: true } as never);
  render(<DisplayConfigProvider config={{}}><PurchaseBatchChooser company={company} item={item} name="Milk 1 L" postingDate={postingDate} profile={profile} canCreate={false} onSelect={vi.fn()} onClose={vi.fn()} /></DisplayConfigProvider>);
  await userEvent.type(screen.getByRole('combobox', { name: 'Search batches' }), 'B-1');
  expect(await screen.findByText('Couldn’t load results.')).toBeVisible();
});

it('shows the verified batch code and expiry on saved lines, respecting read access', async () => {
  const { rerender } = render(<DisplayConfigProvider config={{}}><PurchaseBatchSummary company={company} item={item} batchId={batch} permitted /></DisplayConfigProvider>);
  expect(await screen.findByText(/Batch B-1.*Expires/)).toBeVisible();
  expect(productFieldRequest).toHaveBeenCalledWith('accounting', 'GET', `/v1/companies/${company}/stock-tracking/batches/${batch}`, undefined, undefined, expect.any(AbortSignal));
  vi.mocked(productFieldRequest).mockClear();
  rerender(<DisplayConfigProvider config={{}}><PurchaseBatchSummary company={company} item={item} batchId={batch} permitted={false} /></DisplayConfigProvider>);
  expect(screen.getByText('Batch selected')).toBeVisible();
  expect(productFieldRequest).not.toHaveBeenCalled();
});
