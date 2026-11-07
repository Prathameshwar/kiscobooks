import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { ProductDetailHeader, ProductDetailView } from '../app/components/ProductDetailView';
import { fields, access, COMPANY, RECORD } from './product-classification-fixtures';

const metadata = [...fields('catalog.item'), ...fields('catalog.product_family').filter(field => ['kind', 'description'].includes(field.key))];
const row = { id: RECORD, company_id: COMPANY, name: 'Banjara Blue Notebook', sku: 'BN-A5-BLUE', status: 'ACTIVE', kind: 'GOODS', description: 'A5 ruled notebook.\nBlue cover with 160 pages.', sellable: true, purchasable: false, min_sale_quantity: '2.0000', row_version: 4 };
const mount = (visible = metadata) => render(<><ProductDetailHeader title={row.name} fields={visible} row={row} actions={<button>Edit product</button>} /><ProductDetailView company={COMPANY} fields={visible} row={row} access={access} returnTo={'/masters/items/' + RECORD} /></>);

it('presents product identity and readable grouped details without edit inputs', () => {
  mount();
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(row.name);
  expect(screen.getAllByText(row.sku)).toHaveLength(2);
  expect(screen.getByRole('heading', { name: 'Product overview' })).toBeVisible();
  const trading = screen.getByRole('region', { name: 'Trading' });
  expect(within(trading).getByText('Enabled')).toBeVisible();
  expect(within(trading).getByText('Disabled')).toBeVisible();
  expect(screen.queryByRole('textbox', { name: 'Name' })).toBeNull();
  expect(screen.getByText(/Blue cover with 160 pages/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Edit product' })).toBeEnabled();
});

it('excludes protected facts and protected status from the header and sections', () => {
  mount(metadata.map(field => ({ ...field, visible: !['sku', 'status', 'description', 'sellable', 'purchasable', 'min_sale_quantity'].includes(field.key) })));
  expect(screen.queryByText(row.sku)).toBeNull();
  expect(screen.queryByText('Active')).toBeNull();
  expect(screen.queryByText(/Blue cover with 160 pages/)).toBeNull();
  expect(screen.queryByRole('heading', { name: 'Trading' })).toBeNull();
});

it('links section navigation to real section headings', () => {
  mount();
  for (const link of within(screen.getByRole('navigation', { name: 'Product detail sections' })).getAllByRole('link')) {
    const target = document.getElementById(link.getAttribute('href')!.slice(1));
    expect(target).not.toBeNull();
    expect(target).toHaveAttribute('aria-labelledby');
    expect(target).toHaveAttribute('tabindex', '-1');
    fireEvent.click(link);
  }
});
