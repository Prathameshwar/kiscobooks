import { render, screen } from '@testing-library/react';
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
  expect(await screen.findByText(/Waiting for stock posting to release product definitions/)).toBeVisible();
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
  expect(advances).toBe(15);
  expect(screen.queryByRole('button', { name: 'Continue this creation' })).toBeNull();
});
