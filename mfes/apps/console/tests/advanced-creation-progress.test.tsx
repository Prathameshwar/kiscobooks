import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { AdvancedCreationProgress } from '../app/components/AdvancedCreationProgress';
import { masterRequest } from '../app/lib/catalog-master-api';
import type { AdvancedIntent } from '../app/lib/advanced-product-api';

vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
const company = '11111111-1111-4111-8111-111111111111';
const creation = '22222222-2222-4222-8222-222222222222';
const family = '33333333-3333-4333-8333-333333333333';
const item = '44444444-4444-4444-8444-444444444444';
const root = `/v1/companies/${company}/advanced-product-creations`;
const intent = (saved = false) => ({
  company, key: '55555555-5555-4555-8555-555555555555', definition: { profile: { kind: 'GOODS' }, skus: [{}] },
  work: { skus: [{ sku: 'TEA' }], opening: {} }, commands: {}, ...(saved ? { creation_id: creation } : {}),
}) as unknown as AdvancedIntent;
const receipt = (opening: 'SKIPPED' | 'IN_PROGRESS' | 'POSTED', version = 1) => ({
  id: creation, company_id: company, family_id: family, sku_ids: [item], row_version: version,
  status: opening === 'IN_PROGRESS' ? 'OPENING' : 'COMPLETE',
  sku_progress: [{ item_id: item, setup_done: true, price_draft_ids: [], published_price_ids: [], activated: true, opening_state: opening }],
});

beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); });

it('explains readiness blockers and returns to the correct editable step', async () => {
  const onEdit = vi.fn();
  const state = { ...receipt('IN_PROGRESS'), status: 'ACTIVATING', sku_progress: [{ ...receipt('IN_PROGRESS').sku_progress[0], activated: false, opening_state: 'NOT_REQUESTED' }] };
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path === root + '/definitions/' + creation) return state as never;
    if (request.path.endsWith('/readiness')) return { item_id: item, eligible: false, blockers: [{ step: 'business', path: 'business.skus.0.tax', code: 'hsn_required' }] } as never;
    throw new Error('Unexpected request ' + request.path);
  });
  render(<AdvancedCreationProgress initial={intent(true)} onEdit={onEdit} />);
  expect(await screen.findByText(/Step 3 · Business setup · TEA: Check the tax classification/)).toBeVisible();
  expect(within(screen.getByRole('region', { name: 'Product creation progress' })).getByRole('status')).toHaveTextContent('Creation needs attention');
  expect(screen.queryByText(/business\.skus\.0\.tax/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Review remaining setup' }));
  expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ creation_id: creation }), state, 3, undefined);
});

it('retries an uncertain initial request with the same key and clears failure after confirmed completion', async () => {
  let writes = 0;
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path === root + '/definitions' && request.method === 'POST') {
      if (++writes === 1) throw { status: 503, message: 'Product service is temporarily unavailable.' };
      return { creation: receipt('SKIPPED'), family: { company_id: company } } as never;
    }
    if (request.path === root + '/definitions/' + creation) return receipt('SKIPPED') as never;
    throw new Error('Unexpected request ' + request.path);
  });
  render(<AdvancedCreationProgress initial={intent()} onEdit={vi.fn()} />);
  await screen.findByText('Creation needs attention');
  expect(screen.queryByRole('progressbar')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Review product details' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Continue this creation' }));
  await screen.findByText('Product created successfully');
  expect(screen.queryByText('Product service is temporarily unavailable.')).toBeNull();
  expect(screen.getByRole('region', { name: 'Product saved' })).toHaveFocus();
  const requests = vi.mocked(masterRequest).mock.calls.map(([request]) => request).filter(request => request.path === root + '/definitions');
  expect(requests).toHaveLength(2);
  expect(requests[0]).toEqual(requests[1]);
});

it('shows styled progress immediately before definition confirmation', async () => {
  vi.mocked(masterRequest).mockImplementation(() => new Promise(() => {}));
  render(<AdvancedCreationProgress initial={intent()} onEdit={vi.fn()} />);
  expect(await screen.findByRole('progressbar', { name: 'Creating your product and SKUs' })).not.toHaveAttribute('aria-valuenow');
  expect(screen.getByText('Profile and SKUs')).toHaveAttribute('data-state', 'current');
  expect(screen.getByText('Ready to use')).toHaveAttribute('data-state', 'waiting');
});

it('retries a temporary definition fence with the original idempotency key', { timeout: 10000 }, async () => {
  let writes = 0;
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path === root + '/definitions' && request.method === 'POST') {
      if (++writes === 1) throw { status: 409, message: 'stock posting is using these definitions; retry after it completes' };
      return { creation: receipt('SKIPPED'), family: { company_id: company } } as never;
    }
    if (request.path === root + '/definitions/' + creation) return receipt('SKIPPED') as never;
    throw new Error('Unexpected request ' + request.path);
  });
  render(<AdvancedCreationProgress initial={intent()} onEdit={vi.fn()} />);
  expect(await screen.findByText(/Waiting for the current stock posting to finish/)).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('Work will resume automatically');
  expect(await screen.findByText(/Product Profile and all requested SKUs are complete/, {}, { timeout: 6000 })).toBeVisible();
  const requests = vi.mocked(masterRequest).mock.calls.map(([request]) => request).filter(request => request.path === root + '/definitions');
  expect(requests).toHaveLength(2);
  expect(requests[0]).toEqual(requests[1]);
});

it('keeps advancing a retained opening beyond twelve owner steps until it posts', async () => {
  let advances = 0;
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path === root + '/definitions/' + creation) return receipt(advances >= 15 ? 'POSTED' : 'IN_PROGRESS', advances + 1) as never;
    if (request.path.endsWith('/opening/advance')) return receipt(++advances >= 15 ? 'POSTED' : 'IN_PROGRESS', advances + 1) as never;
    throw new Error('Unexpected request ' + request.path);
  });
  render(<AdvancedCreationProgress initial={intent(true)} onEdit={vi.fn()} />);
  expect(await screen.findByText(/Product Profile and all requested SKUs are complete/)).toBeVisible();
  expect(screen.getByRole('region', { name: 'Product saved' })).toHaveFocus();
  expect(advances).toBe(15);
  expect(screen.queryByRole('button', { name: 'Continue this creation' })).toBeNull();
});

it('keeps command keys out of waiting messages and reuses the saved opening command', { timeout: 10000 }, async () => {
  let writes = 0;
  let saved = false;
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path === root + '/definitions/' + creation) return saved ? receipt('SKIPPED') : {
      ...receipt('IN_PROGRESS'), sku_progress: [{ ...receipt('IN_PROGRESS').sku_progress[0], opening_state: 'NOT_REQUESTED' }],
    } as never;
    if (request.path.endsWith('/opening')) {
      if (++writes === 1) throw { status: 409, message: 'stock posting is using these definitions; retry after it completes' };
      saved = true;
      return receipt('SKIPPED') as never;
    }
    throw new Error('Unexpected request ' + request.path);
  });
  render(<AdvancedCreationProgress initial={intent(true)} onEdit={vi.fn()} />);
  expect(await screen.findByText(/before saving opening stock/)).toBeVisible();
  expect(screen.getByRole('status')).not.toHaveTextContent(item);
  expect(await screen.findByText(/Product Profile and all requested SKUs are complete/, {}, { timeout: 6000 })).toBeVisible();
  const requests = vi.mocked(masterRequest).mock.calls.map(([request]) => request).filter(request => request.path.endsWith('/opening'));
  expect(requests).toHaveLength(2);
  expect(requests[0]).toEqual(requests[1]);
});

it('shows a saved opening retry reason after the browser request fails', async () => {
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path === root + '/definitions/' + creation) return {
      ...receipt('IN_PROGRESS'),
      sku_progress: [{ ...receipt('IN_PROGRESS').sku_progress[0], opening_error: 'Owner is temporarily unavailable' }],
    } as never;
    if (request.path.endsWith('/opening/advance')) throw { status: 503, message: 'Owner is temporarily unavailable' };
    throw new Error('Unexpected request ' + request.path);
  });
  render(<AdvancedCreationProgress initial={intent(true)} onEdit={vi.fn()} />);
  expect(await screen.findByText(/SKU 1: Owner is temporarily unavailable/)).toBeVisible();
  expect(await screen.findByRole('button', { name: 'Continue this creation' })).toBeVisible();
});
