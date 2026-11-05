import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { PurchaseSupplierBalance } from '../app/components/PurchaseSupplierBalance';
import type { SupplierBalance } from '../app/lib/purchase-supplier-balance';

const supplier = '10000000-0000-7000-8000-000000000010';
const ready = (patch: Partial<Extract<SupplierBalance, { status: 'ready' }>>): SupplierBalance => ({ supplier, status: 'ready', side: 'CR', amount: '125000.0000', asOf: '2026-11-02', currency: 'INR', ...patch });
const amountOf = () => screen.getByRole('status').querySelector('.janso-purchase-balance__amount')!;

describe('the supplier balance under the Supplier field', () => {
  it('renders nothing when there is no balance to show', () => {
    const { container } = render(<PurchaseSupplierBalance balance={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('says the balance is being checked, in a live region, with no figure', () => {
    render(<PurchaseSupplierBalance balance={{ supplier, status: 'loading' }} />);
    const region = screen.getByRole('status');
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(region).toHaveTextContent('Checking the balance…');
    expect(region).not.toHaveTextContent('₹');
    expect(screen.queryByText('To pay')).toBeNull();
  });

  it('says it is not available, and that the bill can go on', () => {
    render(<PurchaseSupplierBalance balance={{ supplier, status: 'unavailable' }} />);
    expect(screen.getByRole('status')).toHaveTextContent('Not available right now. You can carry on with the bill.');
    expect(screen.queryByText('To pay')).toBeNull();
    expect(screen.getByRole('status')).not.toHaveTextContent('₹');
  });

  it('shows what is owed as one figure marked Cr, with To pay and the date it is as of', () => {
    render(<PurchaseSupplierBalance balance={ready({})} />);
    const region = screen.getByRole('status');
    expect(region).toHaveTextContent('Balance');
    expect(amountOf()).toHaveTextContent('₹1,25,000.00 Cr');
    expect(screen.getByText('To pay', { selector: '.janso-badge' })).toHaveAttribute('data-tone', 'warn');
    expect(region).toHaveTextContent('As of 02 Nov 2026, before this bill');
    expect(region).not.toHaveTextContent('-');
  });

  it('shows an amount to receive as Dr, with To receive', () => {
    render(<PurchaseSupplierBalance balance={ready({ side: 'DR', amount: '5000.5000' })} />);
    expect(amountOf()).toHaveTextContent('₹5,000.50 Dr');
    expect(screen.getByText('To receive', { selector: '.janso-badge' })).toHaveAttribute('data-tone', 'info');
    expect(screen.queryByText('To pay')).toBeNull();
  });

  it('shows nothing owed either way as a plain zero marked Settled, with neither Cr nor Dr', () => {
    render(<PurchaseSupplierBalance balance={ready({ side: 'NIL', amount: '0.0000' })} />);
    expect(amountOf()).toHaveTextContent('₹0.00');
    expect(amountOf()).not.toHaveTextContent(/Cr|Dr/);
    expect(screen.getByText('Settled', { selector: '.janso-badge' })).toHaveAttribute('data-tone', 'neutral');
  });

  it('takes grouping, separators, symbol side, precision and date pattern from the company display configuration, not the browser locale', () => {
    render(<DisplayConfigProvider config={{ digitGrouping: 'western', groupSeparator: '.', decimalSeparator: ',', currencySymbolPosition: 'suffix', amountPrecision: 3, dateFormat: 'dd/MM/yyyy', locale: 'de-DE' }}>
      <PurchaseSupplierBalance balance={ready({ amount: '12345678.9000' })} />
    </DisplayConfigProvider>);
    expect(amountOf()).toHaveTextContent('12.345.678,900₹ Cr');
    expect(screen.getByRole('status')).toHaveTextContent('As of 02/11/2026, before this bill');
  });
});
