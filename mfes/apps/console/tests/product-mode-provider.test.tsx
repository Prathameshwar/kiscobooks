import { act, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import {
  ProductModeProvider,
  modeEvent,
  useProductMode,
} from '../app/components/ProductModeProvider';
import { masterRequest } from '../app/lib/catalog-master-api';
import { sessionFor } from './helpers';
import { COMPANY, RECORD } from './product-classification-fixtures';
vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
function Probe() {
  const mode = useProductMode()!;
  return (
    <p>
      {mode.company}:{' '}
      {mode.data ? String(mode.data.product_family_sku_enabled) : 'unknown'}{' '}
      {mode.failure?.message}
    </p>
  );
}
it('ignores a late previous-company response and retains verified state during refresh', async () => {
  const session = await sessionFor();
  session.company = { id: COMPANY, name: 'One' };
  session.grants = [
    {
      permissions: ['product_configuration.read'],
      scope_type: 'tenant',
      scope_id: null,
      valid_from: '2020-01-01',
      valid_to: null,
    },
  ];
  let finishOld!: (data: unknown) => void,
    finishRefresh!: (data: unknown) => void;
  vi.mocked(masterRequest)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishOld = resolve as typeof finishOld;
        }),
    )
    .mockResolvedValueOnce({
      company_id: RECORD,
      row_version: 1,
      policy_generation: 8,
      product_family_sku_enabled: false,
    })
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishRefresh = resolve as typeof finishRefresh;
        }),
    );
  const view = render(
    <ProductModeProvider session={session}>
      <Probe />
    </ProductModeProvider>,
  );
  await waitFor(() => expect(masterRequest).toHaveBeenCalledTimes(1));
  view.rerender(
    <ProductModeProvider
      session={{ ...session, company: { id: RECORD, name: 'Two' } }}
    >
      <Probe />
    </ProductModeProvider>,
  );
  await screen.findByText(RECORD + ': false');
  await act(async () =>
    finishOld({
      company_id: COMPANY,
      row_version: 1,
      policy_generation: 8,
      product_family_sku_enabled: true,
    }),
  );
  expect(screen.getByText(RECORD + ': false')).toBeVisible();
  act(() => window.dispatchEvent(new Event(modeEvent)));
  await waitFor(() => expect(masterRequest).toHaveBeenCalledTimes(3));
  expect(screen.getByText(RECORD + ': false')).toBeVisible();
  await act(async () =>
    finishRefresh({
      company_id: RECORD,
      row_version: 2,
      policy_generation: 9,
      product_family_sku_enabled: true,
    }),
  );
  expect(screen.getByText(RECORD + ': true')).toBeVisible();
});
it('does not interpret denied mode access as single-product mode', async () => {
  vi.clearAllMocks();
  const session = await sessionFor();
  session.company = { id: COMPANY, name: 'One' };
  session.grants = [];
  render(
    <ProductModeProvider session={session}>
      <Probe />
    </ProductModeProvider>,
  );
  expect(screen.getByText(/unknown.*read access is required/)).toBeVisible();
  expect(masterRequest).not.toHaveBeenCalled();
});
