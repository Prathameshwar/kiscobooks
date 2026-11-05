import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { VoucherEntry } from '../app/components/VoucherEntry';
import { productFieldRequest } from '../app/lib/product-fields';
import { COMPANY, RECORD, SOURCE } from './product-classification-fixtures';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('../app/components/VoucherItems', () => ({
  VoucherItems: ({ lines }: { lines: unknown[] }) => (
    <output data-testid="opening-items">{JSON.stringify(lines)}</output>
  ),
}));
vi.mock('../app/components/VoucherStock', () => ({
  VoucherStock: () => <p>Stock dimensions</p>,
}));
vi.mock('@janso/ui', async (original) => ({
  ...(await original<typeof import('@janso/ui')>()),
  Select: ({
    label,
    onChange,
    options,
  }: {
    label: string;
    onChange: (value: string) => void;
    options: { value: string; label: string }[];
  }) => (
    <select
      aria-label={label}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="" />
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));
let opening = true,
  wrongCompany = false;
beforeEach(() => {
  opening = true;
  wrongCompany = false;
  vi.mocked(productFieldRequest)
    .mockReset()
    .mockImplementation(async (_service, _method, path) => {
      if (path.includes('/field-set'))
        return {
          native: { properties: { stock: {}, stock_date: {} } },
          custom: [],
          configuration: {
            kind: 'STOCK_JOURNAL',
            profile: opening ? 'OPENING' : 'TRANSFER',
            type_revision_id: SOURCE,
            policy: { stock: { opening_gl_mode: 'COMBINED' } },
          },
        } as never;
      if (path.includes('/items/'))
        return {
          id: RECORD,
          company_id: wrongCompany ? SOURCE : COMPANY,
          status: 'ACTIVE',
          row_version: 3,
          base_unit_id: SOURCE,
        } as never;
      return {
        items: path.includes('voucher-types')
          ? [{ id: SOURCE, name: 'Opening stock' }]
          : [],
      } as never;
    });
});
async function load() {
  fireEvent.click(screen.getByRole('button', { name: 'Load voucher types' }));
  await screen.findByRole('option', { name: 'Opening stock' });
  fireEvent.change(screen.getByLabelText('Voucher type'), {
    target: { value: SOURCE },
  });
  fireEvent.change(screen.getByLabelText('Document date'), {
    target: { value: '2026-04-01' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Load entry fields' }));
}
it('prefills the same native product ID and its verified version/base unit', async () => {
  render(
    <VoucherEntry
      company={COMPANY}
      currency="INR"
      canCreate
      openingOnly
      initialItemId={RECORD}
    />,
  );
  await load();
  const lines = JSON.parse(
    (await screen.findByTestId('opening-items')).textContent!,
  );
  expect(lines).toHaveLength(1);
  expect(lines[0]).toMatchObject({
    line_kind: 'ITEM',
    item: { item_id: RECORD, item_version: 3, unit_id: SOURCE },
  });
  expect(
    screen.getByRole('heading', { name: 'Record opening stock' }),
  ).toBeVisible();
});
it('refuses a non-opening stock profile before constructing a draft', async () => {
  opening = false;
  render(
    <VoucherEntry
      company={COMPANY}
      currency="INR"
      canCreate
      openingOnly
      initialItemId={RECORD}
    />,
  );
  await load();
  await screen.findByText(
    /Choose a stock journal type configured for opening stock/,
  );
  expect(screen.queryByTestId('opening-items')).not.toBeInTheDocument();
});
it('refuses a product returned for another company', async () => {
  wrongCompany = true;
  render(
    <VoucherEntry
      company={COMPANY}
      currency="INR"
      canCreate
      openingOnly
      initialItemId={RECORD}
    />,
  );
  await load();
  await screen.findByText(
    'The product is unavailable or not active for opening stock.',
  );
  expect(screen.queryByTestId('opening-items')).not.toBeInTheDocument();
});
