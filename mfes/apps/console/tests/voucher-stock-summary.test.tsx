import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import type { components } from '@janso/api-client/vouchers';
import { VoucherStockSummary } from '../app/components/VoucherStockSummary';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const stock = { version: 1, action: 'RECEIPT', stock_date: '2026-10-28', currency: 'INR', reason: 'Goods received against delivery', lines: [{ line_id: id(1), item_id: id(2), warehouse_id: id(3), bin_id: id(4), lot_id: id(5), unit_ids: [id(6)], quantity: '1.0000', received_value: '1250.5000' }] } as components['schemas']['StockInput-Output'];
it('shows stock and tracking evidence without linking to retired record pages', () => {
  render(<VoucherStockSummary stock={stock} />);
  expect(screen.getByText('Goods received against delivery')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'View stock' })).toHaveAttribute('href', '/inventory/stock?item_id=' + id(2));
  expect(screen.getByText('Batch assigned')).toBeInTheDocument();
  expect(screen.getByText('Selected serials: 1')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /View product|View batch|View serial/ })).toBeNull();
  expect(screen.getByRole('columnheader', { name: 'Inward carrying value' })).toBeInTheDocument();
});
it('shows transfer destinations without presenting an invented inward value', () => {
  render(<VoucherStockSummary stock={{ ...stock, action: 'TRANSFER', lines: [{ ...stock.lines[0]!, received_value: null, destination_warehouse_id: id(7) }] }} />);
  expect(screen.getByRole('link', { name: 'View destination warehouse' })).toHaveAttribute('href', '/masters/warehouses/' + id(7));
  expect(screen.queryByRole('columnheader', { name: 'Inward carrying value' })).not.toBeInTheDocument();
});
it('names a goods purchase bill movement and never shows an entered inward value for it', () => {
  render(<VoucherStockSummary stock={{ ...stock, action: 'PURCHASE_INVOICE', lines: [{ ...stock.lines[0]!, received_value: null }] }} />);
  expect(screen.getByText('Purchase invoice receipt')).toBeInTheDocument();
  expect(screen.queryByRole('columnheader', { name: 'Inward carrying value' })).not.toBeInTheDocument();
});
