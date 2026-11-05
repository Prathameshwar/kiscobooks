import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { CompanyDirectory } from '../app/components/CompanyDirectory';
import { CompanyWizard } from '../app/components/CompanyWizard';
import { CompanyFinancialYears } from '../app/components/CompanyFinancialYears';
import { companyCall } from '../app/lib/company-api';
import { goTo } from '../app/lib/navigate';
import { renderWithProviders, sessionFor } from './helpers';
import { companyId } from './access-fixtures';
vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn(), companyFailure: (error: unknown) => error, openCompany: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn() }));
beforeEach(() => {
  vi.mocked(goTo).mockReset(); vi.mocked(companyCall).mockReset();
  vi.mocked(companyCall).mockImplementation(async (_service, path) => {
    if (path.startsWith('/v1/companies?')) return { items: [{ id: companyId, display_name: 'Acme', code: 'AC', status: 'active', visibility: 'full', base_currency: 'INR' }], page: { has_more: false, next_cursor: null } };
    if (path === '/v1/company-features') return { items: [] };
    if (path.includes('/field-set')) return { fields: [] };
    return [];
  });
});
afterEach(() => vi.restoreAllMocks());
async function administrator() {
  const keys = ['company.read', 'company.create', 'company.update', 'period.read'];
  const session = await sessionFor({ permissions: keys });
  return { ...session, grants: [{ scope_type: 'tenant', scope_id: null, permissions: keys, valid_from: '2000-01-01', valid_to: null }] };
}
it('restores company directory filters and passes them to view/edit/create links', async () => {
  const session = await administrator();
  await renderWithProviders(<CompanyDirectory session={session} {...{ initialQuery: 'q=Ac&status=active&limit=25' }} />);
  const view = await screen.findByRole('link', { name: 'Acme' });
  expect(screen.getByRole('searchbox', { name: 'Search companies' })).toHaveValue('Ac');
  const back = new URL(view.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo');
  expect(back).toContain('/companies/manage?'); expect(back).toContain('q=Ac'); expect(back).toContain('limit=25');
  expect(new URL(screen.getByRole('link', { name: 'Create company' }).getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toBe(back);
});
it('returns an untouched company wizard to its explicit directory destination', async () => {
  const session = await administrator(), user = userEvent.setup();
  await renderWithProviders(<CompanyWizard session={session} canBootstrapBooks={false} {...{ returnTo: '/companies/manage?q=Ac' }} />);
  await user.click(await screen.findByRole('button', { name: 'Cancel' }));
  expect(goTo).toHaveBeenCalledWith('/companies/manage?q=Ac');
});
it('keeps an edited wizard when its navigation discard is declined', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false), session = await administrator(), user = userEvent.setup();
  await renderWithProviders(<CompanyWizard session={session} canBootstrapBooks={false} />);
  await user.type(await screen.findByRole('textbox', { name: /Legal name/ }), 'Acme');
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(confirm).toHaveBeenCalled(); expect(goTo).not.toHaveBeenCalled();
});
it('returns financial-year navigation to the company directory that opened it', async () => {
  await renderWithProviders(<CompanyFinancialYears session={await administrator()} companyId={companyId} companyName="Acme" {...{ returnTo: '/companies/manage?q=Ac' }} />);
  expect(screen.getByRole('link', { name: 'Back to companies' })).toHaveAttribute('href', '/companies/manage?q=Ac');
});
