import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { OpeningStockHistory } from '../app/components/OpeningStockHistory';
import { serviceCall } from '../app/lib/service-call';
import {
  COMPANY,
  CONTROL,
  ITEM,
  WAREHOUSE,
  access,
  control,
  manifest,
  page,
} from './opening-stock-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/components/StockTrackingCommon', () => ({
  TrackingReference: () => null,
}));
vi.mock('../app/components/VoucherStock', () => ({
  StockReference: () => null,
}));
beforeEach(() => {
  vi.mocked(serviceCall)
    .mockReset()
    .mockImplementation(async (_endpoint, request) => {
      if (request.path.includes('/cohorts?'))
        return {
          items: [
            {
              id: CONTROL,
              item_id: ITEM,
              warehouse_id: WAREHOUSE,
              quantity: '2',
              value: '12.5',
              currency: 'INR',
              received_on: null,
              history_known: false,
              posting_id: CONTROL,
              source_key: 'opening-a',
              reversed: false,
            },
          ],
          page,
        } as never;
      if (request.path.includes('/revisions?'))
        return {
          items: [
            { id: CONTROL, revision: 1, created_at: '2026-04-01T00:00:00Z' },
          ],
          page,
        } as never;
      return manifest as never;
    });
});
it('shows unknown receipt history honestly and uses bounded typed product filters', async () => {
  render(
    <OpeningStockHistory
      company={COMPANY}
      control={control}
      access={access}
      initialItemId={ITEM}
    />,
  );
  expect(await screen.findByRole('cell', { name: 'Unknown' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Stock movements' })).toHaveAttribute(
    'href',
    '/inventory/stock?view=movements&posting_id=' + CONTROL,
  );
  expect(
    vi
      .mocked(serviceCall)
      .mock.calls.some(
        ([, request]) =>
          request.path.includes('item_id=' + ITEM) &&
          request.path.includes('limit=25'),
      ),
  ).toBe(true);
  await userEvent.click(
    screen.getByRole('button', { name: 'Review revision 1' }),
  );
  expect(
    await screen.findByText('Historical worksheet evidence'),
  ).toBeVisible();
});
it('does not render protected costs or offer export after access is denied', async () => {
  vi.mocked(serviceCall).mockRejectedValue({
    status: 403,
    message: 'Opening costs are protected.',
  });
  render(
    <OpeningStockHistory
      company={COMPANY}
      control={control}
      access={{ ...access, export: false }}
    />,
  );
  await screen.findByText('Opening costs are protected.');
  expect(
    screen.queryByRole('cell', { name: '12.50 INR' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'Export company opening evidence' }),
  ).not.toBeInTheDocument();
});
