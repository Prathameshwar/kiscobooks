import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { VoucherUnitReference } from '../app/components/VoucherUnitReference';
import { productFieldRequest } from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
const company = '10000000-0000-7000-8000-000000000001', unit = '10000000-0000-7000-8000-000000000002';
beforeEach(() => { vi.mocked(productFieldRequest).mockReset(); });
it('hydrates the selected unit label and locks physical stock to its base unit', async () => {
  vi.mocked(productFieldRequest).mockResolvedValue({ id: unit, company_id: company, code: 'PCS', name: 'Pieces' } as never);
  render(<VoucherUnitReference company={company} label="Stock unit" value={unit} disabled={false} baseOnly onChange={vi.fn()} />);
  expect(await screen.findByDisplayValue('Pieces')).toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: 'Stock unit' })).toBeDisabled();
  expect(screen.queryByDisplayValue(unit)).not.toBeInTheDocument();
});
it('does not show a unit from another company', async () => {
  vi.mocked(productFieldRequest).mockResolvedValue({ id: unit, company_id: unit, code: 'FOREIGN', name: 'Other company unit' } as never);
  render(<VoucherUnitReference company={company} label="Stock unit" value={unit} disabled={false} baseOnly={false} onChange={vi.fn()} />);
  await screen.findByText('Unit ownership could not be verified.');
  expect(screen.queryByDisplayValue('Other company unit')).not.toBeInTheDocument();
  expect(screen.queryByDisplayValue(unit)).not.toBeInTheDocument();
});
