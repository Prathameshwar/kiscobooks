import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductCreationCard } from '../app/components/ProductCreationCard';
import { ProductCreationExperience } from '../app/components/ProductCreationExperience';
import { ProductExperience } from '../app/components/ProductExperience';
import { useProductMode } from '../app/components/ProductModeProvider';
import { COMPANY, access } from './product-classification-fixtures';

vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: vi.fn() }));
vi.mock('../app/components/SimpleProductCreate', () => ({ SimpleProductCreate: () => <p>Simple creation form</p> }));
vi.mock('../app/components/AdvancedProductWizard', () => ({ AdvancedProductWizard: () => <p>Advanced creation wizard</p> }));
vi.mock('../app/components/SimpleProductDirectory', () => ({ SimpleProductDirectory: () => <p>Simple directory</p> }));
const refresh = vi.fn();
const mode = (advanced: boolean) => ({ company: COMPANY, data: { company_id: COMPANY, row_version: 2, policy_generation: 4, product_family_sku_enabled: advanced }, loading: false, failure: null, refresh });
beforeEach(() => { vi.clearAllMocks(); });

it.each([[false, 'New product', 'Create product', 'Simple creation form'], [true, 'New Product Profile + SKUs', 'Create profile and SKUs', 'Advanced creation wizard']] as const)('uses the verified company mode for the card and direct URL', (advanced, title, action, form) => {
  vi.mocked(useProductMode).mockReturnValue(mode(advanced));
  render(<><ProductCreationCard company={COMPANY} href="/masters/items/new" canCreate /><ProductCreationExperience company={COMPANY} /></>);
  expect(screen.getByRole('heading', { name: title })).toBeVisible();
  expect(screen.getByRole('link', { name: action })).toHaveAttribute('href', '/masters/items/new');
  expect(screen.getByText(form)).toBeVisible();
});

it('blocks the direct URL and card when setup access is denied', () => {
  vi.mocked(useProductMode).mockReturnValue({ ...mode(false), data: null, failure: { status: 403, message: 'Denied' } });
  render(<><ProductCreationCard company={COMPANY} href="/masters/items/new" canCreate /><ProductCreationExperience company={COMPANY} /></>);
  expect(screen.queryByRole('link', { name: /Create product/ })).toBeNull();
  expect(screen.queryByText('Simple creation form')).toBeNull();
  expect(screen.getAllByText(/Product setup access is needed/)).toHaveLength(2);
});

it('offers a retry after a failed mode read and does not fall back to Simple', async () => {
  vi.mocked(useProductMode).mockReturnValue({ ...mode(false), data: null, failure: { status: 503, message: 'Unavailable' } });
  render(<><ProductCreationCard company={COMPANY} href="/masters/items/new" canCreate /><ProductCreationExperience company={COMPANY} /><ProductExperience company={COMPANY} access={access} initialQuery="" canImport={false}><p>Advanced directory</p></ProductExperience></>);
  expect(screen.queryByText('Simple directory')).toBeNull();
  expect(screen.queryByText('Simple creation form')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Retry product setup' }));
  expect(refresh).toHaveBeenCalled();
});

it('keeps a mounted Advanced wizard selected when the company mode changes', () => {
  vi.mocked(useProductMode).mockReturnValue(mode(true));
  const view = render(<ProductCreationExperience company={COMPANY} />);
  vi.mocked(useProductMode).mockReturnValue(mode(false));
  view.rerender(<ProductCreationExperience company={COMPANY} />);
  expect(screen.getByText('Advanced creation wizard')).toBeVisible();
});
