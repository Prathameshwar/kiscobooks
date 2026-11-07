import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { components } from '@janso/api-client/catalog';
import { AdvancedCreationProgress } from '../app/components/AdvancedCreationProgress';
import { masterRequest } from '../app/lib/catalog-master-api';
import { definitionBody, type AdvancedIntent } from '../app/lib/advanced-product-api';
import { fixture, id, COMPANY } from './advanced-config-scenarios-fixtures';

vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
type Status = components['schemas']['AdvancedDefinitionStatus'];
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); });

it('lets a definite initial validation rejection return to editable product details', async () => {
  const { work, options } = fixture(1), edit = vi.fn();
  vi.mocked(masterRequest).mockRejectedValue({ status: 422, message: 'Check the product name.', fields: { name: 'Use a valid product name.' } });
  render(<AdvancedCreationProgress initial={{ company: COMPANY, key: id(80), definition: definitionBody(work, options), work, commands: {} }} onEdit={edit} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Review product details' }));
  expect(edit).toHaveBeenCalledWith(expect.objectContaining({ work }), null, 1, { name: 'Use a valid product name.' });
});

it('stops scheduling new native writes after the creation view unmounts', async () => {
  const { work, options } = fixture(2);
  const creation = id(90), family = id(91), item = id(100);
  const state: Status = { id: creation, company_id: COMPANY, family_id: family, row_version: 1, status: 'SETUP', step: 'SETUP', sku_ids: [item], sku_progress: [{ item_id: item, setup_done: false, activated: false, price_draft_ids: [], published_price_ids: [], opening_state: 'NOT_REQUESTED' }] };
  let finish: (value: Status) => void = () => {};
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path.endsWith('/definitions/' + creation)) return state as never;
    if (request.path.includes('/options?')) return options as never;
    if (request.path.includes('/authoring-defaults?')) return options.defaults as never;
    if (request.path.endsWith('/product-families/' + family)) return { company_id: COMPANY, row_version: 1 } as never;
    if (request.path.endsWith('/items/' + item)) return { company_id: COMPANY, family_id: family, row_version: 1 } as never;
    if (request.path.endsWith('/setup')) return new Promise(resolve => { finish = resolve; }) as never;
    return { ...state, row_version: 3 } as never;
  });
  const view = render(<AdvancedCreationProgress initial={{ company: COMPANY, key: id(80), creation_id: creation, definition: definitionBody(work, options), work, commands: {} }} onEdit={vi.fn()} />);
  await waitFor(() => expect(vi.mocked(masterRequest).mock.calls.some(([request]) => request.path.endsWith('/setup'))).toBe(true));
  view.unmount();
  await act(async () => { finish({ ...state, row_version: 2, sku_progress: [{ ...state.sku_progress![0]!, setup_done: true, price_draft_ids: [id(200)] }] }); });
  const writes = vi.mocked(masterRequest).mock.calls.map(([request]) => request).filter(request => request.method === 'POST');
  expect(writes).toHaveLength(1);
  expect(writes[0]!.path).toMatch(/\/setup$/);
});

it.each([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])('scenario %i drives real client commands through simulated native confirmations', async number => {
  const { work, options } = fixture(number);
  const items = work.skus.map((_, i) => id(100 + i)), creation = id(90), family = id(91);
  let state: Status = { id: creation, company_id: COMPANY, family_id: family, row_version: 1, status: 'DEFINED', step: 'SETUP', sku_ids: items,
    sku_progress: items.map(item_id => ({ item_id, setup_done: false, price_draft_ids: [], published_price_ids: [], activated: false, opening_state: 'NOT_REQUESTED' })) };
  const response = () => {
    if (state.sku_progress!.every(row => row.activated && (row.opening_state === 'SKIPPED' || row.opening_state === 'POSTED'))) state.status = 'COMPLETE';
    return structuredClone(state);
  };
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path.endsWith('/definitions') && request.method === 'POST') return { creation: response(), family: { id: family, company_id: COMPANY } } as never;
    if (request.path.includes('/options?')) return options as never;
    if (request.path.includes('/authoring-defaults?')) return options.defaults as never;
    if (request.path.endsWith('/product-families/' + family)) return { id: family, company_id: COMPANY, row_version: 1 } as never;
    const itemId = request.path.match(/\/items\/([^/]+)$/)?.[1];
    if (itemId) return { id: itemId, company_id: COMPANY, family_id: family, row_version: 1 } as never;
    if (request.path.endsWith('/definitions/' + creation)) return response() as never;
    const index = items.findIndex(item => request.path.includes('/skus/' + item + '/'));
    if (index < 0) throw new Error('Unexpected request ' + request.path);
    const row = state.sku_progress![index]!;
    if (request.path.endsWith('/setup')) {
      const body = request.body as components['schemas']['AdvancedSkuSetup'];
      expect(body.expected_creation_version).toBe(state.row_version);
      row.setup_done = true; row.price_draft_ids = (body.setup.prices ?? []).map((_, i) => id(200 + index * 10 + i));
    } else if (request.path.endsWith('/publish-prices')) row.published_price_ids = [...row.price_draft_ids!];
    else if (request.path.endsWith('/readiness')) return { item_id: items[index], eligible: true, blockers: [], source_version: 9, policy_generation: 4, family_version: 1, item_version: 1 } as never;
    else if (request.path.endsWith('/activate')) row.activated = true;
    else if (request.path.endsWith('/opening-preflight')) return { item_id: items[index] } as never;
    else if (request.path.endsWith('/opening/advance')) row.opening_state = 'POSTED';
    else if (request.path.endsWith('/opening')) row.opening_state = (request.body as { opening: { decision: string } }).opening.decision === 'OPEN' ? 'IN_PROGRESS' : 'SKIPPED';
    else throw new Error('Unexpected request ' + request.path);
    state.row_version++; return response() as never;
  });
  const intent: AdvancedIntent = { company: COMPANY, key: id(80), definition: definitionBody(work, options), work, commands: {} };
  render(<AdvancedCreationProgress initial={intent} onEdit={vi.fn()} />);
  const completed = await screen.findByRole('region', { name: 'Product saved' });
  expect(within(completed).getByText('Product created successfully')).toBeVisible();
  await waitFor(() => expect(completed).toHaveFocus());
  const requests = vi.mocked(masterRequest).mock.calls.map(([request]) => request);
  expect(requests.filter(request => request.path.endsWith('/definitions') && request.method === 'POST')).toHaveLength(1);
  expect(requests.filter(request => request.path.endsWith('/setup'))).toHaveLength(work.skus.length);
  expect(requests.filter(request => request.path.endsWith('/activate'))).toHaveLength(work.skus.length);
  expect(requests.filter(request => request.path.endsWith('/opening'))).toHaveLength(work.skus.length);
  expect(state.sku_progress!.every(row => row.setup_done && row.activated)).toBe(true);
  expect(sessionStorage.getItem('advanced-product-intent:' + COMPANY)).toBeNull();
});
