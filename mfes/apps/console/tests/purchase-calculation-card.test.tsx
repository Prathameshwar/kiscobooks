import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PurchaseCalculationCard } from '../app/components/PurchaseCalculationCard';
import type { PurchaseCalculation } from '../app/lib/purchase-api';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
type Code = 'CGST' | 'SGST' | 'UTGST' | 'IGST' | 'CESS';
const tax = (code: Code, amount: string, supplier_charged = true) => ({ key: code + amount, code, amount, basis: '1000.0000', supplier_charged });
const line = (n: number, taxable: string, payable: string, taxes: ReturnType<typeof tax>[]) => ({ key: id(n), entered: taxable, commercial: taxable, taxable, price_rounding: '0.0000', payable, taxes });
const base = { commercial_total: '1500.0000', tax_total: '0.0000', rounding: '0.0000', payable: '1500.0000', supplier_difference: null, lines: [] } as unknown as PurchaseCalculation;
const calc = (patch: Partial<PurchaseCalculation>) => ({ ...base, ...patch }) as PurchaseCalculation;
const lines = [{ key: id(1), label: 'Professional fees' }, { key: id(2), label: 'Office rent' }];

describe('the GST in Accounting’s calculation of a Purchase bill', () => {
  it('shows nothing about GST for a bill that has none', () => {
    render(<PurchaseCalculationCard calculation={calc({ lines: [line(1, '1500.0000', '1500.0000', [])] })} accepted={false} revision={1} lines={lines} />);
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByText(/Reverse-charge/)).toBeNull();
    expect(screen.queryByText('CGST')).toBeNull();
  });

  it('adds each component once, across the lines, and a table line by line named as the bill names them', () => {
    const value = calc({ tax_total: '270.0000', payable: '1770.0000', lines: [
      line(1, '1000.0000', '1180.0000', [tax('CGST', '90.0000'), tax('SGST', '90.0000')]),
      line(2, '500.0000', '590.0000', [tax('CGST', '45.0000'), tax('SGST', '45.0000')]),
    ] });
    const { container } = render(<PurchaseCalculationCard calculation={value} accepted={false} revision={2} lines={lines} />);
    const figures = container.querySelector('.janso-purchase-figures')!;
    expect(within(figures as HTMLElement).getByText('CGST').nextElementSibling).toHaveTextContent('₹135.00');
    expect(within(figures as HTMLElement).getByText('SGST').nextElementSibling).toHaveTextContent('₹135.00');
    const table = screen.getByRole('table', { name: 'GST line by line' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows.map(row => within(row).getByRole('rowheader').textContent)).toEqual(['Professional fees', 'Office rent']);
    expect(within(rows[0]!).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['₹1,000.00', '₹180.00', '₹1,180.00']);
    expect(within(rows[1]!).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['₹500.00', '₹90.00', '₹590.00']);
    expect(screen.queryByText(/Reverse-charge/)).toBeNull();
  });

  it('names a line "Line N" when the bill has no name for it', () => {
    render(<PurchaseCalculationCard calculation={calc({ lines: [line(7, '1500.0000', '1770.0000', [tax('IGST', '270.0000')])] })} accepted revision={1} lines={lines} />);
    expect(within(screen.getByRole('table')).getByRole('rowheader')).toHaveTextContent('Line 1');
  });

  it('keeps reverse-charge tax apart from tax the supplier charged, and says it is the company’s own to pay', () => {
    const value = calc({ tax_total: '270.0000', payable: '1500.0000', lines: [line(1, '1500.0000', '1500.0000', [tax('IGST', '180.0000', true), tax('IGST', '90.0000', false)])] });
    const { container } = render(<PurchaseCalculationCard calculation={value} accepted={false} revision={1} lines={lines} />);
    const figures = container.querySelector('.janso-purchase-figures')! as HTMLElement;
    expect(within(figures).getByText('IGST').nextElementSibling).toHaveTextContent('₹180.00');
    expect(within(figures).getByText('IGST · reverse charge').nextElementSibling).toHaveTextContent('₹90.00');
    expect(screen.getByText(/Reverse-charge GST is yours to pay to the government.*not part of the supplier payable/)).toBeVisible();
  });

  it('names cess and UTGST as they are named in the service', () => {
    render(<PurchaseCalculationCard calculation={calc({ lines: [line(1, '1000.0000', '1000.0000', [tax('UTGST', '9.0000'), tax('CESS', '1.0000')])] })} accepted={false} revision={1} lines={lines} />);
    expect(screen.getByText('UTGST')).toBeVisible();
    expect(screen.getByText('Cess')).toBeVisible();
  });
});
