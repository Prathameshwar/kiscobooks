import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import OverviewPage from '../app/page';
import CustomersPage from '../app/customers/page';
import ProductFieldsPage from '../app/products/custom-fields/page';
import { pageContext } from '../app/lib/page-context';
import { redirect } from 'next/navigation';
import { companyContextFor, sessionFor } from './helpers';
vi.mock('next/navigation', () => ({ redirect: vi.fn((path: string) => { throw new Error(path); }) }));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ProductFields', () => ({ ProductFields: () => <p>Field editor</p> }));
beforeEach(async () => {
  vi.clearAllMocks();
  const session = await sessionFor({ permissions: [] }); session.company = { id: 'company-a', name: 'A' };
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});
it('does not load overview figures for a role without report access', async () => {
  render(await OverviewPage({}));
  expect(screen.getByText('Company figures need report access')).toBeVisible();
  expect(screen.getByRole('heading', { level: 1, name: 'Business overview' })).toBeVisible();
  expect(screen.getByText(/Ask a company administrator to review your access/)).toBeVisible();
});
it('sends a company-less platform operator to administration', async () => {
  const data = await pageContext(); data.session.company = { name: 'Select a company' };
  data.session.permissions = ['platform.tenant.read'];
  await expect(OverviewPage({})).rejects.toThrow('/platform');
});
it('preserves the overview for platform operators with a selected company', async () => {
  const data = await pageContext(); data.session.permissions = ['platform.tenant.read'];
  render(await OverviewPage({}));
  expect(redirect).not.toHaveBeenCalled();
  expect(screen.getByRole('heading', { name: 'Business overview' })).toBeVisible();
});
it('preserves tenant onboarding and ordinary empty-company behavior', async () => {
  const data = await pageContext(); data.session.company = { name: 'Select a company' };
  data.context.companies = []; data.session.permissions = ['company.create'];
  await expect(OverviewPage({})).rejects.toThrow('/companies/new');
  vi.mocked(redirect).mockClear(); data.session.permissions = [];
  render(await OverviewPage({})); expect(redirect).not.toHaveBeenCalled();
});
it('does not load customers on an unauthorised direct visit', async () => {
  await expect(CustomersPage({})).rejects.toThrow('/accounting/parties?role=CUSTOMER'); expect(redirect).toHaveBeenCalledWith('/accounting/parties?role=CUSTOMER');
});
it('requires company selection before loading company business data', async () => {
  const data = await pageContext(); data.session.company = { name: 'Select a company' }; data.session.permissions = ['customer.read'];
  await expect(CustomersPage({})).rejects.toThrow('/accounting/parties?role=CUSTOMER');
});
it('does not render a product editor without its read permission', async () => {
  render(await ProductFieldsPage({})); expect(screen.queryByText('Field editor')).not.toBeInTheDocument();
});
it('routes legacy customer readers to the independently authorized party directory', async () => {
  const data = await pageContext(); data.session.permissions = ['customer.read'];
  await expect(CustomersPage({})).rejects.toThrow('/accounting/parties?role=CUSTOMER');
});
