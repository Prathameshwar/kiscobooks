/** Diagnostics for unresolved quantity display findings from the unit review. */
import { render, screen } from '@testing-library/react';
import { DisplayConfigProvider } from '@janso/ui';
import { expect, it, vi } from 'vitest';
import { StockDirectory } from '../app/components/StockDirectory';
import { serviceCall } from '../app/lib/service-call';

vi.mock('../app/lib/service-call', async original => ({
  ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn(),
}));
vi.mock('../app/components/StockTrackingCommon', () => ({ TrackingReference: () => null }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');

it('reproduces nonzero stock displayed as zero without its base unit', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.path.endsWith('/configuration')) return { posting_enabled: true } as never;
    if (request.path.endsWith('/field-set')) return {
      resource: 'stock-cost-pools', fields: ['item_id', 'quantity', 'value', 'currency'].map(key => ({ key, readable: true, visible: true })),
    } as never;
    return { items: [{ id: id(3), item_id: id(2), quantity: '0.0010', value: '1', currency: 'INR' }],
      page: { limit: 25, has_more: false, next_cursor: null } } as never;
  });
  render(<DisplayConfigProvider config={{ quantityPrecision: 2 }}><StockDirectory company={id(1)} view="cost-pools" canConfigure={false} /></DisplayConfigProvider>);
  await screen.findByRole('link', { name: 'View product' }, { timeout: 10000 });
  expect(screen.getByRole('cell', { name: '0.00' })).toBeInTheDocument();
  expect(screen.queryByText(/0\.001/)).not.toBeInTheDocument();
  expect(screen.queryByRole('columnheader', { name: /unit/i })).not.toBeInTheDocument();
});
